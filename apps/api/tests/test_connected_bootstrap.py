"""Boot a fresh CONNECTED database without creating demo caller data or accounts."""

import os
import subprocess
import sys


def test_connected_bootstrap_login_catalog_and_policy(tmp_path) -> None:
    environment = os.environ.copy()
    environment.update({
        "APP_MODE": "connected",
        "APP_SECRET_KEY": "connected-bootstrap-test-secret-2026",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'connected.db').as_posix()}",
        "CALENDAR_PROVIDER": "local",
        "OPENAI_API_KEY": "",
    })
    script = '''
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select
from voicedesk.bootstrap_connected import bootstrap_connected
from voicedesk.db import Base, SessionLocal, engine
from voicedesk.main import app
from voicedesk.models import Appointment, Customer, User

Base.metadata.create_all(bind=engine)
original_read_text = Path.read_text
def without_generated_data(path, *args, **kwargs):
    if path.name == "cedar_full.json":
        raise FileNotFoundError("generated full data is absent in the fresh image")
    return original_read_text(path, *args, **kwargs)
with patch.object(Path, "read_text", without_generated_data):
    summary = bootstrap_connected("admin@cedar.example.com", "UniqueConnectedPassword2026!")
assert summary["workspace_id"] == "cedar-connected"
assert summary["customers"] == summary["appointments"] == 0
with SessionLocal() as db:
    assert not db.scalars(select(Customer)).first()
    assert not db.scalars(select(Appointment)).first()
    assert [user.email for user in db.scalars(select(User))] == ["admin@cedar.example.com"]
with TestClient(app) as client:
    login = client.post("/api/auth/login", json={"email": "admin@cedar.example.com", "password": "UniqueConnectedPassword2026!"})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["workspace_id"] == "cedar-connected"
    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200, catalog.text
    assert len(catalog.json()["services"]) == 8
    assert len(catalog.json()["zones"]) == 3
    assert len(catalog.json()["staff"]) == 6
    policy = client.get("/api/knowledge")
    assert policy.status_code == 200, policy.text
    assert policy.json()["articles"]
    assert policy.json()["synthetic"] is True
    assert client.get("/api/appointments").json() == []
engine.dispose()
'''
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
