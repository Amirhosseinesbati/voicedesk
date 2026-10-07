"""Booking use cases. Database claims make retries and local slot races deterministic."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from voicedesk.calendar import CalendarError, GoogleCalendar, LocalCalendar
from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.domain import DomainError, blocks, stored_utc, validate_local_instant
from voicedesk.models import (
    Appointment,
    BookingOperation,
    Customer,
    DemoOutbox,
    Proposal,
    Service,
    SessionEvent,
    SlotClaim,
    SlotHold,
    StaffResource,
    VoiceSession,
    Workspace,
    utcnow,
)

_hasher = PasswordHasher()
_calendar = LocalCalendar()


class BookingError(DomainError):
    pass


def _id() -> str:
    return str(uuid4())


def _event(db: Session, session: VoiceSession, kind: str, detail: dict) -> None:
    db.add(SessionEvent(id=_id(), workspace_id=session.workspace_id, session_id=session.id, type=kind, detail=detail))


def _proposal_hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def make_proposal(db: Session, voice_session: VoiceSession, payload) -> Proposal:
    start = validate_local_instant(payload.start_at, payload.timezone)
    if start <= utcnow():
        raise BookingError("slot_in_past", "Choose a future appointment time.")
    db.scalar(select(Workspace).where(Workspace.id == voice_session.workspace_id).with_for_update())
    service, _, staff = _calendar._resources(db, voice_session.workspace_id, payload.service_id, payload.zone_id)
    if service.duration_minutes % 15:
        raise BookingError("invalid_duration", "Service duration must align to 15-minute blocks.")
    end = start + timedelta(minutes=service.duration_minutes)
    selected = next((resource for resource in staff if _calendar.is_available(db, voice_session.workspace_id, service.id, payload.zone_id, resource.id, payload.start_at, payload.timezone)), None)
    if not selected:
        raise BookingError("slot_unavailable", "That time is unavailable. Choose one of the current alternatives.")
    if _uses_google() and GoogleCalendar().busy(start, end):
        raise BookingError("provider_conflict", "The connected calendar reports this time as busy. Choose another slot.")
    if voice_session.active_proposal_id:
        old = db.get(Proposal, voice_session.active_proposal_id)
        if old and old.status == "pending":
            old.status = "superseded"
            old_hold = db.scalar(select(SlotHold).where(SlotHold.proposal_id == old.id))
            if old_hold:
                old_hold.status = "released"
    version = voice_session.proposal_version + 1
    values = {
        "session_id": voice_session.id, "version": version, "service_id": service.id,
        "zone_id": payload.zone_id, "staff_id": selected.id, "start_at": start.isoformat(),
        "end_at": end.isoformat(), "timezone": payload.timezone,
        "customer_name": payload.customer_name.strip(), "customer_email": str(payload.customer_email).lower(),
        "customer_phone": payload.customer_phone,
    }
    proposal = Proposal(
        id=_id(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
        version=version, proposal_hash=_proposal_hash(values), service_id=service.id,
        zone_id=payload.zone_id, staff_id=selected.id,
        customer_name=values["customer_name"], customer_email=values["customer_email"],
        customer_phone=payload.customer_phone, start_at=start, end_at=end,
        timezone=payload.timezone, status="pending", expires_at=utcnow() + timedelta(minutes=10),
    )
    db.add(proposal)
    db.flush()
    db.add(SlotHold(id=_id(), workspace_id=voice_session.workspace_id, proposal_id=proposal.id,
                    staff_id=selected.id, start_at=start, end_at=end, expires_at=proposal.expires_at))
    voice_session.proposal_version = version
    voice_session.active_proposal_id = proposal.id
    voice_session.stable_slots = values
    voice_session.timezone = payload.timezone
    voice_session.last_reply = f"Please confirm {service.name} on {start.astimezone(__import__('zoneinfo').ZoneInfo(payload.timezone)).strftime('%A, %B %d at %I:%M %p')} {payload.timezone} for {payload.customer_name}."
    _event(db, voice_session, "proposal_created", {"proposal_id": proposal.id, "version": version, "hash": proposal.proposal_hash})
    return proposal


def invalidate_proposal(db: Session, voice_session: VoiceSession, reason: str) -> None:
    if not voice_session.active_proposal_id:
        return
    proposal = db.get(Proposal, voice_session.active_proposal_id)
    if proposal and proposal.status == "pending":
        proposal.status = "superseded"
        hold = db.scalar(select(SlotHold).where(SlotHold.proposal_id == proposal.id))
        if hold:
            hold.status = "released"
    voice_session.active_proposal_id = None
    voice_session.proposal_version += 1
    _event(db, voice_session, "proposal_invalidated", {"reason": reason})


def _claim_blocks(db: Session, appointment: Appointment) -> None:
    for block in blocks(stored_utc(appointment.start_at), stored_utc(appointment.end_at)):
        db.add(SlotClaim(id=_id(), workspace_id=appointment.workspace_id, staff_id=appointment.staff_id,
                         appointment_id=appointment.id, block_start_at=block))
    db.flush()


def _operation_result(db: Session, workspace_id: str, key: str, kind: str) -> Appointment | None:
    existing = db.scalar(select(BookingOperation).where(BookingOperation.workspace_id == workspace_id, BookingOperation.idempotency_key == key))
    if not existing:
        return None
    if existing.kind != kind:
        raise BookingError("idempotency_reused", "This idempotency key belongs to a different action.")
    if existing.status != "committed" or not existing.appointment_id:
        raise BookingError("operation_pending", "The previous operation needs reconciliation before retrying.")
    return db.get(Appointment, existing.appointment_id)


def _demo_code(db: Session, appointment_id: str) -> str | None:
    record = db.scalar(select(DemoOutbox).where(DemoOutbox.appointment_id == appointment_id, DemoOutbox.kind == "booking_confirmation"))
    return record.body.split("Verification code: ")[-1] if record else None


def _uses_google() -> bool:
    settings = get_settings()
    return not settings.is_demo and settings.calendar_provider == "google"


def _set_provider_uncertain(operation_id: str, reason: str) -> None:
    with SessionLocal.begin() as db:
        operation = db.get(BookingOperation, operation_id)
        if operation and operation.status != "committed":
            operation.status = "uncertain"
            operation.failure_reason = reason[:500]


def _reject_google_booking(operation_id: str, reason: str) -> None:
    with SessionLocal.begin() as db:
        operation = db.get(BookingOperation, operation_id)
        appointment = db.get(Appointment, operation.appointment_id)
        proposal = db.get(Proposal, operation.proposal_id)
        voice_session = db.get(VoiceSession, operation.session_id)
        operation.status = "conflict"
        operation.failure_reason = reason
        appointment.status = "cancelled"
        proposal.status = "stale"
        db.execute(delete(SlotClaim).where(SlotClaim.appointment_id == appointment.id))
        if voice_session.active_proposal_id == proposal.id:
            voice_session.active_proposal_id = None
        _event(db, voice_session, "provider_conflict", {"operation_id": operation.id, "reason": reason})


def reconcile_google_booking(operation_id: str) -> str:
    """A stable Google event ID resolves retries; uncertainty retains local slot claims."""
    with SessionLocal() as db:
        operation = db.get(BookingOperation, operation_id)
        if not operation or operation.kind != "book":
            raise BookingError("operation_missing", "Booking operation not found.")
        appointment = db.get(Appointment, operation.appointment_id)
        service = db.get(Service, appointment.service_id)
        if operation.status == "committed":
            return appointment.id
        if operation.status == "conflict":
            raise BookingError("provider_conflict", operation.failure_reason or "External calendar conflict.")
        event_id = appointment.provider_event_id
        start, end, summary = stored_utc(appointment.start_at), stored_utc(appointment.end_at), service.name
    provider = GoogleCalendar()
    try:
        existing = provider.get_event(event_id)
        if existing is None:
            if provider.busy(start, end):
                _reject_google_booking(operation_id, "External calendar slot is occupied; no local booking was confirmed.")
                raise BookingError("provider_conflict", "External calendar slot is occupied; please choose another time.")
            try:
                created_id = provider.create_event(event_id, start, end, summary)
                if created_id != event_id:
                    raise CalendarError("Google Calendar returned an unexpected event ID.")
            except Exception:
                # A timeout may have occurred after the provider committed. Query the deterministic ID.
                existing = provider.get_event(event_id)
                if existing is None:
                    _set_provider_uncertain(operation_id, "Google create outcome could not be established.")
                    raise BookingError("provider_uncertain", "Calendar outcome is uncertain. The slot remains locally held; an operator must reconcile it.") from None
            else:
                existing = provider.get_event(event_id)
        if not _google_event_matches(existing, start, end, event_id):
            _set_provider_uncertain(operation_id, "Google event does not match the proposed time.")
            raise BookingError("provider_uncertain", "Calendar event details could not be verified; the slot remains held for reconciliation.")
    except BookingError:
        raise
    except Exception as exc:
        _set_provider_uncertain(operation_id, "Google availability or reconciliation failed.")
        raise CalendarError("Google Calendar is unavailable; booking is pending reconciliation.") from exc
    with SessionLocal.begin() as db:
        operation = db.scalar(select(BookingOperation).where(BookingOperation.id == operation_id).with_for_update())
        appointment = db.get(Appointment, operation.appointment_id)
        proposal = db.get(Proposal, operation.proposal_id)
        voice_session = db.get(VoiceSession, operation.session_id)
        operation.status = "committed"
        operation.failure_reason = None
        appointment.status = "confirmed"
        proposal.status = "confirmed"
        voice_session.active_proposal_id = None
        voice_session.status = "booked"
        voice_session.last_reply = "Your appointment is confirmed on the connected calendar. Keep the verification code shown now to change it later."
        hold = db.scalar(select(SlotHold).where(SlotHold.proposal_id == proposal.id))
        if hold:
            hold.status = "converted"
        _event(db, voice_session, "booking_confirmed", {"appointment_id": appointment.id, "operation_id": operation.id, "provider": "google"})
        return appointment.id


def confirm_proposal(workspace_id: str, session_id: str, proposal_id: str, version: int, proposal_hash: str, idempotency_key: str) -> tuple[str, str | None]:
    """Rechecks inside one transaction. Unique slot claims settle concurrent races."""
    with SessionLocal() as lookup:
        existing = lookup.scalar(select(BookingOperation).where(BookingOperation.workspace_id == workspace_id, BookingOperation.idempotency_key == idempotency_key))
        if existing:
            if existing.kind != "book" or existing.proposal_id != proposal_id:
                raise BookingError("idempotency_reused", "This key belongs to another action.")
            if _uses_google() and existing.status in {"pending_provider", "uncertain"}:
                return reconcile_google_booking(existing.id), None
            if existing.status == "committed":
                return existing.appointment_id, _demo_code(lookup, existing.appointment_id) if get_settings().is_demo else None
            raise BookingError("operation_pending", f"Booking operation {existing.id} needs reconciliation.")
    operation_id = None
    code = None
    try:
        with SessionLocal.begin() as db:
            db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
            voice_session = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.workspace_id == workspace_id).with_for_update())
            proposal = db.scalar(select(Proposal).where(Proposal.id == proposal_id, Proposal.workspace_id == workspace_id).with_for_update())
            if not voice_session or not proposal or proposal.session_id != session_id:
                raise BookingError("proposal_missing", "This proposal is unavailable.")
            if proposal.status != "pending" or voice_session.active_proposal_id != proposal.id or proposal.version != version or voice_session.proposal_version != version or proposal.proposal_hash != proposal_hash:
                raise BookingError("proposal_stale", "Details changed; review a new proposal before confirming.")
            if stored_utc(proposal.expires_at) <= utcnow():
                raise BookingError("proposal_expired", "This proposal expired. Check availability again.")
            service = db.get(Service, proposal.service_id)
            if not service or stored_utc(proposal.end_at) - stored_utc(proposal.start_at) != timedelta(minutes=service.duration_minutes):
                raise BookingError("proposal_stale", "Service duration changed; review a new proposal before confirming.")
            db.scalar(select(StaffResource).where(StaffResource.id == proposal.staff_id).with_for_update())
            if not _calendar.is_available(db, workspace_id, proposal.service_id, proposal.zone_id, proposal.staff_id, stored_utc(proposal.start_at), proposal.timezone):
                raise BookingError("slot_conflict", "The slot was just taken. Please choose an alternative.")
            customer = db.scalar(select(Customer).where(Customer.workspace_id == workspace_id, Customer.email == proposal.customer_email))
            if not customer:
                customer = Customer(id=_id(), workspace_id=workspace_id, name=proposal.customer_name,
                                    email=proposal.customer_email, phone=proposal.customer_phone)
                db.add(customer)
                db.flush()
            code = f"{secrets.randbelow(1_000_000):06d}"
            appointment = Appointment(id=_id(), workspace_id=workspace_id, customer_id=customer.id,
                                      booking_reference=f"CED-{secrets.token_hex(4).upper()}",
                                      service_id=proposal.service_id, zone_id=proposal.zone_id, staff_id=proposal.staff_id,
                                      start_at=proposal.start_at, end_at=proposal.end_at,
                                      status="pending_provider" if _uses_google() else "confirmed",
                                      source_session_id=session_id, verification_hash=_hasher.hash(code),
                                      provider_event_id=_id().replace("-", "") if _uses_google() else None)
            db.add(appointment)
            db.flush()
            _claim_blocks(db, appointment)
            operation = BookingOperation(id=_id(), workspace_id=workspace_id, session_id=session_id,
                                         proposal_id=proposal_id, appointment_id=appointment.id, kind="book",
                                         idempotency_key=idempotency_key,
                                         status="pending_provider" if _uses_google() else "committed",
                                         provider_request_id=appointment.provider_event_id,
                                         payload={"proposal_hash": proposal_hash, "version": version})
            db.add(operation)
            operation_id = operation.id
            proposal.status = "pending_provider" if _uses_google() else "confirmed"
            hold = db.scalar(select(SlotHold).where(SlotHold.proposal_id == proposal.id))
            if hold:
                hold.status = "pending_provider" if _uses_google() else "converted"
            if not _uses_google():
                voice_session.active_proposal_id = None
                voice_session.status = "booked"
                voice_session.last_reply = "Your appointment is confirmed. Keep the verification code to change it later."
                _event(db, voice_session, "booking_confirmed", {"appointment_id": appointment.id, "operation_id": operation.id})
            if get_settings().is_demo:
                db.add(DemoOutbox(id=_id(), workspace_id=workspace_id, appointment_id=appointment.id,
                                  recipient=customer.email, kind="booking_confirmation", body=f"Synthetic demo confirmation. Verification code: {code}"))
            if not _uses_google():
                return appointment.id, code
    except IntegrityError as exc:
        raise BookingError("slot_conflict", "The slot was just taken. Please choose an alternative.") from exc
    except OperationalError as exc:
        raise BookingError("slot_busy", "The slot is being booked; refresh availability and retry.") from exc
    return reconcile_google_booking(operation_id), code


def _token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().app_secret_key, salt="voicedesk-appointment-verify-v1")


def verify_appointment(db: Session, workspace_id: str, appointment_id: str, email: str, code: str) -> str:
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id))
    customer = db.get(Customer, appointment.customer_id) if appointment else None
    if not appointment or not customer or customer.email.lower() != email.lower() or not appointment.verification_hash:
        raise BookingError("verification_failed", "Booking details could not be verified.")
    if appointment.verification_hash.startswith("demo-hmac:"):
        if not get_settings().is_demo:
            raise BookingError("verification_failed", "Demo fixture verification is disabled in connected mode.")
        expected = hmac.new(get_settings().app_secret_key.encode(), f"fixture-code:{code}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(appointment.verification_hash.removeprefix("demo-hmac:"), expected):
            raise BookingError("verification_failed", "Booking details could not be verified.")
    else:
        try:
            _hasher.verify(appointment.verification_hash, code)
        except VerifyMismatchError as exc:
            raise BookingError("verification_failed", "Booking details could not be verified.") from exc
    return _token_serializer().dumps({"workspace_id": workspace_id, "appointment_id": appointment_id, "email": email.lower()})


def check_verification_token(token: str, workspace_id: str, appointment_id: str) -> None:
    try:
        data = _token_serializer().loads(token, max_age=600)
    except (BadSignature, SignatureExpired) as exc:
        raise BookingError("verification_expired", "Verify this booking again.") from exc
    if data.get("workspace_id") != workspace_id or data.get("appointment_id") != appointment_id:
        raise BookingError("verification_failed", "This verification token belongs to another booking.")


def cancel_appointment(workspace_id: str, appointment_id: str, idempotency_key: str) -> str:
    if _uses_google():
        return _begin_google_cancel(workspace_id, appointment_id, idempotency_key)
    try:
        with SessionLocal.begin() as db:
            prior = _operation_result(db, workspace_id, idempotency_key, "cancel")
            if prior:
                return prior.id
            appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id).with_for_update())
            if not appointment:
                raise BookingError("appointment_missing", "Booking not found.")
            if appointment.status == "cancelled":
                raise BookingError("already_cancelled", "This booking is already cancelled.")
            appointment.status = "cancelled"
            db.execute(delete(SlotClaim).where(SlotClaim.appointment_id == appointment.id))
            db.add(BookingOperation(id=_id(), workspace_id=workspace_id, session_id=appointment.source_session_id,
                                    appointment_id=appointment.id, kind="cancel", idempotency_key=idempotency_key, status="committed"))
            if get_settings().is_demo:
                customer = db.get(Customer, appointment.customer_id)
                db.add(DemoOutbox(id=_id(), workspace_id=workspace_id, appointment_id=appointment.id,
                                  recipient=customer.email, kind="cancellation", body="Synthetic demo cancellation confirmation."))
            return appointment.id
    except IntegrityError as exc:
        raise BookingError("operation_conflict", "This action is already being processed.") from exc


def reschedule_appointment(workspace_id: str, appointment_id: str, payload) -> str:
    if _uses_google():
        return _begin_google_reschedule(workspace_id, appointment_id, payload)
    start = validate_local_instant(payload.start_at, payload.timezone)
    if start <= utcnow():
        raise BookingError("slot_in_past", "Choose a future appointment time.")
    try:
        with SessionLocal.begin() as db:
            prior = _operation_result(db, workspace_id, payload.idempotency_key, "reschedule")
            if prior:
                return prior.id
            appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id).with_for_update())
            if not appointment or appointment.status != "confirmed":
                raise BookingError("appointment_missing", "An active booking was not found.")
            service_id = payload.service_id or appointment.service_id
            zone_id = payload.zone_id or appointment.zone_id
            service, _, staff = _calendar._resources(db, workspace_id, service_id, zone_id)
            end = start + timedelta(minutes=service.duration_minutes)
            staff_ids = [appointment.staff_id] + [resource.id for resource in staff if resource.id != appointment.staff_id]
            new_staff = next((staff_id for staff_id in staff_ids if _calendar.is_available(db, workspace_id, service_id, zone_id, staff_id, payload.start_at, payload.timezone, exclude_appointment_id=appointment.id)), None)
            if not new_staff:
                raise BookingError("slot_conflict", "The requested new slot is unavailable; your existing booking is unchanged.")
            db.scalar(select(StaffResource).where(StaffResource.id == new_staff).with_for_update())
            db.execute(delete(SlotClaim).where(SlotClaim.appointment_id == appointment.id))
            appointment.service_id = service_id
            appointment.zone_id = zone_id
            appointment.staff_id = new_staff
            appointment.start_at = start
            appointment.end_at = end
            _claim_blocks(db, appointment)
            db.add(BookingOperation(id=_id(), workspace_id=workspace_id, session_id=appointment.source_session_id,
                                    appointment_id=appointment.id, kind="reschedule", idempotency_key=payload.idempotency_key,
                                    status="committed"))
            if get_settings().is_demo:
                customer = db.get(Customer, appointment.customer_id)
                db.add(DemoOutbox(id=_id(), workspace_id=workspace_id, appointment_id=appointment.id,
                                  recipient=customer.email, kind="reschedule", body="Synthetic demo reschedule confirmation."))
            return appointment.id
    except IntegrityError as exc:
        raise BookingError("slot_conflict", "The requested new slot was just taken; your old booking is unchanged.") from exc


def _begin_google_cancel(workspace_id: str, appointment_id: str, idempotency_key: str) -> str:
    with SessionLocal.begin() as db:
        existing = db.scalar(select(BookingOperation).where(BookingOperation.workspace_id == workspace_id, BookingOperation.idempotency_key == idempotency_key))
        if existing:
            if existing.kind != "cancel" or existing.appointment_id != appointment_id:
                raise BookingError("idempotency_reused", "This key belongs to another action.")
            operation_id = existing.id
        else:
            appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id).with_for_update())
            if not appointment or appointment.status != "confirmed" or not appointment.provider_event_id:
                raise BookingError("appointment_missing", "An active connected booking was not found.")
            operation = BookingOperation(id=_id(), workspace_id=workspace_id, session_id=appointment.source_session_id,
                                         appointment_id=appointment.id, kind="cancel", idempotency_key=idempotency_key,
                                         status="pending_provider", provider_request_id=appointment.provider_event_id,
                                         payload={})
            db.add(operation)
            operation_id = operation.id
    return reconcile_google_change(operation_id)


def _begin_google_reschedule(workspace_id: str, appointment_id: str, payload) -> str:
    start = validate_local_instant(payload.start_at, payload.timezone)
    if start <= utcnow():
        raise BookingError("slot_in_past", "Choose a future appointment time.")
    try:
        with SessionLocal.begin() as db:
            existing = db.scalar(select(BookingOperation).where(BookingOperation.workspace_id == workspace_id, BookingOperation.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.kind != "reschedule" or existing.appointment_id != appointment_id:
                    raise BookingError("idempotency_reused", "This key belongs to another action.")
                operation_id = existing.id
            else:
                appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id).with_for_update())
                if not appointment or appointment.status != "confirmed" or not appointment.provider_event_id:
                    raise BookingError("appointment_missing", "An active connected booking was not found.")
                service_id = payload.service_id or appointment.service_id
                zone_id = payload.zone_id or appointment.zone_id
                service, _, staff = _calendar._resources(db, workspace_id, service_id, zone_id)
                end = start + timedelta(minutes=service.duration_minutes)
                staff_ids = [appointment.staff_id] + [resource.id for resource in staff if resource.id != appointment.staff_id]
                new_staff = next((staff_id for staff_id in staff_ids if _calendar.is_available(db, workspace_id, service_id, zone_id, staff_id, payload.start_at, payload.timezone, exclude_appointment_id=appointment.id)), None)
                if not new_staff:
                    raise BookingError("slot_conflict", "The new slot is unavailable; your old booking is unchanged.")
                old_blocks = set(blocks(stored_utc(appointment.start_at), stored_utc(appointment.end_at))) if new_staff == appointment.staff_id else set()
                held = []
                for block in blocks(start, end):
                    if block not in old_blocks:
                        claim = SlotClaim(id=_id(), workspace_id=workspace_id, staff_id=new_staff,
                                          appointment_id=appointment.id, block_start_at=block)
                        db.add(claim)
                        held.append(claim.id)
                db.flush()
                operation = BookingOperation(id=_id(), workspace_id=workspace_id, session_id=appointment.source_session_id,
                                             appointment_id=appointment.id, kind="reschedule",
                                             idempotency_key=payload.idempotency_key, status="pending_provider",
                                             provider_request_id=appointment.provider_event_id,
                                             payload={"service_id": service_id, "zone_id": zone_id, "staff_id": new_staff,
                                                      "start_at": start.isoformat(), "end_at": end.isoformat(),
                                                      "new_claim_ids": held})
                db.add(operation)
                operation_id = operation.id
    except IntegrityError as exc:
        raise BookingError("slot_conflict", "The new slot was just taken; your old booking is unchanged.") from exc
    return reconcile_google_change(operation_id)


def _google_event_owned(event: dict | None, event_id: str) -> bool:
    return bool(event and event.get("id") == event_id and
                event.get("extendedProperties", {}).get("private", {}).get("voicedesk_event_id") == event_id)


def _google_event_matches(event: dict | None, start: datetime, end: datetime, event_id: str | None = None) -> bool:
    if not event or not event.get("start", {}).get("dateTime") or not event.get("end", {}).get("dateTime"):
        return False
    if event.get("status") == "cancelled":
        return False
    if event_id and not _google_event_owned(event, event_id):
        return False
    actual_start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
    actual_end = datetime.fromisoformat(event["end"]["dateTime"].replace("Z", "+00:00"))
    return stored_utc(actual_start) == start and stored_utc(actual_end) == end


def reconcile_google_change(operation_id: str) -> str:
    """Resolve a pending cancellation/move; never drop the old local booking on uncertainty."""
    with SessionLocal() as db:
        operation = db.get(BookingOperation, operation_id)
        if not operation or operation.kind not in {"cancel", "reschedule"}:
            raise BookingError("operation_missing", "Change operation not found.")
        if operation.status == "committed":
            return operation.appointment_id
        if operation.status == "conflict":
            raise BookingError("provider_conflict", operation.failure_reason or "External calendar conflict.")
        appointment = db.get(Appointment, operation.appointment_id)
        if appointment.workspace_id != operation.workspace_id:
            raise BookingError("operation_missing", "Workspace mismatch.")
        kind, payload, event_id = operation.kind, operation.payload or {}, appointment.provider_event_id
        service = db.get(Service, payload["service_id"] if kind == "reschedule" else appointment.service_id)
    provider = GoogleCalendar()
    try:
        event = provider.get_event(event_id)
        if kind == "cancel":
            if event:
                if not _google_event_owned(event, event_id):
                    _set_provider_uncertain(operation_id, "Google event ownership marker did not match.")
                    raise BookingError("provider_conflict", "External event is not owned by this booking; cancellation needs operator review.")
                try:
                    provider.delete_event(event_id)
                except Exception:
                    if provider.get_event(event_id):
                        _set_provider_uncertain(operation_id, "Google cancellation outcome could not be established.")
                        raise BookingError("provider_uncertain", "Cancellation outcome is uncertain; the old local booking is retained pending reconciliation.") from None
                if provider.get_event(event_id):
                    _set_provider_uncertain(operation_id, "Google event still exists after cancellation request.")
                    raise BookingError("provider_uncertain", "Cancellation was not verified; the old local booking is retained pending reconciliation.")
        else:
            start = datetime.fromisoformat(payload["start_at"])
            end = datetime.fromisoformat(payload["end_at"])
            if not event:
                _set_provider_uncertain(operation_id, "Google event is missing during reschedule.")
                raise BookingError("provider_uncertain", "Calendar event is missing; the old local booking is retained pending review.")
            if not _google_event_owned(event, event_id):
                _set_provider_uncertain(operation_id, "Google event ownership marker did not match.")
                raise BookingError("provider_conflict", "External event is not owned by this booking; reschedule needs operator review.")
            if not _google_event_matches(event, start, end, event_id):
                if provider.conflicts_except(start, end, event_id):
                    _set_provider_uncertain(operation_id, "Google reports a conflict with another event.")
                    raise BookingError("provider_conflict", "External calendar conflict; old booking retained and new slot held pending review.")
                try:
                    provider.update_event(event_id, start, end, service.name)
                except Exception:
                    if not _google_event_matches(provider.get_event(event_id), start, end, event_id):
                        _set_provider_uncertain(operation_id, "Google reschedule outcome could not be established.")
                        raise BookingError("provider_uncertain", "Reschedule outcome is uncertain; the old local booking is retained pending reconciliation.") from None
                if not _google_event_matches(provider.get_event(event_id), start, end, event_id):
                    _set_provider_uncertain(operation_id, "Google event still has the old time after reschedule request.")
                    raise BookingError("provider_uncertain", "Reschedule was not verified; the old local booking is retained pending reconciliation.")
    except BookingError:
        raise
    except Exception as exc:
        _set_provider_uncertain(operation_id, "Google reconciliation failed.")
        raise CalendarError("Connected calendar is unavailable; old booking remains until reconciliation.") from exc
    with SessionLocal.begin() as db:
        operation = db.scalar(select(BookingOperation).where(BookingOperation.id == operation_id).with_for_update())
        appointment = db.scalar(select(Appointment).where(Appointment.id == operation.appointment_id).with_for_update())
        if operation.status == "committed":
            return appointment.id
        if kind == "cancel":
            appointment.status = "cancelled"
            db.execute(delete(SlotClaim).where(SlotClaim.appointment_id == appointment.id))
        else:
            held = set(payload["new_claim_ids"])
            old_claims = db.scalars(select(SlotClaim).where(SlotClaim.appointment_id == appointment.id)).all()
            for claim in old_claims:
                if claim.id not in held and not (claim.staff_id == payload["staff_id"] and
                                                  stored_utc(claim.block_start_at) in set(blocks(start, end))):
                    db.delete(claim)
            appointment.service_id = payload["service_id"]
            appointment.zone_id = payload["zone_id"]
            appointment.staff_id = payload["staff_id"]
            appointment.start_at = start
            appointment.end_at = end
        operation.status = "committed"
        operation.failure_reason = None
        if appointment.source_session_id:
            voice_session = db.get(VoiceSession, appointment.source_session_id)
            if voice_session:
                _event(db, voice_session, "booking_cancelled" if kind == "cancel" else "booking_rescheduled",
                       {"appointment_id": appointment.id, "operation_id": operation.id})
        return appointment.id
