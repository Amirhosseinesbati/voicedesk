"""Workspace-scoped purge of retained conversation material."""

import argparse
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select

from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import (
    DemoOutbox,
    Handoff,
    Proposal,
    SessionEvent,
    TranscriptTurn,
    VoiceSession,
    Workspace,
)
from voicedesk.reset_demo import delete_checkpoint_threads


def purge_workspace(workspace_id: str, now: datetime | None = None) -> dict[str, int]:
    settings = get_settings()
    if settings.retention_days < 1:
        raise ValueError("RETENTION_DAYS must be at least one day.")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.retention_days)
    with SessionLocal() as db:
        if not db.get(Workspace, workspace_id):
            raise ValueError("Workspace not found.")
        expired_turn_sessions = set(db.scalars(select(TranscriptTurn.session_id).where(
            TranscriptTurn.workspace_id == workspace_id, TranscriptTurn.created_at < cutoff
        )))
        affected_sessions = set(db.scalars(select(VoiceSession.id).where(
            VoiceSession.workspace_id == workspace_id,
            or_(VoiceSession.updated_at < cutoff, VoiceSession.id.in_(expired_turn_sessions)),
        )))
        affected_proposals = set(db.scalars(select(Proposal.id).where(
            Proposal.workspace_id == workspace_id,
            or_(Proposal.created_at < cutoff, Proposal.session_id.in_(affected_sessions)),
        )))
    checkpoint_threads = {
        *(f"semantic:{workspace_id}:{session_id}" for session_id in affected_sessions),
        *(f"confirm:{workspace_id}:{proposal_id}" for proposal_id in affected_proposals),
    }
    delete_checkpoint_threads(checkpoint_threads)
    with SessionLocal.begin() as db:
        counts: dict[str, int] = {}
        for label, model in (
            ("turns", TranscriptTurn),
            ("events", SessionEvent),
            ("handoffs", Handoff),
            ("demo_outbox", DemoOutbox),
        ):
            outcome = db.execute(
                delete(model).where(model.workspace_id == workspace_id, model.created_at < cutoff)
            )
            counts[label] = outcome.rowcount or 0
        old_sessions = db.scalars(select(VoiceSession).where(
            VoiceSession.workspace_id == workspace_id, VoiceSession.id.in_(affected_sessions)
        )).all()
        for session in old_sessions:
            session.stable_slots = {}
            session.tentative_slots = {}
            session.last_reply = None
        counts["sessions_scrubbed"] = len(old_sessions)
        counts["checkpoint_threads_purged"] = len(checkpoint_threads)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge old conversation material in one workspace.")
    parser.add_argument("--workspace", required=True, help="Exact workspace ID to purge.")
    parser.add_argument("--confirm", action="store_true", help="Required to perform the purge.")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Pass --confirm to purge retained conversation data.")
    try:
        counts = purge_workspace(args.workspace)
    except Exception as exc:
        parser.exit(1, f"Retention purge failed: {exc}\n")
    print(json.dumps({"workspace_id": args.workspace, "purged": counts}))


if __name__ == "__main__":
    main()
