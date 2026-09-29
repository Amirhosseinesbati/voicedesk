"""Explicit, workspace-scoped reset of synthetic DEMO state."""

import argparse
import json
import sqlite3
from pathlib import Path

from sqlalchemy import delete, select

from voicedesk.config import get_settings
from voicedesk.db import SessionLocal
from voicedesk.models import (
    Appointment,
    AuthSession,
    Blackout,
    BookingOperation,
    BusinessHours,
    Customer,
    DemoOutbox,
    Handoff,
    Proposal,
    Service,
    ServiceZone,
    SessionEvent,
    SlotClaim,
    SlotHold,
    StaffResource,
    TranscriptTurn,
    User,
    VoiceSession,
    Workspace,
)
from voicedesk.seed import seed

DEMO_WORKSPACES = ("cedar-demo", "harbor-demo")


def _delete_demo_checkpoints() -> None:
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        with PostgresSaver.from_conn_string(dsn) as saver:
            _delete_scoped_threads(saver)
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = Path("voicedesk-checkpoints.sqlite")
    if not path.exists():
        return
    connection = sqlite3.connect(path, timeout=5, check_same_thread=False)
    try:
        _delete_scoped_threads(SqliteSaver(connection))
    finally:
        connection.close()


def _delete_scoped_threads(saver) -> None:
    prefixes = tuple(
        f"{kind}:{workspace_id}:"
        for workspace_id in DEMO_WORKSPACES
        for kind in ("semantic", "confirm")
    )
    thread_ids = {
        checkpoint.config["configurable"]["thread_id"]
        for checkpoint in saver.list(None)
        if checkpoint.config["configurable"]["thread_id"].startswith(prefixes)
    }
    for thread_id in thread_ids:
        saver.delete_thread(thread_id)


def delete_checkpoint_threads(thread_ids: set[str]) -> None:
    """Remove exact graph threads while preserving every other workspace."""
    if not thread_ids:
        return
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        with PostgresSaver.from_conn_string(dsn) as saver:
            for thread_id in thread_ids:
                saver.delete_thread(thread_id)
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = Path("voicedesk-checkpoints.sqlite")
    if not path.exists():
        return
    connection = sqlite3.connect(path, timeout=5, check_same_thread=False)
    try:
        saver = SqliteSaver(connection)
        for thread_id in thread_ids:
            saver.delete_thread(thread_id)
    finally:
        connection.close()


def reset_demo() -> dict[str, int]:
    settings = get_settings()
    if not settings.is_demo:
        raise RuntimeError("DEMO reset is disabled unless APP_MODE=demo.")
    with SessionLocal.begin() as db:
        demo_users = select(User.id).where(User.workspace_id.in_(DEMO_WORKSPACES))
        db.execute(delete(AuthSession).where(AuthSession.user_id.in_(demo_users)))
        for model in (
            DemoOutbox,
            SlotClaim,
            BookingOperation,
            SlotHold,
            Handoff,
            TranscriptTurn,
            SessionEvent,
            Appointment,
            Proposal,
            VoiceSession,
            Blackout,
            BusinessHours,
            Customer,
            StaffResource,
            ServiceZone,
            Service,
            User,
        ):
            db.execute(delete(model).where(model.workspace_id.in_(DEMO_WORKSPACES)))
        db.execute(delete(Workspace).where(Workspace.id.in_(DEMO_WORKSPACES)))
    _delete_demo_checkpoints()
    return seed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset only the seeded VoiceDesk DEMO workspaces.")
    parser.add_argument("--confirm", action="store_true", help="Required to perform the reset.")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Pass --confirm to reset synthetic DEMO workspaces.")
    try:
        counts = reset_demo()
    except Exception as exc:
        parser.exit(1, f"DEMO reset failed: {exc}\n")
    print(json.dumps({"reset_workspaces": DEMO_WORKSPACES, "seeded": counts}))


if __name__ == "__main__":
    main()
