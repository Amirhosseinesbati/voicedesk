"""Checkpointed semantic turns and approval-separated booking workflow."""

import re
from datetime import date, datetime
from threading import RLock
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

from voicedesk.booking import confirm_proposal
from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import Service, ServiceZone
from voicedesk.prompts import TURN_EXTRACTION_V1


class ExtractedTurn(BaseModel):
    intent: Literal["booking", "availability", "policy", "reschedule", "cancel", "handoff", "greeting", "other"] = "other"
    service_id: str | None = None
    zone_id: str | None = None
    exact_date: date | None = None
    exact_time: str | None = None
    timezone: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    booking_reference: str | None = None
    verification_code: str | None = None
    ambiguous_date: bool = False
    reply_hint: str | None = None


class SemanticState(TypedDict, total=False):
    workspace_id: str
    session_id: str
    turn_id: str
    text: str
    mode: str
    stable_slots: dict
    tentative_slots: dict
    timezone: str
    proposal_version: int
    confirmation: bool | None
    booking_operation_id: str | None
    observable_events: list[dict]
    extracted: dict
    route: str
    reply_text: str


class ConfirmationState(TypedDict, total=False):
    workspace_id: str
    session_id: str
    proposal_id: str
    version: int
    proposal_hash: str
    confirmation: bool
    idempotency_key: str
    appointment_id: str
    verification_code: str | None
    status: str


def _demo_extract(text: str, workspace_id: str) -> ExtractedTurn:
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    name_match = re.search(r"\b(?:I'm|I am|my name is|this is)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b", text)
    phone_match = re.search(r"\b(?:\+1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b", text)
    intent_text = text
    for match in (email_match, name_match, phone_match):
        if match:
            intent_text = intent_text.replace(match.group(0), " ")
    lower = intent_text.lower()
    if re.search(r"\b(?:human|operator|person|complaint|emergency)\b", lower):
        intent = "handoff"
    elif re.search(r"\b(?:cancel|call off)\b", lower):
        intent = "cancel"
    elif re.search(r"\b(?:reschedule|move my appointment|change my appointment|move booking|change booking)\b", lower):
        intent = "reschedule"
    elif re.search(r"\b(?:price|cost|policy|charge|service area)\b", lower):
        intent = "policy"
    elif re.search(r"\b(?:available|availability|open slot|free slot)\b", lower):
        intent = "availability"
    elif re.search(r"\b(?:book|booking|appointment|schedule|service|repair|i meant|actually)\b", lower):
        intent = "booking"
    elif re.search(r"\b(?:hello|hi|good morning)\b", lower):
        intent = "greeting"
    else:
        intent = "other"
    service_id = zone_id = None
    with SessionLocal() as db:
        for service in db.query(Service).filter(Service.workspace_id == workspace_id):
            if service.name.lower() in lower or service.id.replace("-", " ") in lower:
                service_id = service.id
                break
        for zone in db.query(ServiceZone).filter(ServiceZone.workspace_id == workspace_id):
            if zone.name.lower() in lower or re.search(rf"\b{re.escape(zone.id.lower())}\b", lower):
                zone_id = zone.id
                break
    day_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    month_match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b", text, re.I)
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(AM|PM)?\b", text, re.I)
    reference_match = re.search(r"\bCED-(?:\d{6}|[0-9A-F]{8})\b", text, re.I)
    code_match = re.search(r"\b(?:verification code|code)\s*(?:is|:)?\s*(\d{6})\b", text, re.I)
    exact_date = None
    if day_match:
        try:
            exact_date = date.fromisoformat(day_match.group(1))
        except ValueError:
            pass
    elif month_match:
        try:
            year = int(month_match.group(3) or get_settings().demo_reference_date[:4])
            exact_date = datetime.strptime(f"{month_match.group(1)} {month_match.group(2)} {year}", "%B %d %Y").date()
            if not month_match.group(3) and exact_date < date.fromisoformat(get_settings().demo_reference_date):
                exact_date = exact_date.replace(year=year + 1)
        except ValueError:
            pass
    ambiguous = not exact_date and bool(re.search(r"\b(today|tomorrow|next|later|this (monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", lower))
    hour = int(time_match.group(1)) if time_match else None
    if hour is not None and time_match.group(3):
        hour = hour % 12 + (12 if time_match.group(3).lower() == "pm" else 0)
    return ExtractedTurn(
        intent=intent, service_id=service_id, zone_id=zone_id, exact_date=exact_date,
        exact_time=f"{hour:02d}:{time_match.group(2)}" if time_match else None,
        timezone="America/New_York" if "new york" in lower or "eastern" in lower else None,
        customer_name=name_match.group(1) if name_match else None,
        customer_email=email_match.group(0) if email_match else None,
        customer_phone=phone_match.group(0) if phone_match else None,
        booking_reference=reference_match.group(0).upper() if reference_match else None,
        verification_code=code_match.group(1) if code_match else None,
        ambiguous_date=ambiguous,
    )


def _connected_extract(text: str) -> tuple[ExtractedTurn, dict]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for connected semantic turns.")
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, timeout=20, max_retries=1)
    structured = model.with_structured_output(ExtractedTurn, include_raw=True)
    result = structured.invoke([("system", TURN_EXTRACTION_V1), ("human", text)])
    extracted = result.get("parsed")
    if not isinstance(extracted, ExtractedTurn):
        raise RuntimeError("Connected model did not return a valid structured turn.")
    raw = result.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    return extracted, {
        "type": "model_usage", "model": settings.openai_model,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cost_usd": None, "cost_status": "unknown",
    }


def build_semantic_graph(checkpointer):
    def interpret(state: SemanticState) -> dict:
        if state["mode"] == "demo":
            extracted = _demo_extract(state["text"], state["workspace_id"])
            usage_event = None
        else:
            extracted, usage_event = _connected_extract(state["text"])
        previous = dict(state.get("stable_slots", {}))
        fresh = extracted.model_dump(exclude_none=True, mode="json")
        intent = extracted.intent
        for key in ("service_id", "zone_id", "exact_date", "exact_time", "timezone", "customer_name", "customer_email", "customer_phone", "booking_reference"):
            if key in fresh:
                previous[key] = fresh[key]
        if intent in {"cancel", "reschedule"}:
            previous["change_intent"] = intent
        if intent == "handoff":
            route = "handoff"
        elif intent == "policy":
            # A caller can mention a relative day while explicitly asking only
            # for policy (for example, "not booking today"). Date clarification
            # belongs to scheduling, not a sourced policy answer.
            route = "policy"
        elif extracted.ambiguous_date:
            previous.pop("exact_date", None)
            previous.pop("exact_time", None)
            route = "clarify"
        elif intent in {"cancel", "reschedule"} or previous.get("change_intent"):
            route = "change"
        elif (intent in {"availability", "booking"} or any(key in fresh for key in ("exact_date", "exact_time", "zone_id", "service_id", "timezone", "customer_email"))) and previous.get("service_id") and previous.get("zone_id") and previous.get("exact_date"):
            route = "availability"
        elif intent in {"availability", "booking"}:
            route = "clarify"
        else:
            route = "general"
        events = [{"type": "turn_interpreted", "intent": intent, "turn_id": state["turn_id"]}]
        if usage_event:
            events.append(usage_event)
        return {"extracted": fresh, "stable_slots": previous, "route": route,
                "tentative_slots": {}, "observable_events": events}

    def clarify(state: SemanticState) -> dict:
        slots = state["stable_slots"]
        if state["extracted"].get("ambiguous_date"):
            reply = "Please say the exact date (YYYY-MM-DD) and timezone so I can check the correct day."
        elif not slots.get("service_id"):
            reply = "Which service do you need? I can help with boiler, plumbing, electrical, heating, drains, air conditioning, water heater, or home inspection."
        elif not slots.get("zone_id"):
            reply = "Which service zone are you in: North, Central, or South?"
        else:
            reply = "What exact date (YYYY-MM-DD) and timezone would you prefer?"
        return {"reply_text": reply}

    def policy(state: SemanticState) -> dict:
        from voicedesk.knowledge import answer_policy
        return {"reply_text": answer_policy(state["text"], state["stable_slots"].get("service_id"), state["workspace_id"])}

    def availability(state: SemanticState) -> dict:
        from voicedesk.calendar import GoogleCalendar, LocalCalendar
        from voicedesk.domain import overlaps
        slots = state["stable_slots"]
        with SessionLocal() as db:
            local_options = LocalCalendar().slots(db, state["workspace_id"], slots["service_id"], slots["zone_id"], date.fromisoformat(slots["exact_date"]), slots.get("timezone", "America/New_York"))
        settings = get_settings()
        if not settings.is_demo and settings.calendar_provider == "google":
            busy_intervals = (GoogleCalendar().busy_intervals(
                min(item["start_at"] for item in local_options),
                max(item["end_at"] for item in local_options),
            ) if local_options else [])
            options = [item for item in local_options
                       if not any(overlaps(item["start_at"], item["end_at"], start, end)
                                  for start, end in busy_intervals)][:3]
        else:
            options = local_options[:3]
        if not options:
            return {"reply_text": "There are no verified openings for that date. Choose another date to see alternatives.",
                    "observable_events": state.get("observable_events", []) + [{"type": "availability_checked", "count": 0}]}
        times = ", ".join(item["start_at"].astimezone(__import__('zoneinfo').ZoneInfo(slots.get("timezone", "America/New_York"))).strftime("%I:%M %p") for item in options)
        return {"reply_text": f"I found verified openings on {slots['exact_date']} in {slots.get('timezone', 'America/New_York')}: {times}. Choose a slot, then review the exact proposal before confirming.",
                "observable_events": state.get("observable_events", []) + [{"type": "availability_checked", "count": len(options)}]}

    def handoff(state: SemanticState) -> dict:
        return {"reply_text": "I can connect this request to a human operator. The handoff will contain a factual summary of this call."}

    def change(state: SemanticState) -> dict:
        slots = state["stable_slots"]
        if not slots.get("booking_reference") or not slots.get("customer_email"):
            return {"reply_text": "Please give the booking reference and the email on that booking for local verification. Connected bookings also need the verification code."}
        if state["mode"] == "connected" and not slots.get("change_verified") and not state["extracted"].get("verification_code"):
            return {"reply_text": "Please give the six-digit verification code from your booking confirmation. Your existing appointment remains in place."}
        if slots.get("change_intent") == "reschedule" and not (slots.get("exact_date") and slots.get("exact_time")):
            return {"reply_text": "What exact new date, time, and timezone would you prefer? Your old booking remains in place."}
        return {"reply_text": "I have the change details. Please complete local verification and explicitly confirm the exact change. Your existing booking remains in place until then."}

    def general(state: SemanticState) -> dict:
        return {"reply_text": "Welcome to Cedar Home Services. Tell me the service and zone you need, or ask about prices and availability."}

    builder = StateGraph(SemanticState)
    for name, fn in [("interpret", interpret), ("clarify", clarify), ("policy", policy), ("availability", availability), ("handoff", handoff), ("change", change), ("general", general)]:
        builder.add_node(name, fn)
    builder.add_edge(START, "interpret")
    builder.add_conditional_edges("interpret", lambda state: state["route"], ["clarify", "policy", "availability", "handoff", "change", "general"])
    for name in ("clarify", "policy", "availability", "handoff", "change", "general"):
        builder.add_edge(name, END)
    return builder.compile(checkpointer=checkpointer)


def build_confirmation_graph(checkpointer):
    def ask(state: ConfirmationState) -> Command[Literal["commit", "rejected"]]:
        decision = interrupt({"proposal_id": state["proposal_id"], "version": state["version"],
                              "hash": state["proposal_hash"], "question": "Confirm this exact appointment?"})
        valid = bool(decision.get("confirmed")) and decision.get("version") == state["version"] and decision.get("hash") == state["proposal_hash"]
        return Command(update={"confirmation": valid, "idempotency_key": decision.get("idempotency_key", "")}, goto="commit" if valid else "rejected")

    def commit(state: ConfirmationState) -> dict:
        appointment_id, code = confirm_proposal(state["workspace_id"], state["session_id"], state["proposal_id"], state["version"], state["proposal_hash"], state["idempotency_key"])
        return {"appointment_id": appointment_id, "verification_code": code, "status": "committed"}

    builder = StateGraph(ConfirmationState)
    builder.add_node("ask", ask)
    builder.add_node("commit", commit)
    builder.add_node("rejected", lambda _: {"status": "rejected"})
    builder.add_edge(START, "ask")
    builder.add_edge("commit", END)
    builder.add_edge("rejected", END)
    return builder.compile(checkpointer=checkpointer)


class GraphRuntime:
    def __init__(self, checkpointer):
        self.lock = RLock()
        self.semantic = build_semantic_graph(checkpointer)
        self.confirmation = build_confirmation_graph(checkpointer)

    def interpret(self, state: SemanticState) -> SemanticState:
        with self.lock:
            return self.semantic.invoke(state, {"configurable": {"thread_id": f"semantic:{state['workspace_id']}:{state['session_id']}"}, "recursion_limit": 12})

    def propose(self, workspace_id: str, session_id: str, proposal_id: str, version: int, proposal_hash: str) -> None:
        with self.lock:
            self.confirmation.invoke({"workspace_id": workspace_id, "session_id": session_id, "proposal_id": proposal_id,
                                      "version": version, "proposal_hash": proposal_hash, "status": "pending"},
                                     {"configurable": {"thread_id": f"confirm:{workspace_id}:{proposal_id}"}, "recursion_limit": 8})

    def confirm(self, workspace_id: str, proposal_id: str, version: int, proposal_hash: str, idempotency_key: str) -> ConfirmationState:
        with self.lock:
            return self.confirmation.invoke(Command(resume={"confirmed": True, "version": version, "hash": proposal_hash,
                                                             "idempotency_key": idempotency_key}),
                                            {"configurable": {"thread_id": f"confirm:{workspace_id}:{proposal_id}"}, "recursion_limit": 8})
