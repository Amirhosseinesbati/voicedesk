"""Workspace-scoped, admin-only client configuration. No provider calls."""

from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from voicedesk.auth import current_user, mutation_user
from voicedesk.db import get_db
from voicedesk.models import BusinessHours, Proposal, Service, SlotHold, User, Workspace

Day = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS: tuple[Day, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class HoursInput(BaseModel):
    day: Day
    closed: bool = False
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def ordered_hours(self):
        if not self.closed and self.start >= self.end:
            raise ValueError("Opening time must be before closing time. Overnight hours need separate days.")
        return self


class ServiceInput(BaseModel):
    id: str
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(max_length=2000)
    duration_minutes: int = Field(ge=15, le=480, multiple_of=15)
    price_from_cents: int = Field(ge=0, le=10000000)
    active: bool

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError("Enter a service name.")
        return value.strip()


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(max_length=64)
    tagline: str = Field(max_length=120)
    theme: Literal["forest", "ocean", "plum"]
    hours: list[HoursInput] = Field(min_length=7, max_length=7)
    services: list[ServiceInput] = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA timezone such as America/New_York.") from exc
        return value

    @model_validator(mode="after")
    def complete_configuration(self):
        self.name = self.name.strip()
        self.tagline = self.tagline.strip()
        if len(self.name) < 2:
            raise ValueError("Enter a business name.")
        if {item.day for item in self.hours} != set(DAYS):
            raise ValueError("Include each weekday exactly once.")
        if len({item.id for item in self.services}) != len(self.services):
            raise ValueError("Each service must appear once.")
        if not any(item.active for item in self.services):
            raise ValueError("Keep at least one service available.")
        return self


class WorkspaceView(WorkspaceInput):
    id: str
    policy_review_required: bool = False


def workspace_view(db: Session, workspace_id: str) -> WorkspaceView:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found.")
    hours = db.scalars(select(BusinessHours).where(BusinessHours.workspace_id == workspace_id)).all()
    services = db.scalars(select(Service).where(Service.workspace_id == workspace_id).order_by(Service.name)).all()
    by_day = {row.weekday: row for row in hours}
    return WorkspaceView(
        id=workspace.id, name=workspace.name, timezone=workspace.business_timezone,
        revision=(workspace.presentation or {}).get("revision", 0),
        policy_review_required=(workspace.presentation or {}).get("policy_review_required", False),
        tagline=(workspace.presentation or {}).get("tagline", "Every call, a clear next step."),
        theme=(workspace.presentation or {}).get("theme", "forest"),
        hours=[HoursInput(day=day, closed=day not in by_day or by_day[day].start_local == by_day[day].end_local,
                          start=by_day[day].start_local if day in by_day else "09:00",
                          end=by_day[day].end_local if day in by_day else "17:00") for day in DAYS],
        services=[ServiceInput(id=item.id, name=item.name, description=item.description,
                               duration_minutes=item.duration_minutes, price_from_cents=item.price_from_cents,
                               active=item.active) for item in services],
    )


@router.get("", response_model=WorkspaceView)
def read_workspace(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return workspace_view(db, user.workspace_id)


@router.put("", response_model=WorkspaceView)
def update_workspace(payload: WorkspaceInput, user: User = Depends(mutation_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only workspace admins can change client configuration.")
    workspace = db.scalar(select(Workspace).where(Workspace.id == user.workspace_id).with_for_update())
    if not workspace:
        raise HTTPException(404, "Workspace not found.")
    services = {item.id: item for item in db.scalars(select(Service).where(Service.workspace_id == user.workspace_id))}
    if set(services) != {item.id for item in payload.services}:
        raise HTTPException(400, "Configure exactly the services in this workspace. Staff assignment is managed separately.")
    if payload.revision != (workspace.presentation or {}).get("revision", 0):
        raise HTTPException(409, "Another admin updated this workspace. Reload the saved settings before making changes.")
    policy_review = bool((workspace.presentation or {}).get("policy_review_required")) or payload.name != workspace.name or any(
        item.name != services[item.id].name or item.description != services[item.id].description
        or item.duration_minutes != services[item.id].duration_minutes
        or item.price_from_cents != services[item.id].price_from_cents or item.active != services[item.id].active
        for item in payload.services
    )
    changed = db.execute(
        update(Workspace).where(
            Workspace.id == user.workspace_id,
            func.coalesce(Workspace.presentation["revision"].as_integer(), 0) == payload.revision,
        ).values(name=payload.name, business_timezone=payload.timezone,
                 presentation={"theme": payload.theme, "tagline": payload.tagline,
                               "revision": payload.revision + 1, "policy_review_required": policy_review})
        .returning(Workspace.id), execution_options={"synchronize_session": False},
    ).scalar_one_or_none()
    if changed is None:
        db.rollback()
        raise HTTPException(409, "Another admin updated this workspace. Reload the saved settings before making changes.")
    for item in payload.services:
        service = services[item.id]
        service.name, service.description = item.name, item.description
        service.duration_minutes, service.price_from_cents = item.duration_minutes, item.price_from_cents
        service.active = item.active
    db.execute(delete(BusinessHours).where(BusinessHours.workspace_id == user.workspace_id))
    for hours in payload.hours:
        db.add(BusinessHours(id=str(uuid4()), workspace_id=user.workspace_id, weekday=hours.day,
                             start_local="00:00" if hours.closed else hours.start,
                             end_local="00:00" if hours.closed else hours.end))
    # A review made under old hours/duration must never silently book new details.
    for proposal in db.scalars(select(Proposal).where(Proposal.workspace_id == user.workspace_id, Proposal.status == "pending")):
        proposal.status = "invalidated"
    for hold in db.scalars(select(SlotHold).where(SlotHold.workspace_id == user.workspace_id, SlotHold.status == "pending")):
        hold.status = "invalidated"
    db.commit()
    db.expire(workspace)
    return workspace_view(db, user.workspace_id)
