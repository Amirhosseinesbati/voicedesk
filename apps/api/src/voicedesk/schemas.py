from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    role: str
    workspace_id: str


class AuthView(BaseModel):
    user: UserView
    csrf_token: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class SessionCreate(BaseModel):
    mode: Literal["demo", "connected"] = "demo"
    channel: Literal["text", "voice"] = "text"


class TurnInput(BaseModel):
    turn_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)
    source: Literal["text", "stt", "replay"] = "text"


class ProposalInput(BaseModel):
    service_id: str
    zone_id: str
    start_at: datetime
    timezone: str = "America/New_York"
    customer_name: str = Field(min_length=2, max_length=160)
    customer_email: EmailStr
    customer_phone: str | None = Field(default=None, max_length=50)


class ConfirmInput(BaseModel):
    version: int
    hash: str = Field(min_length=64, max_length=64)
    confirmed: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=120)


class VerifyInput(BaseModel):
    email: EmailStr
    verification_code: str


class VerifyView(BaseModel):
    verified: Literal[True] = True
    token: str


class CancelInput(BaseModel):
    verification_token: str
    idempotency_key: str = Field(min_length=8, max_length=120)


class RescheduleInput(CancelInput):
    service_id: str | None = None
    zone_id: str | None = None
    start_at: datetime
    timezone: str = "America/New_York"


class SlotView(BaseModel):
    start_at: datetime
    end_at: datetime
    staff_id: str
    staff_name: str


class AvailabilityView(BaseModel):
    date: date
    timezone: str
    slots: list[SlotView]


class TurnView(BaseModel):
    id: str
    turn_id: str
    speaker: str
    text: str
    source: str
    superseded: bool
    created_at: datetime


class EventView(BaseModel):
    id: str
    type: str
    detail: dict
    created_at: datetime


class ProposalView(BaseModel):
    id: str
    version: int
    hash: str
    service_id: str
    service_name: str
    zone_id: str
    zone_name: str
    staff_id: str
    staff_name: str
    customer_name: str
    customer_email: str
    customer_phone: str | None
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    expires_at: datetime


class SessionView(BaseModel):
    id: str
    workspace_id: str
    mode: str
    channel: str
    status: str
    timezone: str
    stable_slots: dict
    proposal_version: int
    proposal: ProposalView | None
    turns: list[TurnView]
    events: list[EventView]
    last_reply: str | None
    created_at: datetime
    updated_at: datetime


class TurnResult(BaseModel):
    session: SessionView
    turn: TurnView
    reply_text: str
    verification_code: str | None = None


class ProposalResult(BaseModel):
    proposal: ProposalView
    session: SessionView


class AppointmentView(BaseModel):
    id: str
    booking_reference: str
    customer_id: str
    customer_name: str
    customer_email: str
    service_id: str
    service_name: str
    zone_id: str
    zone_name: str
    staff_id: str
    staff_name: str
    start_at: datetime
    end_at: datetime
    status: str
    source_session_id: str | None
    created_at: datetime


class AppointmentResult(BaseModel):
    appointment: AppointmentView
    session: SessionView | None = None
    verification_code: str | None = None


class HandoffView(BaseModel):
    id: str
    session_id: str
    reason: str
    summary: str
    status: str
    created_at: datetime


class ErrorView(BaseModel):
    code: str
    detail: str
