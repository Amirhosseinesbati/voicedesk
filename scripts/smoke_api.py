"""Run a disposable full-data API journey without Docker or external providers."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


def expect(response, status: int = 200):
    if response.status_code != status:
        raise AssertionError(f"Expected HTTP {status}; got {response.status_code}: {response.text[:1000]}")
    return response.json()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="voicedesk-smoke-", ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        os.environ["APP_MODE"] = "demo"
        os.environ["DATABASE_URL"] = f"sqlite:///{(temp / 'business.db').as_posix()}"
        os.environ["DEMO_DATA_SIZE"] = "full"
        os.chdir(temp)

        from fastapi.testclient import TestClient

        from voicedesk.db import Base, engine
        from voicedesk.main import app
        from voicedesk.seed import seed

        Base.metadata.create_all(bind=engine)
        counts = seed()
        assert counts == {"services": 8, "staff": 6, "zones": 3, "customers": 400, "appointments": 600}, counts

        with TestClient(app, raise_server_exceptions=True) as client:
            auth = expect(client.post("/api/auth/login", json={
                "email": "operator@cedar.example.com", "password": "DemoVoiceDesk2026!",
            }))
            headers = {"X-CSRF-Token": auth["csrf_token"]}
            catalog = expect(client.get("/api/catalog"))
            assert len(catalog["services"]) == 8
            before = expect(client.get("/api/appointments"))
            assert len(before) == 600
            session = expect(client.post("/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers))

            timezone = "America/New_York"
            today = datetime.now(ZoneInfo(timezone)).date()
            options = []
            for offset in range(2, 24):
                requested_date = (today + timedelta(days=offset)).isoformat()
                availability = expect(client.get("/api/calendar/availability", params={
                    "service_id": "boiler-service", "zone_id": "central",
                    "date": requested_date, "timezone": timezone,
                }))
                options = availability["slots"]
                if len(options) >= 2:
                    break
            assert len(options) >= 2, "No two boiler-service slots were available in the next 24 days"

            proposal_input = {
                "service_id": "boiler-service", "zone_id": "central",
                "start_at": options[0]["start_at"], "timezone": timezone,
                "customer_name": "Avery Example", "customer_email": "avery@example.com",
                "customer_phone": "+1-555-0100",
            }
            first = expect(client.post(f"/api/sessions/{session['id']}/proposals", json=proposal_input, headers=headers))["proposal"]
            assert len(expect(client.get("/api/appointments"))) == 600, "A proposal created an appointment before confirmation"

            expect(client.post(f"/api/sessions/{session['id']}/turns", json={
                "turn_id": str(uuid4()), "text": "Actually, change the day before I confirm.", "source": "text",
            }, headers=headers))
            stale = client.post(f"/api/sessions/{session['id']}/proposals/{first['id']}/confirm", json={
                "version": first["version"], "hash": first["hash"], "confirmed": True,
                "idempotency_key": f"stale-{uuid4()}",
            }, headers=headers)
            assert stale.status_code == 409, f"Superseded proposal unexpectedly confirmed: {stale.status_code} {stale.text}"
            assert len(expect(client.get("/api/appointments"))) == 600

            proposal_input["start_at"] = options[1]["start_at"]
            current = expect(client.post(f"/api/sessions/{session['id']}/proposals", json=proposal_input, headers=headers))["proposal"]
            confirmation = {
                "version": current["version"], "hash": current["hash"], "confirmed": True,
                "idempotency_key": f"book-{uuid4()}",
            }
            booked = expect(client.post(f"/api/sessions/{session['id']}/proposals/{current['id']}/confirm", json=confirmation, headers=headers))
            appointment_id = booked["appointment"]["id"]
            assert booked["verification_code"], "Demo confirmation did not return a local verification code"
            assert len(expect(client.get("/api/appointments"))) == 601

            duplicate = client.post(f"/api/sessions/{session['id']}/proposals/{current['id']}/confirm", json=confirmation, headers=headers)
            assert duplicate.status_code == 200, f"Idempotent retry failed: {duplicate.status_code} {duplicate.text}"
            assert duplicate.json()["appointment"]["id"] == appointment_id
            assert len(expect(client.get("/api/appointments"))) == 601, "Duplicate confirmation created another appointment"

            verified = expect(client.post(f"/api/appointments/{appointment_id}/verify", json={
                "email": "avery@example.com", "verification_code": booked["verification_code"],
            }, headers=headers))
            cancelled = expect(client.post(f"/api/appointments/{appointment_id}/cancel", json={
                "verification_token": verified["token"], "idempotency_key": f"cancel-{uuid4()}",
            }, headers=headers))
            assert cancelled["appointment"]["status"] == "cancelled"

            harbor = expect(client.post("/api/auth/login", json={
                "email": "operator@harbor.example.com", "password": "DemoVoiceDesk2026!",
            }))
            assert harbor["user"]["workspace_id"] == "harbor-demo"
            assert client.get(f"/api/sessions/{session['id']}").status_code == 404
        engine.dispose()
        print("PASS: full seed, auth, availability, no early booking, stale rejection, idempotency, cancellation, workspace isolation")


if __name__ == "__main__":
    main()

