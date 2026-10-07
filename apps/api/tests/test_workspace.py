"""Configuration affects real local capacity and stays inside the admin's workspace."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def workspace_client():
    # Keep application imports lazy: the existing concurrency suite configures
    # its disposable database before importing the composition root.
    from voicedesk.auth import hash_password
    from voicedesk.db import Base, get_db
    from voicedesk.main import app
    from voicedesk.models import BusinessHours, Service, StaffResource, User, Workspace

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    password_hash = hash_password("TestWorkspacePassword2026!")
    with Session(engine) as db:
        for workspace_id in ("test-a", "test-b"):
            db.add(Workspace(id=workspace_id, name=workspace_id, business_timezone="America/New_York"))
            db.add(Service(id=f"{workspace_id}-service", workspace_id=workspace_id, name="Consultation",
                           description="A service", duration_minutes=60, price_from_cents=10000, active=True))
            db.add(StaffResource(id=f"{workspace_id}-staff", workspace_id=workspace_id, name="Alex",
                                 service_ids=[f"{workspace_id}-service"], zone_ids=[f"{workspace_id}-zone"],
                                 weekly_hours={"monday": [{"start": "09:00", "end": "17:00"}]}))
            db.add(BusinessHours(id=f"{workspace_id}-hours", workspace_id=workspace_id, weekday="monday", start_local="09:00", end_local="17:00"))
            for role in ("admin", "operator", "viewer"):
                db.add(User(id=f"{workspace_id}-{role}", workspace_id=workspace_id,
                            email=f"{role}@{workspace_id}.example", role=role, active=True, password_hash=password_hash))
        from voicedesk.models import ServiceZone
        for workspace_id in ("test-a", "test-b"):
            db.add(ServiceZone(id=f"{workspace_id}-zone", workspace_id=workspace_id, name="Central", postal_prefixes=[]))
        db.commit()

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    yield client, engine
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def sign_in(client, role="admin"):
    response = client.post("/api/auth/login", json={"email": f"{role}@test-a.example", "password": "TestWorkspacePassword2026!"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_configuration_validation(workspace_client):
    from voicedesk.workspace import WorkspaceInput

    client, _ = workspace_client
    sign_in(client)
    config = client.get("/api/workspace").json()
    config.pop("id")
    config.pop("policy_review_required")
    for patch in ({"timezone": "Invalid/Zone"}, {"name": "   "}, {"hours": config["hours"][:6]}):
        with pytest.raises(ValidationError):
            WorkspaceInput.model_validate({**config, **patch})
    config["hours"][0].update(start="17:00", end="09:00")
    with pytest.raises(ValidationError):
        WorkspaceInput.model_validate(config)


def test_workspace_put_is_allowed_by_configured_cors_preflight(workspace_client):
    from voicedesk.config import get_settings

    client, _ = workspace_client
    origin = get_settings().cors_origins.split(",")[0].strip()
    response = client.options("/api/workspace", headers={
        "Origin": origin, "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "X-CSRF-Token",
    })
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_workspace_migration_preserves_legacy_rows_and_is_safe_for_fresh_metadata():
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[1] / "migrations" / "versions" / "20261006_0002_workspace_presentation.py"
    spec = importlib.util.spec_from_file_location("workspace_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, business_timezone TEXT)")
        connection.exec_driver_sql("INSERT INTO workspaces VALUES ('legacy', 'Original client', 'UTC')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # Fresh initial metadata may already include it.
        row = connection.exec_driver_sql("SELECT name, presentation FROM workspaces").one()
        assert row == ("Original client", "{}")
    engine.dispose()


def test_admin_csrf_scope_and_persisted_configuration(workspace_client):
    from voicedesk.models import BusinessHours, Service, Workspace

    client, engine = workspace_client
    headers = sign_in(client)
    original = client.get("/api/workspace").json()
    config = {key: value for key, value in original.items() if key not in {"id", "policy_review_required"}}
    assert client.put("/api/workspace", json=config).status_code == 403
    config.update(name="North Studio", timezone="Europe/London", theme="ocean", tagline="A better welcome.")
    config["services"][0].update(name="First consultation", duration_minutes=90)
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 200
    assert client.get("/api/workspace").json()["name"] == "North Studio"
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 409
    assert client.get("/api/catalog").json()["services"][0]["duration_minutes"] == 90
    with Session(engine) as db:
        assert db.get(Workspace, "test-b").name == "test-b"
        assert db.get(Service, "test-b-service").duration_minutes == 60
        assert len(db.scalars(select(BusinessHours).where(BusinessHours.workspace_id == "test-a")).all()) == 7
    config["services"][0]["id"] = "test-b-service"
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 400
    for role in ("operator", "viewer"):
        headers = sign_in(client, role)
        assert client.get("/api/workspace").status_code == 200
        assert client.put("/api/workspace", json={key: value for key, value in original.items() if key not in {"id", "policy_review_required"}}, headers=headers).status_code == 403


def test_closed_days_and_duration_control_capacity(workspace_client):
    from voicedesk.calendar import LocalCalendar

    client, engine = workspace_client
    headers = sign_in(client)
    config = client.get("/api/workspace").json()
    config.pop("id")
    config.pop("policy_review_required")
    config["hours"][0].update(start="10:00", end="12:00")
    config["services"][0]["duration_minutes"] = 90
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 200
    with Session(engine) as db:
        slots = LocalCalendar().slots(db, "test-a", "test-a-service", "test-a-zone", date(2026, 10, 12), "America/New_York")
        assert [slot["start_at"].hour for slot in slots] == [14, 14]
        assert len(slots) == 2  # 10:00 and 10:30, each fits 90 minutes.
    config["hours"][0]["closed"] = True
    config["revision"] = client.get("/api/workspace").json()["revision"]
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 200
    with Session(engine) as db:
        assert LocalCalendar().slots(db, "test-a", "test-a-service", "test-a-zone", date(2026, 10, 12), "America/New_York") == []


def test_changed_configuration_invalidates_pending_reviews_and_sets_session_zone(workspace_client):
    from voicedesk.models import Proposal, SlotHold, VoiceSession

    client, engine = workspace_client
    headers = sign_in(client)
    created = client.post("/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers)
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]
    start = datetime(2026, 10, 12, 14, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add(Proposal(id="pending-review", workspace_id="test-a", session_id=session_id,
                        version=1, proposal_hash="a" * 64, service_id="test-a-service", zone_id="test-a-zone",
                        staff_id="test-a-staff", customer_name="Test Customer", customer_email="customer@example.com",
                        start_at=start, end_at=start + timedelta(hours=1), timezone="America/New_York",
                        status="pending", expires_at=start + timedelta(days=1)))
        db.add(SlotHold(id="pending-hold", workspace_id="test-a", proposal_id="pending-review", staff_id="test-a-staff",
                       start_at=start, end_at=start + timedelta(hours=1), expires_at=start + timedelta(days=1), status="pending"))
        db.commit()
    config = client.get("/api/workspace").json()
    config.pop("id")
    config.pop("policy_review_required")
    config["timezone"] = "Europe/London"
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 200
    with Session(engine) as db:
        assert db.get(Proposal, "pending-review").status == "invalidated"
        assert db.get(SlotHold, "pending-hold").status == "invalidated"
        assert db.get(VoiceSession, session_id).timezone == "America/New_York"
    new_session = client.post("/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers)
    assert new_session.json()["timezone"] == "Europe/London"


def test_demo_startup_seed_preserves_customized_configuration(workspace_client, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from voicedesk import seed as seed_module
    from voicedesk.models import BusinessHours, Service, Workspace

    client, engine = workspace_client
    headers = sign_in(client)
    config = client.get("/api/workspace").json()
    config.pop("id")
    config.pop("policy_review_required")
    config["name"] = "Custom client"
    config["services"][0].update(name="Custom consultation", duration_minutes=90)
    config["hours"][0]["closed"] = True
    assert client.put("/api/workspace", json=config, headers=headers).status_code == 200
    monkeypatch.setattr(seed_module, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(seed_module, "load_dataset", lambda: {
        "workspaces": [{"id": "test-a", "name": "Original seed name"}],
        "services": [{"id": "test-a-service", "workspace_id": "test-a", "name": "Original service", "duration_minutes": 60, "price_from_cents": 10000}],
        "zones": [], "staff": [], "customers": [], "appointments": [],
        "business_hours": [{"workspace_id": "test-a", "weekday": "monday", "start": "09:00", "end": "17:00"}],
    })
    seed_module.seed()
    seed_module.seed()
    with Session(engine) as db:
        assert db.get(Workspace, "test-a").name == "Custom client"
        assert db.get(Service, "test-a-service").duration_minutes == 90
        hours = db.scalars(select(BusinessHours).where(BusinessHours.workspace_id == "test-a")).all()
        assert len(hours) == 7
        assert next(item for item in hours if item.weekday == "monday").start_local == "00:00"


def test_local_responses_use_client_catalogue_and_do_not_repeat_unreviewed_policies(workspace_client, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from voicedesk import db as database_module
    from voicedesk import graphs
    from voicedesk.knowledge import scoped_articles
    from voicedesk.models import Service, Workspace

    client, engine = workspace_client
    headers = sign_in(client)
    config = client.get("/api/workspace").json()
    config.pop("id")
    config.pop("policy_review_required")
    config["name"] = "North Studio"
    config["services"][0]["name"] = "First consultation"
    saved = client.put("/api/workspace", json=config, headers=headers)
    assert saved.json()["policy_review_required"] is True
    local_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(graphs, "SessionLocal", local_sessions)
    monkeypatch.setattr(database_module, "SessionLocal", local_sessions)
    with Session(engine) as db:
        db.add(Service(id="disabled-service", workspace_id="test-a", name="Hidden consultation", description="",
                       duration_minutes=60, price_from_cents=10000, active=False))
        db.add(Workspace(id="cedar-demo", name="Changed demo", presentation={"policy_review_required": True}))
        db.commit()
    result = graphs.build_semantic_graph(checkpointer=None).invoke({
        "workspace_id": "test-a", "session_id": "local-brand", "turn_id": "greeting", "text": "Hello",
        "mode": "demo", "stable_slots": {}, "timezone": "Europe/London", "observable_events": [],
    })
    assert "North Studio" in result["reply_text"]
    assert "First consultation" in result["reply_text"]
    assert "Hidden consultation" not in result["reply_text"]
    assert result["stable_slots"]["timezone"] == "Europe/London"
    assert graphs._demo_extract("I need Hidden consultation", "test-a").service_id is None
    assert scoped_articles("cedar-demo") == []


def test_transcript_orders_customer_before_reply_when_legacy_timestamps_match(workspace_client):
    from voicedesk.models import TranscriptTurn, VoiceSession
    from voicedesk.views import session_view

    _, engine = workspace_client
    instant = datetime(2026, 10, 6, 14, tzinfo=timezone.utc)
    with Session(engine) as db:
        session = VoiceSession(id="timestamp-order", workspace_id="test-a", created_by_user_id="test-a-admin",
                               mode="demo", channel="text", status="active", stable_slots={}, tentative_slots={})
        db.add(session)
        for speaker, text in (("assistant", "A reply"), ("user", "A request")):
            db.add(TranscriptTurn(id=f"legacy-{speaker}", workspace_id="test-a", session_id=session.id,
                                  turn_id="same-turn", speaker=speaker, text=text, source="text", created_at=instant))
        db.commit()
        assert [turn.speaker for turn in session_view(db, session).turns] == ["user", "assistant"]
