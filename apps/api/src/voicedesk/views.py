"""Workspace-scoped API projections; never return private verification hashes."""

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from voicedesk.domain import stored_utc
from voicedesk.models import (
    Appointment,
    Customer,
    Proposal,
    Service,
    ServiceZone,
    SessionEvent,
    StaffResource,
    TranscriptTurn,
    VoiceSession,
)
from voicedesk.schemas import AppointmentView, EventView, ProposalView, SessionView, TurnView


def proposal_view(db: Session, proposal: Proposal) -> ProposalView:
    return ProposalView(
        id=proposal.id, version=proposal.version, hash=proposal.proposal_hash,
        service_id=proposal.service_id, service_name=db.get(Service, proposal.service_id).name,
        zone_id=proposal.zone_id, zone_name=db.get(ServiceZone, proposal.zone_id).name,
        staff_id=proposal.staff_id, staff_name=db.get(StaffResource, proposal.staff_id).name,
        customer_name=proposal.customer_name, customer_email=proposal.customer_email,
        customer_phone=proposal.customer_phone, start_at=stored_utc(proposal.start_at),
        end_at=stored_utc(proposal.end_at), timezone=proposal.timezone,
        status=proposal.status, expires_at=stored_utc(proposal.expires_at),
    )


def session_view(db: Session, voice_session: VoiceSession) -> SessionView:
    proposal = db.get(Proposal, voice_session.active_proposal_id) if voice_session.active_proposal_id else None
    turns = db.scalars(select(TranscriptTurn).where(TranscriptTurn.workspace_id == voice_session.workspace_id, TranscriptTurn.session_id == voice_session.id).order_by(
        TranscriptTurn.created_at,
        case((TranscriptTurn.speaker == "user", 0), (TranscriptTurn.speaker == "assistant", 1), else_=2),
        TranscriptTurn.id,
    )).all()
    events = db.scalars(select(SessionEvent).where(SessionEvent.workspace_id == voice_session.workspace_id, SessionEvent.session_id == voice_session.id).order_by(SessionEvent.created_at)).all()
    return SessionView(
        id=voice_session.id, workspace_id=voice_session.workspace_id, mode=voice_session.mode,
        channel=voice_session.channel, status=voice_session.status, timezone=voice_session.timezone,
        stable_slots=voice_session.stable_slots or {}, proposal_version=voice_session.proposal_version,
        proposal=proposal_view(db, proposal) if proposal else None,
        turns=[TurnView(id=item.id, turn_id=item.turn_id, speaker=item.speaker, text=item.text,
                        source=item.source, superseded=item.superseded, created_at=stored_utc(item.created_at)) for item in turns],
        events=[EventView(id=item.id, type=item.type, detail=item.detail,
                          created_at=stored_utc(item.created_at)) for item in events],
        last_reply=voice_session.last_reply, created_at=stored_utc(voice_session.created_at),
        updated_at=stored_utc(voice_session.updated_at),
    )


def appointment_view(db: Session, appointment: Appointment) -> AppointmentView:
    customer = db.get(Customer, appointment.customer_id)
    service = db.get(Service, appointment.service_id)
    zone = db.get(ServiceZone, appointment.zone_id)
    staff = db.get(StaffResource, appointment.staff_id)
    return AppointmentView(
        id=appointment.id, booking_reference=appointment.booking_reference,
        customer_id=customer.id, customer_name=customer.name,
        customer_email=customer.email, service_id=service.id, service_name=service.name,
        zone_id=zone.id, zone_name=zone.name, staff_id=staff.id, staff_name=staff.name,
        start_at=stored_utc(appointment.start_at), end_at=stored_utc(appointment.end_at),
        status=appointment.status, source_session_id=appointment.source_session_id,
        created_at=stored_utc(appointment.created_at),
    )
