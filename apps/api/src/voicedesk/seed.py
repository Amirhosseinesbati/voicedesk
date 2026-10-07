"""Idempotent synthetic demo seed. Never run against a connected installation."""

import hashlib
import hmac
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from voicedesk.auth import hash_password
from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import (
    Appointment,
    Blackout,
    BusinessHours,
    Customer,
    Service,
    ServiceZone,
    StaffResource,
    User,
    Workspace,
)


def parse_instant(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("Seed dates must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def demo_fixture_code(appointment_id: str) -> str:
    """Deterministic demo-only verification for synthetic historical records."""
    digest = hmac.new(get_settings().app_secret_key.encode(), appointment_id.encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


def demo_fixture_hash(appointment_id: str) -> str:
    code = demo_fixture_code(appointment_id)
    digest = hmac.new(get_settings().app_secret_key.encode(), f"fixture-code:{code}".encode(), hashlib.sha256).hexdigest()
    return f"demo-hmac:{digest}"


def _fallback_dataset() -> dict:
    services = [
        ("boiler-service", "Boiler service", 60, 12000),
        ("plumbing-repair", "Plumbing repair", 60, 9500),
        ("electrical-repair", "Electrical repair", 60, 10500),
        ("heating-check", "Heating check", 45, 8500),
        ("drain-clearing", "Drain clearing", 75, 13500),
        ("ac-repair", "Air conditioning repair", 90, 14500),
        ("water-heater", "Water heater service", 90, 15500),
        ("home-inspection", "Home maintenance inspection", 60, 11500),
    ]
    zones = [("north", "North Zone"), ("central", "Central Zone"), ("south", "South Zone")]
    hours = {day: [{"start": "08:00", "end": "17:00"}] for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]}
    return {
        "workspaces": [{"id": "cedar-demo", "name": "Cedar Home Services — Synthetic demo"}, {"id": "harbor-demo", "name": "Harbor Test — Synthetic isolation"}],
        "services": [{"id": key, "workspace_id": "cedar-demo", "name": name, "description": f"Cedar provides {name.lower()} in serviced zones.", "duration_minutes": duration, "price_from_cents": price, "policy_source": f"kb:{key}"} for key, name, duration, price in services],
        "zones": [{"id": key, "workspace_id": "cedar-demo", "name": name, "postal_prefixes": []} for key, name in zones],
        "staff": [{"id": f"staff-{number}", "workspace_id": "cedar-demo", "name": f"Cedar Technician {number}", "service_ids": [x[0] for x in services], "zone_ids": [x[0] for x in zones], "weekly_hours": hours} for number in range(1, 7)],
        "business_hours": [{"weekday": day, "start": "08:00", "end": "17:00"} for day in hours],
        "blackouts": [], "customers": [], "appointments": [],
    }


def load_dataset() -> dict:
    settings = get_settings()
    if settings.demo_data_path:
        return json.loads(Path(settings.demo_data_path).read_text(encoding="utf-8"))
    generator = settings.api_root / "scripts" / "generate_demo_data.py"
    if generator.exists():
        spec = importlib.util.spec_from_file_location("voicedesk_demo_generator", generator)
        if not spec or not spec.loader:
            raise RuntimeError("Cannot load demo data generator")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_dataset(seed=settings.demo_seed, reference_date=settings.demo_reference_date, size=settings.demo_data_size)
    if settings.demo_data_size == "full":
        raise FileNotFoundError(f"Full demo data generator is missing: {generator}. Copy scripts/ into the container or set DEMO_DATA_PATH.")
    return _fallback_dataset()


def seed() -> dict[str, int]:
    settings = get_settings()
    if not settings.is_demo:
        return {"skipped_connected_mode": 1}
    data = load_dataset()
    counts: dict[str, int] = {}
    with SessionLocal.begin() as db:
        customized = {workspace.id for workspace in db.scalars(select(Workspace))
                      if (workspace.presentation or {}).get("revision", 0) > 0}
        for item in data["workspaces"]:
            if item["id"] in customized:
                continue
            db.merge(Workspace(id=item["id"], name=item["name"], business_timezone=item.get("business_timezone", data.get("metadata", {}).get("timezone", "America/New_York"))))
        db.flush()
        accounts = [
            ("demo-operator", "cedar-demo", "operator@cedar.example.com", "operator"),
            ("demo-admin", "cedar-demo", "admin@cedar.example.com", "admin"),
            ("demo-viewer", "cedar-demo", "viewer@cedar.example.com", "viewer"),
            ("harbor-operator", "harbor-demo", "operator@harbor.example.com", "operator"),
        ]
        for user_id, workspace_id, email, role in accounts:
            if not db.get(User, user_id):
                db.add(User(id=user_id, workspace_id=workspace_id, email=email, role=role, password_hash=hash_password("DemoVoiceDesk2026!")))
        for item in data["services"]:
            if item.get("workspace_id", "cedar-demo") in customized:
                continue
            db.merge(Service(
                id=item["id"], workspace_id=item.get("workspace_id", "cedar-demo"), name=item["name"],
                description=item.get("description", ""), duration_minutes=item["duration_minutes"],
                price_from_cents=item["price_from_cents"], policy_source=item.get("policy_source", f"kb:{item['id']}"),
                eligible_zone_ids=item.get("eligible_zone_ids", [zone["id"] for zone in data["zones"]]),
            ))
        for item in data["zones"]:
            db.merge(ServiceZone(id=item["id"], workspace_id=item.get("workspace_id", "cedar-demo"), name=item["name"], postal_prefixes=item.get("postal_prefixes", [])))
        for item in data["staff"]:
            db.merge(StaffResource(
                id=item["id"], workspace_id=item.get("workspace_id", "cedar-demo"), name=item["name"],
                service_ids=item["service_ids"], zone_ids=item["zone_ids"], weekly_hours=item["weekly_hours"],
            ))
        db.flush()
        hours_data = data.get("business_hours", [])
        if isinstance(hours_data, dict):
            hours_data = [{"weekday": day, **interval} for day, intervals in hours_data.items() for interval in intervals]
        for index, item in enumerate(hours_data):
            if isinstance(item, dict) and "weekday" in item:
                if item.get("workspace_id", "cedar-demo") in customized:
                    continue
                db.merge(BusinessHours(id=item.get("id", f"cedar-hours-{index}"), workspace_id=item.get("workspace_id", "cedar-demo"), weekday=item["weekday"], start_local=item.get("start", item.get("start_local", "08:00")), end_local=item.get("end", item.get("end_local", "17:00"))))
        for index, item in enumerate(data.get("blackouts", [])):
            db.merge(Blackout(id=item.get("id", f"blackout-{index}"), workspace_id=item.get("workspace_id", "cedar-demo"), staff_id=item.get("staff_id"), start_at=parse_instant(item["start_at"]), end_at=parse_instant(item["end_at"]), reason=item.get("reason", "Unavailable")))
        counts["services"] = len(data["services"])
        counts["staff"] = len(data["staff"])
        counts["zones"] = len(data["zones"])
        db.flush()
        for item in data.get("customers", []):
            db.merge(Customer(id=item["id"], workspace_id=item.get("workspace_id", "cedar-demo"), name=item["name"], email=item["email"], phone=item.get("phone")))
        db.flush()
        for item in data.get("appointments", []):
            db.merge(Appointment(
                id=item["id"], booking_reference=item.get("booking_reference", item["id"]),
                workspace_id=item.get("workspace_id", "cedar-demo"), customer_id=item["customer_id"],
                service_id=item["service_id"], zone_id=item["zone_id"], staff_id=item["staff_id"],
                start_at=parse_instant(item["start_at"]), end_at=parse_instant(item["end_at"]), status=item.get("status", "confirmed"),
                verification_hash=demo_fixture_hash(item["id"]),
            ))
        counts["customers"] = len(data.get("customers", []))
        counts["appointments"] = len(data.get("appointments", []))
    return counts


if __name__ == "__main__":
    print(seed())
