"""Calendar boundary: deterministic local capacity and optional Google Calendar."""

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from voicedesk.config import get_settings
from voicedesk.domain import DomainError, overlaps, stored_utc, validate_local_instant, within_hours
from voicedesk.models import (
    Appointment,
    Blackout,
    BusinessHours,
    Service,
    ServiceZone,
    SlotClaim,
    StaffResource,
    Workspace,
)


class CalendarError(RuntimeError):
    pass


class LocalCalendar:
    def _resources(self, db: Session, workspace_id: str, service_id: str, zone_id: str) -> tuple[Service, ServiceZone, list[StaffResource]]:
        service = db.get(Service, service_id)
        zone = db.get(ServiceZone, zone_id)
        if not service or not service.active or service.workspace_id != workspace_id:
            raise DomainError("service_unavailable", "This service is not offered in this workspace.")
        if not zone or zone.workspace_id != workspace_id:
            raise DomainError("zone_unavailable", "This service zone is not available.")
        if service.eligible_zone_ids and zone_id not in service.eligible_zone_ids:
            raise DomainError("service_zone_unavailable", "This service is not offered in that zone.")
        staff = [resource for resource in db.scalars(select(StaffResource).where(StaffResource.workspace_id == workspace_id)) if service_id in resource.service_ids and zone_id in resource.zone_ids]
        if not staff:
            raise DomainError("service_zone_unavailable", "No qualified staff serves this zone for this service.")
        return service, zone, staff

    def is_available(self, db: Session, workspace_id: str, service_id: str, zone_id: str, staff_id: str, start_at: datetime, timezone_name: str, exclude_appointment_id: str | None = None) -> bool:
        start = validate_local_instant(start_at, timezone_name)
        service, _, staff = self._resources(db, workspace_id, service_id, zone_id)
        selected = next((person for person in staff if person.id == staff_id), None)
        if selected is None:
            return False
        end = start + timedelta(minutes=service.duration_minutes)
        workspace = db.get(Workspace, workspace_id)
        business_timezone = workspace.business_timezone if workspace else "America/New_York"
        local_start = start.astimezone(ZoneInfo(business_timezone))
        day = local_start.strftime("%A").lower()
        if not within_hours(start, end, selected.weekly_hours.get(day, []), business_timezone):
            return False
        global_hours = [dict(start=row.start_local, end=row.end_local) for row in db.scalars(select(BusinessHours).where(BusinessHours.workspace_id == workspace_id, BusinessHours.weekday == day))]
        has_business_schedule = db.scalar(select(BusinessHours.id).where(BusinessHours.workspace_id == workspace_id).limit(1)) is not None
        if has_business_schedule and not within_hours(start, end, global_hours, business_timezone):
            return False
        for blackout in db.scalars(select(Blackout).where(Blackout.workspace_id == workspace_id)):
            if blackout.staff_id in {None, staff_id} and overlaps(start, end, blackout.start_at, blackout.end_at):
                return False
        for appointment in db.scalars(select(Appointment).where(Appointment.workspace_id == workspace_id, Appointment.staff_id == staff_id, Appointment.status == "confirmed", Appointment.start_at < end, Appointment.end_at > start)):
            if appointment.id != exclude_appointment_id and overlaps(start, end, appointment.start_at, appointment.end_at):
                return False
        for claim in db.scalars(select(SlotClaim).where(SlotClaim.workspace_id == workspace_id, SlotClaim.staff_id == staff_id, SlotClaim.block_start_at >= start, SlotClaim.block_start_at < end)):
            if claim.appointment_id != exclude_appointment_id and start <= stored_utc(claim.block_start_at) < end:
                return False
        return True

    def slots(self, db: Session, workspace_id: str, service_id: str, zone_id: str, requested_date: date, timezone_name: str) -> list[dict]:
        service, _, staff = self._resources(db, workspace_id, service_id, zone_id)
        caller_zone = ZoneInfo(timezone_name)
        workspace = db.get(Workspace, workspace_id)
        business_zone = ZoneInfo(workspace.business_timezone if workspace else "America/New_York")
        output = []
        for person in staff:
            for offset in (-1, 0, 1):
                business_date = requested_date + timedelta(days=offset)
                for interval in person.weekly_hours.get(business_date.strftime("%A").lower(), []):
                    clock = time.fromisoformat(interval["start"])
                    cursor = datetime.combine(business_date, clock, tzinfo=business_zone)
                    end_local = datetime.combine(business_date, time.fromisoformat(interval["end"]), tzinfo=business_zone)
                    while cursor + timedelta(minutes=service.duration_minutes) <= end_local:
                        try:
                            if cursor.astimezone(caller_zone).date() == requested_date and self.is_available(db, workspace_id, service_id, zone_id, person.id, cursor.astimezone(timezone.utc), timezone_name):
                                output.append({"start_at": cursor.astimezone(timezone.utc), "end_at": (cursor + timedelta(minutes=service.duration_minutes)).astimezone(timezone.utc), "staff_id": person.id, "staff_name": person.name})
                        except DomainError:
                            pass
                        cursor += timedelta(minutes=30)
        return sorted(output, key=lambda item: (item["start_at"], item["staff_name"]))


class GoogleCalendar:
    """Google writes use a deterministic event ID; uncertain outcomes require reconciliation."""

    def __init__(self):
        settings = get_settings()
        if not settings.google_calendar_id or not settings.google_service_account_json:
            raise CalendarError("Google Calendar credentials and calendar ID are required.")
        self.calendar_id = settings.google_calendar_id
        self.credentials_path = settings.google_service_account_json

    def _client(self):
        import httplib2
        from google.oauth2 import service_account
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]
        try:
            credentials = (service_account.Credentials.from_service_account_info(json.loads(self.credentials_path), scopes=scopes)
                           if self.credentials_path.lstrip().startswith("{") else
                           service_account.Credentials.from_service_account_file(self.credentials_path, scopes=scopes))
            transport = AuthorizedHttp(credentials, http=httplib2.Http(timeout=10))
            return build("calendar", "v3", http=transport, cache_discovery=False)
        except Exception as exc:
            raise CalendarError("Google Calendar setup failed; check the calendar ID and service account configuration.") from exc

    def busy_intervals(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        """Read one bounded free/busy response for a range of candidate slots."""
        try:
            result = self._client().freebusy().query(body={
                "timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": self.calendar_id}],
            }).execute(num_retries=0)
        except CalendarError:
            raise
        except Exception as exc:
            raise CalendarError("Google Calendar free/busy request failed or timed out.") from exc
        calendar = result.get("calendars", {}).get(self.calendar_id)
        if not calendar or calendar.get("errors"):
            raise CalendarError("Google Calendar free/busy could not be verified.")
        try:
            return [(datetime.fromisoformat(entry["start"].replace("Z", "+00:00")),
                     datetime.fromisoformat(entry["end"].replace("Z", "+00:00")))
                    for entry in calendar.get("busy", [])]
        except (KeyError, TypeError, ValueError) as exc:
            raise CalendarError("Google Calendar free/busy response was invalid.") from exc

    def busy(self, start: datetime, end: datetime) -> bool:
        return any(overlaps(start, end, busy_start, busy_end)
                   for busy_start, busy_end in self.busy_intervals(start, end))

    def create_event(self, event_id: str, start: datetime, end: datetime, summary: str) -> str:
        body = {"id": event_id, "summary": summary,
                "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
                "extendedProperties": {"private": {"voicedesk_event_id": event_id}}}
        result = self._client().events().insert(calendarId=self.calendar_id, body=body).execute(num_retries=0)
        return result["id"]

    def get_event(self, event_id: str) -> dict | None:
        from googleapiclient.errors import HttpError
        try:
            return self._client().events().get(calendarId=self.calendar_id, eventId=event_id).execute(num_retries=0)
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise

    def delete_event(self, event_id: str) -> None:
        self._client().events().delete(calendarId=self.calendar_id, eventId=event_id).execute(num_retries=0)

    def update_event(self, event_id: str, start: datetime, end: datetime, summary: str) -> None:
        existing = self.get_event(event_id)
        if existing is None:
            raise CalendarError("External event is missing; reconcile before changing the booking.")
        existing.update({"summary": summary, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}})
        self._client().events().update(calendarId=self.calendar_id, eventId=event_id, body=existing).execute(num_retries=0)

    def conflicts_except(self, start: datetime, end: datetime, excluded_event_id: str) -> bool:
        """Reschedule must ignore its own old event while still detecting other writers."""
        result = self._client().events().list(
            calendarId=self.calendar_id, timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, maxResults=250,
        ).execute(num_retries=0)
        if result.get("nextPageToken"):
            raise CalendarError("Google Calendar conflict list was truncated; refusing to schedule.")
        return any(event.get("id") != excluded_event_id and event.get("status") != "cancelled" and
                   overlaps(start, end,
                            datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00")),
                            datetime.fromisoformat(event["end"]["dateTime"].replace("Z", "+00:00")))
                   for event in result.get("items", []) if "dateTime" in event.get("start", {}) and "dateTime" in event.get("end", {}))
