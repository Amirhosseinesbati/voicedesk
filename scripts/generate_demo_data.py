"""Deterministic Cedar Home Services demo data generator.

The JSON contract is intentionally framework-neutral so the API can import the
builder directly or load an artifact produced by the CLI. All times persisted
for bookings and blackouts are UTC instants; weekly schedules are local times.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_SEED = 20260927
DEFAULT_REFERENCE_DATE = "2026-09-27"
BUSINESS_TIMEZONE = "America/New_York"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

SERVICES = [
    {"id": "boiler-service", "name": "Boiler service", "description": "Annual inspection and maintenance of a residential boiler.", "duration_minutes": 90, "price_from_cents": 18900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:boiler-service"},
    {"id": "heating-repair", "name": "Heating repair", "description": "Diagnosis and repair of a residential heating system.", "duration_minutes": 120, "price_from_cents": 22900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:heating-repair"},
    {"id": "plumbing-repair", "name": "Plumbing repair", "description": "Repair of accessible household pipes, taps, and fixtures.", "duration_minutes": 90, "price_from_cents": 15900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:plumbing-repair"},
    {"id": "drain-clearing", "name": "Drain clearing", "description": "Clear a routine household sink or tub blockage.", "duration_minutes": 60, "price_from_cents": 13900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:drain-clearing"},
    {"id": "electrical-diagnostic", "name": "Electrical diagnostic", "description": "Investigate a residential electrical fault without major rewiring.", "duration_minutes": 90, "price_from_cents": 17900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:electrical-diagnostic"},
    {"id": "appliance-repair", "name": "Appliance repair", "description": "Diagnosis of a residential washer, dryer, or dishwasher.", "duration_minutes": 120, "price_from_cents": 16900, "eligible_zone_ids": ["central", "north"], "policy_source": "kb:appliance-repair"},
    {"id": "roof-inspection", "name": "Roof inspection", "description": "Visual inspection of an accessible residential roof.", "duration_minutes": 120, "price_from_cents": 24900, "eligible_zone_ids": ["central", "south"], "policy_source": "kb:roof-inspection"},
    {"id": "general-maintenance", "name": "General maintenance", "description": "Small household repairs suitable for one visit.", "duration_minutes": 60, "price_from_cents": 11900, "eligible_zone_ids": ["central", "north", "south"], "policy_source": "kb:general-maintenance"},
]
for _service in SERVICES:
    _service["workspace_id"] = "cedar-demo"

ZONES = [
    {"id": "central", "name": "Central Maple County", "postal_prefixes": ["100", "101"], "travel_fee_cents": 0},
    {"id": "north", "name": "North Maple County", "postal_prefixes": ["102", "103"], "travel_fee_cents": 1500},
    {"id": "south", "name": "South Maple County", "postal_prefixes": ["104", "105"], "travel_fee_cents": 2000},
]
for _zone in ZONES:
    _zone["workspace_id"] = "cedar-demo"


def _hours(days: tuple[str, ...], start: str, end: str) -> dict[str, list[dict[str, str]]]:
    return {weekday: ([{"start": start, "end": end}] if weekday in days else []) for weekday in WEEKDAYS}


STAFF = [
    {"id": "amina-patel", "name": "Amina Patel", "service_ids": ["boiler-service", "heating-repair", "general-maintenance"], "zone_ids": ["central", "north"], "weekly_hours": _hours(WEEKDAYS[:5], "08:00", "16:00")},
    {"id": "diego-morales", "name": "Diego Morales", "service_ids": ["plumbing-repair", "drain-clearing", "general-maintenance"], "zone_ids": ["central", "south"], "weekly_hours": _hours(WEEKDAYS[1:6], "09:00", "18:00")},
    {"id": "nora-chen", "name": "Nora Chen", "service_ids": ["electrical-diagnostic", "general-maintenance", "appliance-repair"], "zone_ids": ["central", "north", "south"], "weekly_hours": _hours(WEEKDAYS[:5], "08:30", "17:00")},
    {"id": "elliot-brooks", "name": "Elliot Brooks", "service_ids": ["appliance-repair", "boiler-service", "heating-repair"], "zone_ids": ["central", "north"], "weekly_hours": _hours(WEEKDAYS[:4], "08:00", "15:30")},
    {"id": "jules-ramirez", "name": "Jules Ramirez", "service_ids": ["roof-inspection", "general-maintenance", "plumbing-repair"], "zone_ids": ["central", "south"], "weekly_hours": _hours(WEEKDAYS[2:], "10:00", "18:00")},
    {"id": "riley-owens", "name": "Riley Owens", "service_ids": ["boiler-service", "heating-repair", "drain-clearing", "electrical-diagnostic", "roof-inspection"], "zone_ids": ["central", "north", "south"], "weekly_hours": _hours(WEEKDAYS[:5], "11:00", "19:00")},
]
for _staff in STAFF:
    _staff["workspace_id"] = "cedar-demo"

BUSINESS_HOURS = {weekday: ([{"start": "10:00", "end": "16:00"}] if weekday == "sunday" else [{"start": "08:00", "end": "19:00"}]) for weekday in WEEKDAYS}

FIRST_NAMES = ("Maya", "Oliver", "Sofia", "Liam", "Ava", "Noah", "Isla", "Ethan", "Zoe", "Theo", "Leila", "Miles", "Priya", "Jonah", "Clara", "Felix", "Nina", "Owen", "Elena", "Samir")
LAST_NAMES = ("Wright", "Reed", "Foster", "Kim", "Hughes", "Singh", "Park", "Bennett", "Cole", "Diaz", "Morgan", "Nguyen", "Lewis", "Shah", "Turner", "Price", "Bell", "Bailey", "Stone", "Rivera")


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _holiday_dates(year: int) -> set[date]:
    thanksgiving = date(year, 11, 1)
    thanksgiving += timedelta(days=(3 - thanksgiving.weekday()) % 7 + 21)
    return {date(year, 1, 1), date(year, 7, 4), thanksgiving, date(year, 12, 25)}


def _blackouts(reference_date: date, business_tz: ZoneInfo) -> list[dict[str, str | None]]:
    first_year = (reference_date - timedelta(days=180)).year
    last_year = (reference_date + timedelta(days=120)).year
    result: list[dict[str, str | None]] = []
    for year in range(first_year, last_year + 1):
        for day in sorted(_holiday_dates(year)):
            start = datetime.combine(day, time(0), business_tz)
            end = start + timedelta(days=1)
            result.append({"id": f"holiday-{day.isoformat()}", "workspace_id": "cedar-demo", "staff_id": None, "start_at": _utc_iso(start), "end_at": _utc_iso(end), "reason": "Company holiday"})
    leave_days = [
        ("amina-patel", reference_date + timedelta(days=18), 2),
        ("diego-morales", reference_date + timedelta(days=31), 3),
        ("nora-chen", reference_date - timedelta(days=22), 1),
        ("jules-ramirez", reference_date + timedelta(days=48), 2),
    ]
    for staff_id, first, days in leave_days:
        start = datetime.combine(first, time(0), business_tz)
        end = start + timedelta(days=days)
        result.append({"id": f"leave-{staff_id}-{first.isoformat()}", "workspace_id": "cedar-demo", "staff_id": staff_id, "start_at": _utc_iso(start), "end_at": _utc_iso(end), "reason": "Staff leave"})
    return result


def _customers(rng: random.Random, count: int) -> list[dict[str, str]]:
    customers = []
    for index in range(count):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index // len(FIRST_NAMES) + index * 7) % len(LAST_NAMES)]
        zone = ZONES[index % len(ZONES)]
        prefix = rng.choice(zone["postal_prefixes"])
        workspace_id = "cedar-demo" if index < round(count * 0.95) else "harbor-demo"
        customers.append({
            "id": f"customer-{index + 1:04d}",
            "workspace_id": workspace_id,
            "name": f"{first} {last}",
            "email": f"customer{index + 1:04d}.{workspace_id}@example.com",
            "phone": f"+1-555-000-{index + 1:04d}",
            "zone_id": zone["id"],
            "postal_code": f"{prefix}{rng.randrange(100):02d}",
            "address_line": f"{20 + (index * 17) % 900} {rng.choice(('Maple', 'Birch', 'Oak', 'Cedar', 'Elm'))} Lane",
        })
    return customers


def _overlaps(start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in intervals)


def _appointments(
    rng: random.Random,
    reference_date: date,
    business_tz: ZoneInfo,
    customers: list[dict[str, str]],
    blackouts: list[dict[str, str | None]],
    count: int,
) -> list[dict[str, str]]:
    appointments: list[dict[str, str]] = []
    occupied: dict[tuple[str, str], list[tuple[datetime, datetime]]] = {}
    customers_by_workspace = {
        workspace_id: [customer for customer in customers if customer["workspace_id"] == workspace_id]
        for workspace_id in ("cedar-demo", "harbor-demo")
    }
    blackout_intervals = [
        (blockout["staff_id"], datetime.fromisoformat(str(blockout["start_at"]).replace("Z", "+00:00")), datetime.fromisoformat(str(blockout["end_at"]).replace("Z", "+00:00")))
        for blockout in blackouts
    ]
    # A complete roof-inspection day makes the unavailable-slot demonstration
    # an actual calendar condition rather than a scripted response.
    full_day = reference_date + timedelta(days=14)
    while full_day.weekday() != 2 or full_day in _holiday_dates(full_day.year) or any(
        staff_id in (None, "jules-ramirez", "riley-owens")
        and datetime.combine(full_day, time(12), business_tz).astimezone(timezone.utc) >= blocked_start
        and datetime.combine(full_day, time(12), business_tz).astimezone(timezone.utc) < blocked_end
        for staff_id, blocked_start, blocked_end in blackout_intervals
    ):
        full_day += timedelta(days=1)
    central_customers = [customer for customer in customers_by_workspace["cedar-demo"] if customer["zone_id"] == "central"]
    for staff_id, start_hours in (("jules-ramirez", (10, 12, 14, 16)), ("riley-owens", (11, 13, 15, 17))):
        for start_hour in start_hours:
            start = datetime.combine(full_day, time(start_hour), business_tz).astimezone(timezone.utc)
            end = start + timedelta(hours=2)
            index = len(appointments)
            customer = central_customers[index % len(central_customers)]
            appointments.append({
                "id": f"appointment-{index + 1:04d}", "workspace_id": "cedar-demo",
                "customer_id": customer["id"], "service_id": "roof-inspection", "zone_id": "central",
                "staff_id": staff_id, "start_at": _utc_iso(start), "end_at": _utc_iso(end),
                "status": "confirmed", "created_at": _utc_iso(start - timedelta(days=7)),
                "booking_reference": f"CED-{index + 1:06d}",
            })
            occupied.setdefault(("cedar-demo", staff_id), []).append((start, end))
    historical_cutoff = round(count * 0.7) + len(appointments)
    for index in range(len(appointments), count):
        workspace_id = "cedar-demo"
        phase = "past" if index < historical_cutoff else "future"
        for _attempt in range(20_000):
            offset = -rng.randrange(1, 181) if phase == "past" else rng.randrange(1, 121)
            day = reference_date + timedelta(days=offset)
            staff = rng.choice(STAFF)
            weekday = WEEKDAYS[day.weekday()]
            intervals = staff["weekly_hours"][weekday]
            if not intervals:
                continue
            service = rng.choice([item for item in SERVICES if item["id"] in staff["service_ids"]])
            possible_zones = [zone for zone in staff["zone_ids"] if zone in service["eligible_zone_ids"]]
            if not possible_zones:
                continue
            zone_id = rng.choice(possible_zones)
            candidate_customers = [customer for customer in customers_by_workspace[workspace_id] if customer["zone_id"] == zone_id]
            if not candidate_customers:
                continue
            customer = rng.choice(candidate_customers)
            interval = rng.choice(intervals)
            company_interval = BUSINESS_HOURS[weekday][0]
            opening = datetime.combine(day, max(time.fromisoformat(interval["start"]), time.fromisoformat(company_interval["start"])), business_tz)
            closing = datetime.combine(day, min(time.fromisoformat(interval["end"]), time.fromisoformat(company_interval["end"])), business_tz)
            duration = timedelta(minutes=service["duration_minutes"])
            available_steps = int((closing - opening - duration) / timedelta(minutes=30))
            if available_steps < 0:
                continue
            start = opening + timedelta(minutes=30 * rng.randrange(available_steps + 1))
            end = start + duration
            start_utc = start.astimezone(timezone.utc)
            end_utc = end.astimezone(timezone.utc)
            if any((staff_id is None or staff_id == staff["id"]) and start_utc < blocked_end and end_utc > blocked_start for staff_id, blocked_start, blocked_end in blackout_intervals):
                continue
            resource_key = (workspace_id, staff["id"])
            if _overlaps(start_utc, end_utc, occupied.get(resource_key, [])):
                continue
            status = "cancelled" if index % 13 == 0 else "confirmed"
            if status == "confirmed":
                occupied.setdefault(resource_key, []).append((start_utc, end_utc))
            created_at = start_utc - timedelta(days=rng.randrange(2, 46))
            appointments.append({
                "id": f"appointment-{index + 1:04d}",
                "workspace_id": workspace_id,
                "customer_id": customer["id"],
                "service_id": service["id"],
                "zone_id": zone_id,
                "staff_id": staff["id"],
                "start_at": _utc_iso(start_utc),
                "end_at": _utc_iso(end_utc),
                "status": status,
                "created_at": _utc_iso(created_at),
                "booking_reference": f"CED-{index + 1:06d}" if workspace_id == "cedar-demo" else f"HBR-{index + 1:06d}",
            })
            break
        else:
            raise RuntimeError(f"Unable to place appointment {index + 1}; adjust schedules or range")
    return appointments


def build_dataset(seed: int = DEFAULT_SEED, reference_date: str = DEFAULT_REFERENCE_DATE, size: str = "full") -> dict:
    """Return a deterministic dataset; `quick` is for a fast local smoke test."""
    if size not in ("quick", "full"):
        raise ValueError("size must be 'quick' or 'full'")
    parsed_reference = date.fromisoformat(reference_date)
    business_tz = ZoneInfo(BUSINESS_TIMEZONE)
    rng = random.Random(seed)
    customer_count, appointment_count = (400, 600) if size == "full" else (24, 36)
    customers = _customers(rng, customer_count)
    blackouts = _blackouts(parsed_reference, business_tz)
    appointments = _appointments(rng, parsed_reference, business_tz, customers, blackouts, appointment_count)
    return {
        "metadata": {
            "dataset_name": "Synthetic demo dataset",
            "company": "Cedar Home Services",
            "seed": seed,
            "reference_date": reference_date,
            "timezone": BUSINESS_TIMEZONE,
            "size": size,
            "generated_at": "deterministic; see seed and reference_date",
            "counts": {"services": len(SERVICES), "staff": len(STAFF), "zones": len(ZONES), "customers": len(customers), "appointments": len(appointments)},
            "appointment_status_counts": dict(Counter(appointment["status"] for appointment in appointments)),
            "planted_conditions": {"roof_inspection_full_day": next(
                datetime.fromisoformat(item["start_at"].replace("Z", "+00:00")).astimezone(business_tz).date().isoformat()
                for item in appointments if item["id"] == "appointment-0001"
            )},
        },
        "workspaces": [
            {"id": "cedar-demo", "name": "Cedar Home Services", "synthetic": True},
            {"id": "harbor-demo", "name": "Harbor Home Care (isolation fixture)", "synthetic": True},
        ],
        "services": SERVICES,
        "zones": ZONES,
        "staff": STAFF,
        "business_hours": BUSINESS_HOURS,
        "blackouts": blackouts,
        "customers": customers,
        "appointments": appointments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE, help="YYYY-MM-DD")
    parser.add_argument("--size", choices=("quick", "full"), default="full")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("fixtures/generated") / f"cedar_{args.size}.json"
    dataset = build_dataset(seed=args.seed, reference_date=args.reference_date, size=args.size)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "counts": dataset["metadata"]["counts"], "seed": args.seed, "reference_date": args.reference_date}))


if __name__ == "__main__":
    main()
