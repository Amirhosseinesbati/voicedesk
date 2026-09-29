from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from voicedesk.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    business_timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_from_cents: Mapped[int] = mapped_column(Integer)
    policy_source: Mapped[str] = mapped_column(String(160), default="")
    eligible_zone_ids: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceZone(Base):
    __tablename__ = "service_zones"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    postal_prefixes: Mapped[list] = mapped_column(JSON, default=list)


class StaffResource(Base):
    __tablename__ = "staff_resources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    service_ids: Mapped[list] = mapped_column(JSON, default=list)
    zone_ids: Mapped[list] = mapped_column(JSON, default=list)
    weekly_hours: Mapped[dict] = mapped_column(JSON, default=dict)


class BusinessHours(Base):
    __tablename__ = "business_hours"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    weekday: Mapped[str] = mapped_column(String(16))
    start_local: Mapped[str] = mapped_column(String(5))
    end_local: Mapped[str] = mapped_column(String(5))


class Blackout(Base):
    __tablename__ = "blackouts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_resources.id"), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(200))


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="active")
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    stable_slots: Mapped[dict] = mapped_column(JSON, default=dict)
    tentative_slots: Mapped[dict] = mapped_column(JSON, default=dict)
    proposal_version: Mapped[int] = mapped_column(Integer, default=0)
    active_proposal_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"
    __table_args__ = (UniqueConstraint("session_id", "turn_id", "speaker"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    turn_id: Mapped[str] = mapped_column(String(80))
    speaker: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionEvent(Base):
    __tablename__ = "session_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    proposal_hash: Mapped[str] = mapped_column(String(64))
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    zone_id: Mapped[str] = mapped_column(ForeignKey("service_zones.id"))
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff_resources.id"))
    customer_name: Mapped[str] = mapped_column(String(160))
    customer_email: Mapped[str] = mapped_column(String(255))
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("workspace_id", "booking_reference", name="uq_booking_reference"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    booking_reference: Mapped[str] = mapped_column(String(32), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    zone_id: Mapped[str] = mapped_column(ForeignKey("service_zones.id"))
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff_resources.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    source_session_id: Mapped[str | None] = mapped_column(ForeignKey("voice_sessions.id"), nullable=True)
    verification_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SlotHold(Base):
    __tablename__ = "slot_holds"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), unique=True)
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff_resources.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class SlotClaim(Base):
    __tablename__ = "slot_claims"
    __table_args__ = (UniqueConstraint("workspace_id", "staff_id", "block_start_at", name="uq_slot_claim"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff_resources.id"))
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    block_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BookingOperation(Base):
    __tablename__ = "booking_operations"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key", name="uq_booking_idempotency"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("voice_sessions.id"), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("proposals.id"), nullable=True)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24))
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Handoff(Base):
    __tablename__ = "handoffs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    reason: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemoOutbox(Base):
    __tablename__ = "demo_outbox"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_appointments_staff_window", Appointment.workspace_id, Appointment.staff_id, Appointment.start_at)
