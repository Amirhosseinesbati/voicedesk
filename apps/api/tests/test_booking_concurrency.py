"""Exercise the real API and SQLite uniqueness guard under concurrent confirmations."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import timezone as utc_timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest


def test_only_one_confirmation_claims_a_demo_slot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("DEMO_DATA_SIZE", "quick")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'business.db').as_posix()}")
    monkeypatch.chdir(tmp_path)

    from fastapi.testclient import TestClient
    from langgraph.checkpoint.sqlite import SqliteSaver
    from sqlalchemy import select

    import voicedesk.booking as booking
    from voicedesk.calendar import CalendarError, GoogleCalendar
    from voicedesk.config import get_settings
    from voicedesk.db import Base, SessionLocal, engine
    from voicedesk.domain import stored_utc
    from voicedesk.graphs import GraphRuntime
    from voicedesk.main import app
    from voicedesk.models import (
        Appointment,
        BookingOperation,
        SlotClaim,
        TranscriptTurn,
        User,
        VoiceSession,
        Workspace,
    )
    from voicedesk.purge_retention import purge_workspace
    from voicedesk.reset_demo import reset_demo
    from voicedesk.seed import seed

    get_settings.cache_clear()
    Base.metadata.create_all(bind=engine)
    seed()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            login = client.post(
                "/api/auth/login",
                json={"email": "operator@cedar.example.com", "password": "DemoVoiceDesk2026!"},
            )
            assert login.status_code == 200, login.text
            headers = {"X-CSRF-Token": login.json()["csrf_token"]}
            before = len(client.get("/api/appointments").json())
            timezone = "America/New_York"
            chosen = None
            for offset in range(2, 30):
                day = (datetime.now(ZoneInfo(timezone)).date() + timedelta(days=offset)).isoformat()
                response = client.get(
                    "/api/calendar/availability",
                    params={"service_id": "boiler-service", "zone_id": "central", "date": day, "timezone": timezone},
                )
                assert response.status_code == 200, response.text
                if response.json()["slots"]:
                    chosen = response.json()["slots"][0]
                    break
            assert chosen, "No open demo slot in the next 30 days"

            proposals = []
            for index in range(2):
                session = client.post(
                    "/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers
                )
                assert session.status_code == 200, session.text
                proposal = client.post(
                    f"/api/sessions/{session.json()['id']}/proposals",
                    headers=headers,
                    json={
                        "service_id": "boiler-service",
                        "zone_id": "central",
                        "start_at": chosen["start_at"],
                        "timezone": timezone,
                        "customer_name": f"Concurrent Customer {index}",
                        "customer_email": f"concurrent{index}@example.com",
                    },
                )
                assert proposal.status_code == 200, proposal.text
                proposals.append((session.json()["id"], proposal.json()["proposal"]))

            def confirm(item):
                session_id, proposal = item
                return client.post(
                    f"/api/sessions/{session_id}/proposals/{proposal['id']}/confirm",
                    headers=headers,
                    json={
                        "version": proposal["version"],
                        "hash": proposal["hash"],
                        "confirmed": True,
                        "idempotency_key": f"concurrency-{uuid4()}",
                    },
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(confirm, proposals))
            assert sorted(result.status_code for result in outcomes) == [200, 409], [
                (result.status_code, result.text) for result in outcomes
            ]
            assert len(client.get("/api/appointments").json()) == before + 1

            # A newly issued eight-hex booking reference must also work in the
            # conversation change flow. Verification and cancellation are two
            # separate finalized customer turns.
            confirmed = next(result.json()["appointment"] for result in outcomes if result.status_code == 200)
            assert len(confirmed["booking_reference"]) == 12
            change_session = client.post(
                "/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers
            )
            assert change_session.status_code == 200, change_session.text
            change_session_id = change_session.json()["id"]

            def change_turn(turn_id: str, message: str):
                return client.post(
                    f"/api/sessions/{change_session_id}/turns", headers=headers,
                    json={"turn_id": turn_id, "text": message, "source": "text"},
                )

            owner_email = "concurrent0@example.com" if confirmed["customer_name"].endswith("0") else "concurrent1@example.com"
            initial_change = change_turn(
                "cancel-request", f"Please cancel booking {confirmed['booking_reference']}. My email is {owner_email}."
            )
            assert initial_change.status_code == 200, initial_change.text
            assert "separate verification turn" in initial_change.json()["reply_text"]
            with SessionLocal() as db:
                assert db.get(Appointment, confirmed["id"]).status == "confirmed"
            verify_change = change_turn("cancel-verify", "I verify this is my booking.")
            assert verify_change.status_code == 200, verify_change.text
            assert "explicitly confirm cancellation" in verify_change.json()["reply_text"]
            with SessionLocal() as db:
                assert db.get(Appointment, confirmed["id"]).status == "confirmed"
            final_change = change_turn("cancel-confirm", "Yes, confirm cancellation.")
            assert final_change.status_code == 200, final_change.text
            assert "is cancelled" in final_change.json()["reply_text"]
            with SessionLocal() as db:
                assert db.get(Appointment, confirmed["id"]).status == "cancelled"

            # Simulate an external create timeout, then reconcile the same stable
            # event ID. A mismatched remote time must never confirm the booking.
            another_slot = None
            for offset in range(2, 30):
                day = (datetime.now(ZoneInfo(timezone)).date() + timedelta(days=offset)).isoformat()
                availability = client.get(
                    "/api/calendar/availability",
                    params={"service_id": "boiler-service", "zone_id": "central", "date": day, "timezone": timezone},
                )
                for candidate in availability.json()["slots"]:
                    if candidate["start_at"] != chosen["start_at"]:
                        another_slot = candidate
                        break
                if another_slot:
                    break
            assert another_slot
            session = client.post("/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers).json()
            pending_proposal = client.post(
                f"/api/sessions/{session['id']}/proposals",
                headers=headers,
                json={
                    "service_id": "boiler-service", "zone_id": "central",
                    "start_at": another_slot["start_at"], "timezone": timezone,
                    "customer_name": "Provider Timeout Example",
                    "customer_email": "provider-timeout@example.com",
                },
            )
            assert pending_proposal.status_code == 200, pending_proposal.text
            pending_proposal = pending_proposal.json()["proposal"]

            class TimeoutCalendar:
                remote_event = None

                def get_event(self, _event_id):
                    return self.remote_event

                def busy(self, _start, _end):
                    return False

                def create_event(self, _event_id, _start, _end, _summary):
                    raise TimeoutError("simulated ambiguous provider write")

            provider = TimeoutCalendar()
            monkeypatch.setattr(booking, "GoogleCalendar", lambda: provider)
            monkeypatch.setattr(booking, "_uses_google", lambda: True)
            key = f"provider-{uuid4()}"
            with pytest.raises(booking.BookingError, match="uncertain"):
                booking.confirm_proposal(
                    "cedar-demo", session["id"], pending_proposal["id"],
                    pending_proposal["version"], pending_proposal["hash"], key,
                )
            with SessionLocal() as db:
                operation = db.scalar(select(BookingOperation).where(BookingOperation.idempotency_key == key))
                assert operation and operation.status == "uncertain"
                pending_booking = db.get(Appointment, operation.appointment_id)
                assert pending_booking and pending_booking.status == "pending_provider"
                assert db.scalars(select(SlotClaim).where(SlotClaim.appointment_id == pending_booking.id)).first()
                event_id = pending_booking.provider_event_id
                start = stored_utc(pending_booking.start_at).isoformat()
                end = stored_utc(pending_booking.end_at).isoformat()
                operation_id = operation.id
            provider.remote_event = {
                "id": event_id,
                "extendedProperties": {"private": {"voicedesk_event_id": event_id}},
                "start": {"dateTime": "2030-01-01T00:00:00+00:00"},
                "end": {"dateTime": "2030-01-01T01:00:00+00:00"},
            }
            with pytest.raises(booking.BookingError, match="could not be verified"):
                booking.reconcile_google_booking(operation_id)
            provider.remote_event = {
                "id": event_id, "start": {"dateTime": start}, "end": {"dateTime": end}
            }
            with pytest.raises(booking.BookingError, match="could not be verified"):
                booking.reconcile_google_booking(operation_id)
            provider.remote_event = {
                "id": event_id, "start": {"dateTime": start}, "end": {"dateTime": end},
                "extendedProperties": {"private": {"voicedesk_event_id": event_id}},
            }
            assert booking.reconcile_google_booking(operation_id) == pending_booking.id
            with SessionLocal() as db:
                assert db.get(BookingOperation, operation_id).status == "committed"
                assert db.get(Appointment, pending_booking.id).status == "confirmed"
        with SessionLocal.begin() as db:
            db.add(Workspace(id="unrelated-workspace", name="Must survive demo reset"))
        monkeypatch.setenv("APP_MODE", "connected")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="disabled"):
            reset_demo()
        monkeypatch.setenv("APP_MODE", "demo")
        get_settings.cache_clear()
        reset_demo()
        with SessionLocal() as db:
            assert db.get(Workspace, "unrelated-workspace") is not None
            assert db.get(Workspace, "cedar-demo") is not None
        old = datetime.now(utc_timezone.utc) - timedelta(days=120)
        old_session_id = str(uuid4())
        with SessionLocal.begin() as db:
            operator = db.scalar(select(User).where(User.email == "operator@cedar.example.com"))
            db.add(VoiceSession(
                id=old_session_id, workspace_id="cedar-demo", created_by_user_id=operator.id,
                mode="demo", channel="text", status="closed", stable_slots={"customer_email": "old@example.com"},
                tentative_slots={}, last_reply="old conversation", created_at=old, updated_at=old,
            ))
            db.flush()
            db.add(TranscriptTurn(
                id=str(uuid4()), workspace_id="cedar-demo", session_id=old_session_id,
                turn_id="old-turn", speaker="user", text="old private transcript",
                source="text", created_at=old,
            ))
        thread_id = f"semantic:cedar-demo:{old_session_id}"
        checkpoint_path = tmp_path / "voicedesk-checkpoints.sqlite"
        checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        try:
            GraphRuntime(SqliteSaver(checkpoint_connection)).interpret({
                "workspace_id": "cedar-demo", "session_id": old_session_id,
                "turn_id": "old-turn", "text": "old private transcript", "mode": "demo",
                "stable_slots": {}, "timezone": "America/New_York",
            })
            assert any(item.config["configurable"]["thread_id"] == thread_id
                       for item in SqliteSaver(checkpoint_connection).list(None))
        finally:
            checkpoint_connection.close()
        purged = purge_workspace("cedar-demo")
        assert purged["turns"] >= 1
        assert purged["sessions_scrubbed"] >= 1
        assert purged["checkpoint_threads_purged"] >= 1
        checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        try:
            assert not any(item.config["configurable"]["thread_id"] == thread_id
                           for item in SqliteSaver(checkpoint_connection).list(None))
        finally:
            checkpoint_connection.close()
        with SessionLocal() as db:
            assert db.scalar(select(TranscriptTurn).where(TranscriptTurn.session_id == old_session_id)) is None
            assert db.get(VoiceSession, old_session_id).stable_slots == {}
            assert db.get(Workspace, "unrelated-workspace") is not None

        monkeypatch.setenv("GOOGLE_CALENDAR_ID", "invalid-test-calendar")
        monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{malformed-secret")
        get_settings.cache_clear()
        with pytest.raises(CalendarError, match="setup failed"):
            GoogleCalendar().busy(old, old + timedelta(hours=1))
    finally:
        engine.dispose()
