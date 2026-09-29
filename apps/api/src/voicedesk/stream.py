"""Browser WebSocket transport; semantic turns go through the durable graph."""

import asyncio
from collections import deque
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from voicedesk.audio import AudioProviderError, OpenAITranscriber, OpenAITTS
from voicedesk.auth import websocket_user
from voicedesk.booking import invalidate_proposal
from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import Handoff, VoiceSession
from voicedesk.schemas import TurnInput

router = APIRouter()


def _process(session_id: str, workspace_id: str, turn_id: str, text: str, source: str, graphs):
    from voicedesk.main import process_turn

    with SessionLocal() as db:
        session = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.workspace_id == workspace_id))
        if not session:
            raise RuntimeError("Session is no longer available.")
        return process_turn(db, session, TurnInput(turn_id=turn_id, text=text, source=source), graphs)


def _invalidate(session_id: str, workspace_id: str):
    with SessionLocal.begin() as db:
        session = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.workspace_id == workspace_id))
        if session:
            invalidate_proposal(db, session, "caller interrupted or corrected the current turn")


def _handoff_audio_failure(session_id: str, workspace_id: str):
    with SessionLocal.begin() as db:
        existing = db.scalar(select(Handoff).where(Handoff.session_id == session_id, Handoff.workspace_id == workspace_id, Handoff.reason == "audio_provider_failure"))
        if not existing:
            db.add(Handoff(id=str(uuid4()), workspace_id=workspace_id, session_id=session_id,
                           reason="audio_provider_failure", summary="Audio processing failed repeatedly; no unverified transcript was used for booking."))


@router.websocket("/api/sessions/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str):
    with SessionLocal() as db:
        user = websocket_user(websocket, db)
        session = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.workspace_id == user.workspace_id)) if user else None
        if not user or user.role not in {"operator", "admin"} or not session:
            await websocket.close(code=1008, reason="Unauthorized session")
            return
        mode, workspace_id = session.mode, session.workspace_id
    settings = get_settings()
    if mode != settings.app_mode:
        await websocket.close(code=1008, reason="Session mode is no longer supported")
        return
    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(message: dict):
        async with send_lock:
            await websocket.send_json(message)

    await send({"type": "status", "status": "connected", "mode": mode,
                "disclosure": "Assistant speech is AI-generated. Finalized transcripts are retained; audio is not retained by default.",
                "audio_retained": settings.audio_retention_enabled,
                "transcript_retention_days": settings.retention_days,
                "retention_enforcement": "operator_cli_purge"})
    generation = 0
    speech_task: asyncio.Task | None = None
    suppressed: set[str] = set()
    pending: deque[str] = deque()
    item_turns: dict[str, str] = {}
    current_turn: str | None = None
    muted = False
    failures = 0

    async def stop_speech():
        nonlocal generation, speech_task
        generation += 1
        if speech_task and not speech_task.done():
            speech_task.cancel()
            try:
                await speech_task
            except asyncio.CancelledError:
                pass
        speech_task = None

    async def speak(turn_id: str, reply: str, turn_generation: int):
        nonlocal failures
        try:
            await send({"type": "status", "status": "speaking", "turn_id": turn_id})
            async for chunk in OpenAITTS().chunks(reply):
                if turn_generation != generation or turn_id in suppressed:
                    return
                await send({"type": "audio_chunk", "turn_id": turn_id, "audio": chunk,
                            "format": "pcm16", "sample_rate": 24000})
            if turn_generation == generation:
                await send({"type": "done", "turn_id": turn_id})
        except asyncio.CancelledError:
            raise
        except Exception:
            failures += 1
            await send({"type": "error", "turn_id": turn_id, "code": "tts_failed", "detail": "The live speech provider failed; the text reply remains available."})
            if failures >= 2:
                await asyncio.to_thread(_handoff_audio_failure, session_id, workspace_id)

    async def complete_turn(turn_id: str, transcript: str, source: str):
        nonlocal speech_task, failures
        if turn_id in suppressed or not transcript.strip():
            return
        await send({"type": "transcript", "turn_id": turn_id, "text": transcript, "source": source})
        try:
            result = await asyncio.to_thread(_process, session_id, workspace_id, turn_id, transcript, source, websocket.app.state.graphs)
        except Exception as exc:
            failures += 1
            await send({"type": "error", "turn_id": turn_id, "code": "turn_failed", "detail": str(exc)[:300]})
            if failures >= 2:
                await asyncio.to_thread(_handoff_audio_failure, session_id, workspace_id)
            return
        # Processing can finish while the caller interrupts playback. Surface the
        # durable result even then: a committed booking must never be hidden by a
        # late interruption. The interrupted response does not start TTS.
        interrupted_after_processing = turn_id in suppressed
        await send({"type": "reply_text", "turn_id": turn_id, "text": result.reply_text,
                    "session": result.session.model_dump(mode="json"),
                    "verification_code": result.verification_code,
                    "playback_interrupted": interrupted_after_processing})
        if interrupted_after_processing:
            await send({"type": "done", "turn_id": turn_id, "source": "interrupted_after_processing"})
            return
        if mode == "connected":
            await stop_speech()
            speech_task = asyncio.create_task(speak(turn_id, result.reply_text, generation))
        else:
            await send({"type": "done", "turn_id": turn_id, "source": "script_replay"})

    if mode == "demo":
        try:
            while True:
                message = await websocket.receive_json()
                kind = message.get("type")
                turn_id = str(message.get("turn_id", ""))[:80]
                if kind == "replay_turn":
                    text = str(message.get("text", ""))[:4000]
                    if not turn_id or not text:
                        await send({"type": "error", "code": "invalid_replay_turn", "detail": "A stable turn ID and script text are required."})
                        continue
                    await send({"type": "status", "status": "processing", "turn_id": turn_id, "source": "script_replay"})
                    await complete_turn(turn_id, text, "replay")
                elif kind == "interrupt":
                    await stop_speech()
                    if turn_id:
                        suppressed.add(turn_id)
                    await asyncio.to_thread(_invalidate, session_id, workspace_id)
                    await send({"type": "status", "status": "interrupted", "turn_id": turn_id})
                elif kind == "stop":
                    await send({"type": "status", "status": "stopped"})
                    break
                else:
                    await send({"type": "error", "code": "demo_replay_only", "detail": "DEMO accepts scripted replay turns, not microphone audio."})
        except WebSocketDisconnect:
            pass
        return

    try:
        async with OpenAITranscriber() as transcriber:
            async def receive_provider():
                nonlocal failures
                async for event in transcriber.events():
                    kind = event.get("type")
                    item_id = event.get("item_id")
                    if kind == "input_audio_buffer.committed" and item_id and pending:
                        item_turns[item_id] = pending.popleft()
                    elif kind == "conversation.item.input_audio_transcription.delta":
                        turn_id = item_turns.get(item_id) or (pending[0] if pending else None)
                        if turn_id and turn_id not in suppressed:
                            await send({"type": "transcript_delta", "turn_id": turn_id, "text": event.get("delta", "")})
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        turn_id = item_turns.pop(item_id, None) or (pending.popleft() if pending else None)
                        if turn_id:
                            await complete_turn(turn_id, str(event.get("transcript", "")), "stt")
                    elif kind == "error":
                        failures += 1
                        await send({"type": "error", "code": "stt_failed", "detail": str(event.get("error", {}).get("message", "Live transcription failed."))[:300]})
                        if failures >= 2:
                            await asyncio.to_thread(_handoff_audio_failure, session_id, workspace_id)

            provider_task = asyncio.create_task(receive_provider())
            try:
                while True:
                    message = await websocket.receive_json()
                    kind = message.get("type")
                    turn_id = str(message.get("turn_id", ""))[:80]
                    if kind == "start":
                        await send({"type": "status", "status": "listening"})
                    elif kind == "mute":
                        muted = bool(message.get("muted", True))
                        await send({"type": "status", "status": "muted" if muted else "listening"})
                    elif kind == "audio_chunk":
                        if muted:
                            continue
                        if not turn_id or (current_turn and current_turn != turn_id):
                            await send({"type": "error", "code": "turn_id_required", "detail": "Finish the current turn before changing turn IDs."})
                            continue
                        if speech_task and not speech_task.done():
                            await stop_speech()
                            await send({"type": "status", "status": "interrupted", "turn_id": turn_id})
                        current_turn = turn_id
                        try:
                            await transcriber.append(str(message.get("audio", "")))
                        except AudioProviderError as exc:
                            await send({"type": "error", "turn_id": turn_id, "code": "invalid_audio", "detail": str(exc)})
                    elif kind == "end_turn":
                        if not current_turn or turn_id != current_turn:
                            await send({"type": "error", "code": "turn_not_active", "detail": "No matching audio turn is active."})
                            continue
                        pending.append(turn_id)
                        await transcriber.commit()
                        current_turn = None
                        await send({"type": "status", "status": "processing", "turn_id": turn_id})
                    elif kind == "interrupt":
                        await stop_speech()
                        if turn_id:
                            suppressed.add(turn_id)
                        await asyncio.to_thread(_invalidate, session_id, workspace_id)
                        await send({"type": "status", "status": "interrupted", "turn_id": turn_id})
                    elif kind == "stop":
                        await stop_speech()
                        await send({"type": "status", "status": "stopped"})
                        break
                    else:
                        await send({"type": "error", "code": "unknown_control", "detail": "Unknown audio control message."})
            finally:
                provider_task.cancel()
                try:
                    await provider_task
                except asyncio.CancelledError:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        await send({"type": "error", "code": "audio_disconnected", "detail": "Live audio disconnected; reconnect to start a new audio transport. Saved session and transcript remain available."})
