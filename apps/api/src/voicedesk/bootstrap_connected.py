"""Opt-in connected pilot onboarding without synthetic callers or demo credentials."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from voicedesk.auth import hash_password
from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import BusinessHours, Service, ServiceZone, StaffResource, User, Workspace
from voicedesk.schemas import LoginInput

CONNECTED_WORKSPACE_ID = "cedar-connected"


def bootstrap_connected(email: str, password: str, catalog_path: Path | None = None) -> dict:
    settings = get_settings()
    if settings.is_demo or settings.app_mode != "connected":
        raise RuntimeError("Connected onboarding requires APP_MODE=connected.")
    if settings.app_secret_key == "local-demo-only-change-before-deployment":
        raise RuntimeError("Set a distinct APP_SECRET_KEY before connected onboarding.")
    if len(password) < 12 or password == "DemoVoiceDesk2026!":
        raise ValueError("Choose a unique password of at least 12 characters; demo credentials are refused.")
    email = str(LoginInput(email=email, password=password).email)
    source = catalog_path or settings.api_root / "fixtures" / "sample" / "cedar_quick.json"
    if not source.is_file():
        raise FileNotFoundError(f"Connected pilot catalog is missing: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    services, zones, staff = data["services"], data["zones"], data["staff"]
    if not services or not zones or not staff:
        raise ValueError("Connected pilot catalog requires services, zones, and staff.")
    hours = data.get("business_hours", {})
    if isinstance(hours, dict):
        hours = [{"weekday": day, **interval} for day, intervals in hours.items() for interval in intervals]

    with SessionLocal.begin() as db:
        if db.get(Workspace, CONNECTED_WORKSPACE_ID):
            raise RuntimeError("Connected pilot workspace already exists; onboarding never overwrites it.")
        if db.scalar(select(Workspace).where(Workspace.id.in_(("cedar-demo", "harbor-demo")))):
            raise RuntimeError("This database contains DEMO workspaces; use a fresh connected database.")
        if db.scalar(select(User).where(User.email == email)):
            raise RuntimeError("An account with this email already exists.")
        db.add(Workspace(id=CONNECTED_WORKSPACE_ID,
                         name="Cedar Home Services — fictional connected pilot",
                         business_timezone=data.get("metadata", {}).get("timezone", "America/New_York")))
        db.flush()
        for item in services:
            db.add(Service(
                id=item["id"], workspace_id=CONNECTED_WORKSPACE_ID, name=item["name"],
                description=item.get("description", ""), duration_minutes=item["duration_minutes"],
                price_from_cents=item["price_from_cents"],
                policy_source=item.get("policy_source", f"kb:{item['id']}"),
                eligible_zone_ids=item.get("eligible_zone_ids", [zone["id"] for zone in zones]),
            ))
        for item in zones:
            db.add(ServiceZone(id=item["id"], workspace_id=CONNECTED_WORKSPACE_ID,
                               name=item["name"], postal_prefixes=item.get("postal_prefixes", [])))
        for item in staff:
            db.add(StaffResource(
                id=item["id"], workspace_id=CONNECTED_WORKSPACE_ID,
                name=item["name"], service_ids=item["service_ids"],
                zone_ids=item["zone_ids"], weekly_hours=item["weekly_hours"],
            ))
        db.flush()
        for index, item in enumerate(hours):
            db.add(BusinessHours(
                id=f"connected-hours-{index}", workspace_id=CONNECTED_WORKSPACE_ID,
                weekday=item["weekday"], start_local=item.get("start", item.get("start_local")),
                end_local=item.get("end", item.get("end_local")),
            ))
        db.add(User(id=str(uuid4()), workspace_id=CONNECTED_WORKSPACE_ID,
                    email=email, role="admin", password_hash=hash_password(password)))
    return {"workspace_id": CONNECTED_WORKSPACE_ID, "admin_email": email,
            "services": len(services), "zones": len(zones), "staff": len(staff),
            "customers": 0, "appointments": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a fictional Cedar connected pilot catalog and first admin.")
    parser.add_argument("--email", default=os.environ.get("VOICEDESK_BOOTSTRAP_EMAIL"),
                        help="Admin email (or set VOICEDESK_BOOTSTRAP_EMAIL).")
    parser.add_argument("--catalog", type=Path, help="Optional Cedar catalog JSON path.")
    args = parser.parse_args()
    if not args.email:
        parser.error("Provide --email or VOICEDESK_BOOTSTRAP_EMAIL.")
    password = os.environ.get("VOICEDESK_BOOTSTRAP_PASSWORD")
    if not password:
        if not sys.stdin.isatty():
            parser.error("Set VOICEDESK_BOOTSTRAP_PASSWORD in a noninteractive terminal.")
        password = getpass.getpass("New connected admin password: ")
    try:
        result = bootstrap_connected(args.email, password, args.catalog)
    except Exception as exc:
        parser.exit(1, f"Connected onboarding failed: {exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
