"""FastAPI composition root for the VoiceDesk pilot."""

import hashlib
import json
import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from voicedesk.auth import (
    COOKIE_NAME,
    create_auth_session,
    current_auth,
    current_user,
    mutation_user,
    operator_user,
    user_by_email,
    verify_password,
)
from voicedesk.booking import (
    BookingError,
    cancel_appointment,
    check_verification_token,
    invalidate_proposal,
    make_proposal,
    reconcile_google_booking,
    reconcile_google_change,
    reschedule_appointment,
    verify_appointment,
)
from voicedesk.calendar import CalendarError, GoogleCalendar, LocalCalendar
from voicedesk.config import get_settings
from voicedesk.db import Base, engine, get_db
from voicedesk.domain import DomainError, overlaps, stored_utc
from voicedesk.graphs import GraphRuntime, _demo_extract
from voicedesk.knowledge import scoped_articles
from voicedesk.models import (
    Appointment,
    BookingOperation,
    Customer,
    Handoff,
    Proposal,
    Service,
    ServiceZone,
    SessionEvent,
    StaffResource,
    TranscriptTurn,
    User,
    VoiceSession,
)
from voicedesk.schemas import (
    AppointmentResult,
    AppointmentView,
    AuthView,
    AvailabilityView,
    CancelInput,
    ConfirmInput,
    HandoffView,
    LoginInput,
    ProposalInput,
    ProposalResult,
    RescheduleInput,
    SessionCreate,
    SessionView,
    TurnInput,
    TurnResult,
    UserView,
    VerifyInput,
    VerifyView,
)
from voicedesk.stream import router as stream_router
from voicedesk.views import appointment_view, proposal_view, session_view


def _uuid() -> str:
    return str(uuid4())


def _redact_verification_code(value: str) -> str:
    return re.sub(r"(\b(?:verification code|code)\s*(?:is|:)?\s*)\d{6}\b", r"\1[REDACTED]", value, flags=re.I)


def _spoken_confirmation_matches(proposal: Proposal, text: str) -> bool:
    """An affirmative turn cannot silently confirm details it states differently."""
    mentioned = _demo_extract(text, proposal.workspace_id)
    proposed_local = stored_utc(proposal.start_at).astimezone(ZoneInfo(proposal.timezone))
    if mentioned.ambiguous_date:
        return False
    if mentioned.exact_date and mentioned.exact_date != proposed_local.date():
        return False
    if mentioned.exact_time and mentioned.exact_time != proposed_local.strftime("%H:%M"):
        return False
    if mentioned.service_id and mentioned.service_id != proposal.service_id:
        return False
    if mentioned.zone_id and mentioned.zone_id != proposal.zone_id:
        return False
    stated_zone = re.search(r"\b[A-Za-z]+/[A-Za-z_]+\b", text)
    if stated_zone and stated_zone.group(0).lower() != proposal.timezone.lower():
        return False
    return True


def _owned_session(db: Session, workspace_id: str, session_id: str) -> VoiceSession:
    found = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.workspace_id == workspace_id))
    if not found:
        raise HTTPException(404, "Session not found.")
    return found


def _owned_appointment(db: Session, workspace_id: str, appointment_id: str) -> Appointment:
    found = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id))
    if not found:
        raise HTTPException(404, "Appointment not found.")
    return found


def _change_hash(slots: dict) -> str:
    keys = ("change_intent", "booking_reference", "customer_email", "exact_date", "exact_time", "timezone")
    return hashlib.sha256(json.dumps({key: slots.get(key) for key in keys}, sort_keys=True).encode()).hexdigest()


def _handle_change_turn(db: Session, voice_session: VoiceSession, payload: TurnInput, slots: dict) -> str:
    """Verification and final confirmation are application checks, never model assertions."""
    reference = slots.get("booking_reference")
    email = slots.get("customer_email")
    if not reference or not email:
        return "Please provide the booking reference and the email on that booking. No change has been made."
    appointment = db.scalar(select(Appointment).where(Appointment.workspace_id == voice_session.workspace_id,
                                                      Appointment.booking_reference == reference))
    customer = db.get(Customer, appointment.customer_id) if appointment else None
    if not appointment or appointment.status != "confirmed" or not customer or customer.email.lower() != email.lower():
        return "The booking reference and email could not be verified together. No change has been made; an operator can help."
    if slots.get("change_intent") == "reschedule" and not (slots.get("exact_date") and slots.get("exact_time")):
        return "Please give the exact new date, time, and timezone. Your original booking remains in place."
    code_verified = False
    if voice_session.mode == "connected" and not slots.get("change_verified"):
        code_match = re.search(r"\b(?:verification code|code)\s*(?:is|:)?\s*(\d{6})\b", payload.text, re.I)
        code = code_match.group(1) if code_match else None
        if not code:
            return "Please provide the six-digit verification code from your booking confirmation. No change has been made."
        try:
            verify_appointment(db, voice_session.workspace_id, appointment.id, email, code)
            code_verified = True
        except BookingError:
            return "That verification code did not match. No change has been made."
    current_hash = _change_hash(slots)
    explicit_verification = code_verified or bool(re.search(r"\bverif(?:y|ication)\b", payload.text, re.I))
    affirmative = bool(re.match(r"^\s*(yes|confirm|i confirm)\b", payload.text, re.I))
    correction = bool(re.search(r"\b(but|actually|instead|wait|not that)\b", payload.text, re.I))
    if explicit_verification and not affirmative:
        slots["change_verified"] = True
        slots["change_hash"] = current_hash
        voice_session.stable_slots = dict(slots)
        if slots["change_intent"] == "cancel":
            return f"The booking reference and owner email match. Please explicitly confirm cancellation of {reference}. No change has been made yet."
        return f"The booking reference and owner email match. Please explicitly confirm moving {reference} to {slots['exact_date']} at {slots['exact_time']} {slots.get('timezone', voice_session.timezone)}. Your old booking remains."
    if not affirmative or correction:
        return "Please complete a separate verification turn, then explicitly confirm the exact change. Your original booking remains in place."
    if not slots.get("change_verified") or slots.get("change_hash") != current_hash:
        slots["change_verified"] = False
        voice_session.stable_slots = dict(slots)
        return "The proposed change details changed or were not verified. Please verify the booking reference and owner email again."
    db.commit()
    try:
        if slots["change_intent"] == "cancel":
            cancel_appointment(voice_session.workspace_id, appointment.id, f"turn-cancel:{voice_session.id}:{payload.turn_id}")
            reply = f"Booking {reference} is cancelled."
        else:
            timezone_name = slots.get("timezone", voice_session.timezone)
            start = datetime.fromisoformat(f"{slots['exact_date']}T{slots['exact_time']}").replace(tzinfo=ZoneInfo(timezone_name))
            reschedule_appointment(voice_session.workspace_id, appointment.id,
                                   RescheduleInput(verification_token="verified-in-session",
                                                   idempotency_key=f"turn-move:{voice_session.id}:{payload.turn_id}",
                                                   start_at=start, timezone=timezone_name))
            reply = f"Booking {reference} is moved to {slots['exact_date']} at {slots['exact_time']} {timezone_name}."
    except DomainError as exc:
        reply = f"{exc} Your original booking is unchanged."
    db.expire_all()
    refreshed = _owned_session(db, voice_session.workspace_id, voice_session.id)
    cleaned = dict(refreshed.stable_slots or {})
    for key in ("change_intent", "change_verified", "change_hash", "booking_reference"):
        cleaned.pop(key, None)
    refreshed.stable_slots = cleaned
    db.add(SessionEvent(id=_uuid(), workspace_id=refreshed.workspace_id, session_id=refreshed.id,
                        type="change_outcome", detail={"booking_reference": reference, "reply": reply}))
    return reply


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.app_mode not in {"demo", "connected"}:
        raise RuntimeError("APP_MODE must be demo or connected")
    if settings.app_mode == "connected" and settings.app_secret_key == "local-demo-only-change-before-deployment":
        raise RuntimeError("Set APP_SECRET_KEY before starting connected mode")
    if settings.audio_retention_enabled:
        raise RuntimeError("AUDIO_RETENTION_ENABLED is unsupported until encrypted audio storage and purge are configured")
    if settings.is_demo and settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        context = PostgresSaver.from_conn_string(dsn)
        saver = context.__enter__()
        saver.setup()
        app.state.graphs = GraphRuntime(saver)
        try:
            yield
        finally:
            context.__exit__(None, None, None)
    else:
        from langgraph.checkpoint.sqlite import SqliteSaver
        checkpoint_path = Path("voicedesk-checkpoints.sqlite")
        connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        saver = SqliteSaver(connection)
        app.state.graphs = GraphRuntime(saver)
        try:
            yield
        finally:
            connection.close()


app = FastAPI(title="VoiceDesk API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_audit(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", supplied_id) else str(uuid4())
    request.state.request_id = request_id
    started = monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        logging.getLogger("uvicorn.error").info(json.dumps({
            "event": "http_request", "request_id": request_id,
            "method": request.method, "route": getattr(route, "path", "unmatched"),
            "status": status, "duration_ms": round((monotonic() - started) * 1000, 1),
        }))


app.add_middleware(
    CORSMiddleware, allow_origins=[item.strip() for item in get_settings().cors_origins.split(",")],
    allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
app.include_router(stream_router)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    conflict_codes = {"slot_conflict", "slot_busy", "proposal_stale", "proposal_expired", "operation_pending", "operation_conflict", "already_cancelled", "provider_conflict", "provider_uncertain"}
    return JSONResponse(status_code=409 if exc.code in conflict_codes else 400,
                        content={"code": exc.code, "detail": str(exc)})


@app.exception_handler(CalendarError)
async def calendar_error_handler(_: Request, exc: CalendarError):
    return JSONResponse(status_code=503, content={"code": "calendar_unavailable", "detail": str(exc)})


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "mode": get_settings().app_mode}


@app.post("/api/auth/login", response_model=AuthView)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> AuthView:
    user = user_by_email(db, str(payload.email))
    if not user or not verify_password(user.password_hash, payload.password):
        raise HTTPException(401, "Invalid credentials.")
    auth_session = create_auth_session(db, user, response)
    return AuthView(user=UserView.model_validate(user), csrf_token=auth_session.csrf_token)


@app.get("/api/auth/me", response_model=AuthView)
def me(auth=Depends(current_auth)) -> AuthView:
    auth_session, user = auth
    return AuthView(user=UserView.model_validate(user), csrf_token=auth_session.csrf_token)


@app.post("/api/auth/logout")
def logout(response: Response, auth=Depends(current_auth), user: User = Depends(mutation_user), db: Session = Depends(get_db)) -> dict:
    auth_session, _ = auth
    auth_session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", domain=get_settings().cookie_domain)
    return {"signed_out": True}


@app.get("/api/catalog")
def catalog(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    services = db.scalars(select(Service).where(Service.workspace_id == user.workspace_id, Service.active == True)).all()  # noqa: E712
    zones = db.scalars(select(ServiceZone).where(ServiceZone.workspace_id == user.workspace_id)).all()
    staff = db.scalars(select(StaffResource).where(StaffResource.workspace_id == user.workspace_id)).all()
    return {
        "services": [{"id": item.id, "name": item.name, "description": item.description,
                      "duration_minutes": item.duration_minutes, "price_from_cents": item.price_from_cents,
                      "policy_source": item.policy_source, "eligible_zone_ids": item.eligible_zone_ids} for item in services],
        "zones": [{"id": item.id, "name": item.name, "postal_prefixes": item.postal_prefixes} for item in zones],
        "staff": [{"id": item.id, "name": item.name, "service_ids": item.service_ids, "zone_ids": item.zone_ids} for item in staff],
    }


@app.get("/api/knowledge")
def knowledge(user: User = Depends(current_user)) -> dict:
    return {"articles": scoped_articles(user.workspace_id),
            "synthetic": get_settings().is_demo or user.workspace_id == "cedar-connected"}


@app.get("/api/replays")
def replays(user: User = Depends(current_user)) -> list[dict]:
    if user.workspace_id != "cedar-demo" or not get_settings().is_demo:
        return []
    path = get_settings().api_root / "fixtures" / "audio_scripts" / "scripts.jsonl"
    if not path.exists():
        return []
    output = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        output.append({"id": item["script_id"], "title": item["source_scenario_id"].replace("-", " "),
                       "script": item["turns"], "turns": item["turns"], "provenance": item["provenance"],
                       "status": item["status"], "audio_fixture_url": None})
    return output


@app.get("/api/health/providers")
def provider_health(user: User = Depends(current_user)) -> dict:
    settings = get_settings()
    if settings.is_demo:
        return {"mode": "demo", "model": {"status": "simulated", "detail": "Deterministic text fixture; no model call."},
                "audio": {"status": "simulated", "detail": "Script replay only; microphone provider is disconnected."},
                "calendar": {"status": "simulated", "detail": "Local transactional calendar with synthetic data."}}
    configured_model = bool(settings.openai_api_key)
    configured_calendar = settings.calendar_provider == "local" or bool(settings.google_calendar_id and settings.google_service_account_json)
    return {"mode": "connected",
            "model": {"status": "unverified" if configured_model else "missing_config", "detail": "OpenAI credentials configured; no live request has been verified by this health check." if configured_model else "OPENAI_API_KEY is missing."},
            "audio": {"status": "unverified" if configured_model else "missing_config", "detail": "OpenAI STT/TTS configured; live audio must be verified during a session." if configured_model else "OPENAI_API_KEY is missing."},
            "calendar": {"status": "unverified" if configured_calendar else "missing_config", "detail": f"{settings.calendar_provider} calendar configured; availability and writes are verified per operation." if configured_calendar else "Google Calendar configuration is missing."}}


@app.post("/api/sessions", response_model=SessionView)
def create_session(payload: SessionCreate, user: User = Depends(operator_user), db: Session = Depends(get_db)) -> SessionView:
    if payload.mode != get_settings().app_mode:
        raise HTTPException(400, "Session mode must match the server's configured mode.")
    if payload.mode == "connected" and not get_settings().openai_api_key:
        raise HTTPException(503, "Connected sessions require OPENAI_API_KEY.")
    record = VoiceSession(id=_uuid(), workspace_id=user.workspace_id, created_by_user_id=user.id,
                          mode=payload.mode, channel=payload.channel, status="active",
                          stable_slots={}, tentative_slots={})
    db.add(record)
    db.commit()
    return session_view(db, record)


@app.get("/api/sessions", response_model=list[SessionView])
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[SessionView]:
    records = db.scalars(select(VoiceSession).where(VoiceSession.workspace_id == user.workspace_id).order_by(VoiceSession.created_at.desc()).limit(100)).all()
    return [session_view(db, record) for record in records]


@app.get("/api/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SessionView:
    return session_view(db, _owned_session(db, user.workspace_id, session_id))


def process_turn(db: Session, voice_session: VoiceSession, payload: TurnInput, graphs: GraphRuntime) -> TurnResult:
    previous = db.scalar(select(TranscriptTurn).where(TranscriptTurn.session_id == voice_session.id, TranscriptTurn.turn_id == payload.turn_id, TranscriptTurn.speaker == "user"))
    if previous:
        assistant = db.scalar(select(TranscriptTurn).where(TranscriptTurn.session_id == voice_session.id, TranscriptTurn.turn_id == payload.turn_id, TranscriptTurn.speaker == "assistant"))
        if previous.text != _redact_verification_code(payload.text) or not assistant:
            raise BookingError("turn_conflict", "This turn ID is already processing or has different text.")
        return TurnResult(session=session_view(db, voice_session), turn=next(item for item in session_view(db, voice_session).turns if item.id == previous.id), reply_text=assistant.text)
    user_turn = TranscriptTurn(id=_uuid(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
                               turn_id=payload.turn_id, speaker="user", text=_redact_verification_code(payload.text), source=payload.source)
    db.add(user_turn)
    verification_code = None
    confirm_words = bool(re.match(r"^\s*(yes|confirm|i confirm|that's correct|that is correct)\b", payload.text, re.I))
    correction_words = bool(re.search(r"\b(but|actually|instead|change|not|wait|stop)\b", payload.text, re.I))
    if voice_session.active_proposal_id and confirm_words and not correction_words:
        proposal = db.get(Proposal, voice_session.active_proposal_id)
        if not proposal or not _spoken_confirmation_matches(proposal, payload.text):
            correction_words = True
    if voice_session.active_proposal_id and confirm_words and not correction_words:
        proposal = db.get(Proposal, voice_session.active_proposal_id)
        db.flush()
        db.commit()
        outcome = graphs.confirm(voice_session.workspace_id, proposal.id, proposal.version, proposal.proposal_hash, f"turn:{voice_session.id}:{payload.turn_id}")
        verification_code = outcome.get("verification_code")
        reply = "Your appointment is confirmed. Keep the verification code shown with the booking."
        db.expire_all()
        voice_session = _owned_session(db, voice_session.workspace_id, voice_session.id)
        db.add(SessionEvent(id=_uuid(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
                            type="voice_confirmation", detail={"appointment_id": outcome["appointment_id"], "turn_id": payload.turn_id}))
    else:
        if voice_session.active_proposal_id:
            invalidate_proposal(db, voice_session, "new finalized turn or interruption")
        graph_state = graphs.interpret({
            "workspace_id": voice_session.workspace_id, "session_id": voice_session.id,
            "turn_id": payload.turn_id, "text": _redact_verification_code(payload.text), "mode": voice_session.mode,
            "stable_slots": voice_session.stable_slots or {}, "tentative_slots": {},
            "timezone": voice_session.timezone, "proposal_version": voice_session.proposal_version,
            "confirmation": None, "booking_operation_id": None, "observable_events": [],
        })
        voice_session.stable_slots = graph_state["stable_slots"]
        reply = graph_state["reply_text"]
        for item in graph_state.get("observable_events", []):
            db.add(SessionEvent(id=_uuid(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
                                type=item["type"], detail={key: value for key, value in item.items() if key != "type"}))
        if graph_state.get("route") == "handoff":
            handoff = Handoff(id=_uuid(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
                              reason="unsupported_or_human_request", summary=f"Caller request: {_redact_verification_code(payload.text[:500])}")
            db.add(handoff)
            voice_session.status = "handoff"
        if graph_state.get("route") == "change":
            reply = _handle_change_turn(db, voice_session, payload, graph_state["stable_slots"])
        slots = graph_state["stable_slots"]
        needed = {"service_id", "zone_id", "exact_date", "exact_time", "customer_name", "customer_email"}
        if graph_state.get("route") == "availability" and needed.issubset(slots):
            try:
                timezone_name = slots.get("timezone", voice_session.timezone)
                local = datetime.fromisoformat(f"{slots['exact_date']}T{slots['exact_time']}").replace(tzinfo=ZoneInfo(timezone_name))
                proposal = make_proposal(db, voice_session, ProposalInput(
                    service_id=slots["service_id"], zone_id=slots["zone_id"], start_at=local,
                    timezone=timezone_name, customer_name=slots["customer_name"],
                    customer_email=slots["customer_email"], customer_phone=slots.get("customer_phone"),
                ))
                # The graph checkpointer has its own database connection. Release the
                # proposal transaction before it writes the approval interrupt.
                db.commit()
                graphs.propose(voice_session.workspace_id, voice_session.id, proposal.id, proposal.version, proposal.proposal_hash)
                db.expire_all()
                voice_session = _owned_session(db, voice_session.workspace_id, voice_session.id)
                reply = voice_session.last_reply or reply
            except DomainError as exc:
                reply = f"{exc} I can show other verified times."
    voice_session.last_reply = reply
    db.add(TranscriptTurn(id=_uuid(), workspace_id=voice_session.workspace_id, session_id=voice_session.id,
                          turn_id=payload.turn_id, speaker="assistant", text=reply,
                          source="demo" if voice_session.mode == "demo" else "model"))
    db.commit()
    return TurnResult(session=session_view(db, voice_session),
                      turn=next(item for item in session_view(db, voice_session).turns if item.id == user_turn.id),
                      reply_text=reply, verification_code=verification_code)


@app.post("/api/sessions/{session_id}/turns", response_model=TurnResult)
def add_turn(session_id: str, payload: TurnInput, request: Request,
             user: User = Depends(operator_user), db: Session = Depends(get_db)) -> TurnResult:
    voice_session = _owned_session(db, user.workspace_id, session_id)
    if voice_session.status not in {"active", "handoff", "booked"}:
        raise HTTPException(409, "This session is closed.")
    if payload.source == "stt" and voice_session.channel != "voice":
        raise HTTPException(400, "STT turns require a voice session.")
    return process_turn(db, voice_session, payload, request.app.state.graphs)


@app.post("/api/sessions/{session_id}/proposals", response_model=ProposalResult)
def create_proposal(session_id: str, payload: ProposalInput, request: Request,
                    user: User = Depends(operator_user), db: Session = Depends(get_db)) -> ProposalResult:
    voice_session = _owned_session(db, user.workspace_id, session_id)
    proposal = make_proposal(db, voice_session, payload)
    db.commit()
    request.app.state.graphs.propose(user.workspace_id, session_id, proposal.id, proposal.version, proposal.proposal_hash)
    return ProposalResult(proposal=proposal_view(db, proposal), session=session_view(db, voice_session))


@app.post("/api/sessions/{session_id}/proposals/{proposal_id}/confirm", response_model=AppointmentResult)
def confirm(session_id: str, proposal_id: str, payload: ConfirmInput, request: Request,
            user: User = Depends(operator_user), db: Session = Depends(get_db)) -> AppointmentResult:
    _owned_session(db, user.workspace_id, session_id)
    proposal = db.scalar(select(Proposal).where(Proposal.id == proposal_id, Proposal.workspace_id == user.workspace_id, Proposal.session_id == session_id))
    if not proposal:
        raise HTTPException(404, "Proposal not found.")
    if proposal.version != payload.version or proposal.proposal_hash != payload.hash:
        raise BookingError("proposal_stale", "The proposal version or details changed; review it again.")
    result = request.app.state.graphs.confirm(user.workspace_id, proposal_id, payload.version, payload.hash, payload.idempotency_key)
    if result.get("status") != "committed":
        raise BookingError("confirmation_rejected", "Confirmation was not accepted.")
    db.expire_all()
    appointment = _owned_appointment(db, user.workspace_id, result["appointment_id"])
    return AppointmentResult(appointment=appointment_view(db, appointment),
                             session=session_view(db, _owned_session(db, user.workspace_id, session_id)),
                             verification_code=result.get("verification_code"))


@app.get("/api/calendar/availability", response_model=AvailabilityView)
def availability(service_id: str, zone_id: str, date: date, timezone: str = "America/New_York",
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> AvailabilityView:
    slots = LocalCalendar().slots(db, user.workspace_id, service_id, zone_id, date, timezone)
    if slots and get_settings().calendar_provider == "google" and not get_settings().is_demo:
        busy_intervals = GoogleCalendar().busy_intervals(
            min(slot["start_at"] for slot in slots), max(slot["end_at"] for slot in slots),
        )
        slots = [slot for slot in slots
                 if not any(overlaps(slot["start_at"], slot["end_at"], start, end)
                            for start, end in busy_intervals)]
    return AvailabilityView(date=date, timezone=timezone, slots=slots)


@app.get("/api/appointments", response_model=list[AppointmentView])
def appointments(from_at: datetime | None = None, to_at: datetime | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[AppointmentView]:
    stmt = select(Appointment).where(Appointment.workspace_id == user.workspace_id)
    if from_at:
        stmt = stmt.where(Appointment.end_at > from_at)
    if to_at:
        stmt = stmt.where(Appointment.start_at < to_at)
    records = db.scalars(stmt.order_by(Appointment.start_at).limit(1000)).all()
    return [appointment_view(db, record) for record in records]


@app.get("/api/appointments/by-reference/{booking_reference}", response_model=AppointmentView)
def appointment_by_reference(booking_reference: str, user: User = Depends(current_user),
                             db: Session = Depends(get_db)) -> AppointmentView:
    appointment = db.scalar(select(Appointment).where(Appointment.workspace_id == user.workspace_id,
                                                      Appointment.booking_reference == booking_reference))
    if not appointment:
        raise HTTPException(404, "Booking reference not found.")
    return appointment_view(db, appointment)


@app.post("/api/appointments/{appointment_id}/verify", response_model=VerifyView)
def verify(appointment_id: str, payload: VerifyInput, user: User = Depends(operator_user),
           db: Session = Depends(get_db)) -> VerifyView:
    _owned_appointment(db, user.workspace_id, appointment_id)
    token = verify_appointment(db, user.workspace_id, appointment_id, str(payload.email), payload.verification_code)
    return VerifyView(token=token)


@app.post("/api/appointments/{appointment_id}/cancel", response_model=AppointmentResult)
def cancel(appointment_id: str, payload: CancelInput, user: User = Depends(operator_user),
           db: Session = Depends(get_db)) -> AppointmentResult:
    _owned_appointment(db, user.workspace_id, appointment_id)
    check_verification_token(payload.verification_token, user.workspace_id, appointment_id)
    result_id = cancel_appointment(user.workspace_id, appointment_id, payload.idempotency_key)
    db.expire_all()
    return AppointmentResult(appointment=appointment_view(db, _owned_appointment(db, user.workspace_id, result_id)))


@app.post("/api/appointments/{appointment_id}/reschedule", response_model=AppointmentResult)
def reschedule(appointment_id: str, payload: RescheduleInput, user: User = Depends(operator_user),
               db: Session = Depends(get_db)) -> AppointmentResult:
    _owned_appointment(db, user.workspace_id, appointment_id)
    check_verification_token(payload.verification_token, user.workspace_id, appointment_id)
    result_id = reschedule_appointment(user.workspace_id, appointment_id, payload)
    db.expire_all()
    return AppointmentResult(appointment=appointment_view(db, _owned_appointment(db, user.workspace_id, result_id)))


@app.get("/api/handoffs", response_model=list[HandoffView])
def handoffs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[HandoffView]:
    records = db.scalars(select(Handoff).where(Handoff.workspace_id == user.workspace_id).order_by(Handoff.created_at.desc()).limit(200)).all()
    return [HandoffView(id=item.id, session_id=item.session_id, reason=item.reason, summary=item.summary,
                        status=item.status, created_at=stored_utc(item.created_at)) for item in records]


@app.get("/api/booking-operations")
def booking_operations(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    records = db.scalars(select(BookingOperation).where(BookingOperation.workspace_id == user.workspace_id).order_by(BookingOperation.created_at.desc()).limit(200)).all()
    return [{"id": item.id, "appointment_id": item.appointment_id, "kind": item.kind,
             "status": item.status, "failure_reason": item.failure_reason,
             "created_at": stored_utc(item.created_at).isoformat()} for item in records]


@app.post("/api/booking-operations/{operation_id}/reconcile", response_model=AppointmentResult)
def reconcile_booking_operation(operation_id: str, user: User = Depends(operator_user),
                                db: Session = Depends(get_db)) -> AppointmentResult:
    operation = db.scalar(select(BookingOperation).where(BookingOperation.id == operation_id, BookingOperation.workspace_id == user.workspace_id))
    if not operation:
        raise HTTPException(404, "Booking operation not found.")
    if get_settings().calendar_provider != "google":
        raise HTTPException(400, "External reconciliation is only available for Google Calendar operations.")
    result_id = reconcile_google_booking(operation.id) if operation.kind == "book" else reconcile_google_change(operation.id)
    db.expire_all()
    return AppointmentResult(appointment=appointment_view(db, _owned_appointment(db, user.workspace_id, result_id)))
