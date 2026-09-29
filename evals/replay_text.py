"""Replay public text cases against isolated DEMO API instances.

Each case runs in its own SQLite process/database. The harness only submits
public customer turns and observes API records; it never uses hidden labels to
drive a booking or change. Score the resulting JSONL with evals/run.py.
"""

from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source_digest() -> str:
    """Fingerprint the API, seed, and replay inputs for one comparable run."""
    files = sorted((ROOT / "apps" / "api" / "src" / "voicedesk").rglob("*.py"))
    files += [
        ROOT / "apps" / "api" / "uv.lock",
        ROOT / "fixtures" / "generated" / "cedar_full.json",
        ROOT / "fixtures" / "knowledge_base.json",
        ROOT / "fixtures" / "scenarios" / "development.jsonl",
        ROOT / "fixtures" / "scenarios" / "held_out.jsonl",
        Path(__file__).resolve(),
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _worker(scenario_id: str) -> dict:
    if os.environ.get("VOICEDESK_EVAL_DEBUG") == "1":
        faulthandler.dump_traceback_later(15, repeat=True, file=sys.stderr)
    print("worker: import API", file=sys.stderr, flush=True)
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from fastapi.testclient import TestClient
    from voicedesk.db import Base, engine
    from voicedesk.main import app
    from voicedesk.seed import seed

    public = _load_jsonl(ROOT / "fixtures" / "scenarios" / "development.jsonl") + _load_jsonl(ROOT / "fixtures" / "scenarios" / "held_out.jsonl")
    scenario = next(item for item in public if item["scenario_id"] == scenario_id)
    if os.environ.get("VOICEDESK_EVAL_PRESEEDED") != "1":
        print("worker: create schema", file=sys.stderr, flush=True)
        Base.metadata.create_all(bind=engine)
        print("worker: seed full data", file=sys.stderr, flush=True)
        seed()
    print("worker: open test client", file=sys.stderr, flush=True)
    errors = []
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "operator@cedar.example.com", "password": "DemoVoiceDesk2026!"})
        login.raise_for_status()
        print("worker: authenticated", file=sys.stderr, flush=True)
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        baseline_response = client.get("/api/appointments")
        baseline_response.raise_for_status()
        baseline = {item["id"]: item for item in baseline_response.json()}
        created = client.post("/api/sessions", json={"mode": "demo", "channel": "text"}, headers=headers)
        created.raise_for_status()
        session_id = created.json()["id"]
        print("worker: replay turns", file=sys.stderr, flush=True)
        replies = []
        for index, turn in enumerate(scenario["turns"], 1):
            response = client.post(f"/api/sessions/{session_id}/turns", json={"turn_id": f"{scenario_id}-{index}", "text": turn["text"], "source": "replay"}, headers=headers)
            if response.status_code >= 400:
                errors.append({"turn": index, "status": response.status_code, "body": response.text[:500]})
                break
            replies.append(response.json()["reply_text"])
        session_response = client.get(f"/api/sessions/{session_id}")
        session_response.raise_for_status()
        session = session_response.json()
        appointments_response = client.get("/api/appointments")
        appointments_response.raise_for_status()
        after = {item["id"]: item for item in appointments_response.json()}
        handoffs_response = client.get("/api/handoffs")
        handoffs_response.raise_for_status()
        handoffs = [item for item in handoffs_response.json() if item["session_id"] == session_id]
    mutations = []
    for appointment_id, item in after.items():
        if appointment_id not in baseline:
            mutations.append({"action": "create", "start_at": item["start_at"]})
        else:
            previous = baseline[appointment_id]
            if item["status"] != previous["status"] and item["status"] == "cancelled":
                mutations.append({"action": "cancel", "appointment_id": appointment_id})
            elif item["start_at"] != previous["start_at"]:
                mutations.append({"action": "reschedule", "appointment_id": appointment_id, "start_at": item["start_at"]})
    if handoffs:
        outcome = "handoff"
    elif any(item["action"] == "create" for item in mutations):
        outcome = "booked"
    elif any(item["action"] == "reschedule" for item in mutations):
        outcome = "rescheduled"
    elif any(item["action"] == "cancel" for item in mutations):
        outcome = "cancelled"
    elif scenario["template"] == "policy_price" and any("kb:" in reply.lower() or "source" in reply.lower() for reply in replies):
        outcome = "answered_policy"
    else:
        outcome = "incomplete"
    new_time = next((item["start_at"] for item in mutations if item["action"] in ("create", "reschedule")), None)
    return {"scenario_id": scenario_id, "channel": "text", "outcome": outcome, "start_at": new_time, "appointment_mutations": mutations, "session_status": session["status"], "reply_texts": replies, "errors": errors, "isolation": "fresh SQLite DEMO database per case", "synthetic": True}


def _prepare_template() -> None:
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from voicedesk.db import Base, engine
    from voicedesk.seed import seed
    Base.metadata.create_all(bind=engine)
    counts = seed()
    print(json.dumps({"prepared": True, "counts": counts}))


def _case_environment(local_dir: Path, debug: bool, preseeded: bool = False) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"APP_MODE": "demo", "DATABASE_URL": f"sqlite:///{(local_dir / 'case.db').as_posix()}", "APP_SECRET_KEY": "isolated-evaluation-only-secret", "DEMO_DATA_SIZE": "full", "DEMO_SEED": "20260927", "DEMO_REFERENCE_DATE": "2026-09-27", "PYTHONPATH": str(ROOT / "apps" / "api" / "src"), "TMP": str(local_dir), "TEMP": str(local_dir), "TMPDIR": str(local_dir)})
    if debug:
        env["VOICEDESK_EVAL_DEBUG"] = "1"
    if preseeded:
        env["VOICEDESK_EVAL_PRESEEDED"] = "1"
    return env


def _run_case(scenario: dict, template_db: Path, scratch_root: Path, debug: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="voicedesk-eval-", dir=scratch_root) as temporary:
        local_dir = Path(temporary)
        if not local_dir.resolve().is_relative_to(scratch_root.resolve()):
            raise RuntimeError("Evaluation scratch directory escaped the project workspace")
        shutil.copyfile(template_db, local_dir / "case.db")
        env = _case_environment(local_dir, debug, preseeded=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--worker-case", scenario["scenario_id"]]
        try:
            completed = subprocess.run(command, cwd=local_dir, env=env, text=True, stdout=subprocess.PIPE,
                                       stderr=None if debug else subprocess.PIPE, timeout=120, check=False)
            if completed.returncode == 0:
                return json.loads(completed.stdout.strip().splitlines()[-1])
            return {"scenario_id": scenario["scenario_id"], "channel": "text", "outcome": "incomplete", "start_at": None, "appointment_mutations": [], "errors": [{"worker_exit": completed.returncode, "stderr": (completed.stderr or "")[-1500:]}], "isolation": "fresh SQLite DEMO database per case", "synthetic": True}
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {"scenario_id": scenario["scenario_id"], "channel": "text", "outcome": "incomplete", "start_at": None, "appointment_mutations": [], "errors": [{"worker_timeout_seconds": 120, "stderr": stderr[-1500:]}], "isolation": "fresh SQLite DEMO database per case", "synthetic": True}


def main() -> None:
    print("replay: starting", file=sys.stderr, flush=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held_out"), default="held_out")
    parser.add_argument("--limit", type=int, help="Smoke-test only; omitted runs all cases in the split")
    parser.add_argument("--case", help="Run only one public scenario ID")
    parser.add_argument("--output", type=Path, default=ROOT / "evals" / "results" / "observed_text.jsonl")
    parser.add_argument("--resume", action="store_true", help="Retain existing observations and run only missing cases")
    parser.add_argument("--worker-case")
    parser.add_argument("--prepare-template", action="store_true")
    parser.add_argument("--workers", type=int, default=1, help="Number of isolated API replay processes (default 1 to limit CPU use)")
    parser.add_argument("--debug", action="store_true", help="Show worker stages on stderr")
    args = parser.parse_args()
    if args.worker_case:
        print(json.dumps(_worker(args.worker_case)))
        return
    if args.prepare_template:
        _prepare_template()
        return
    print("replay: loading public scenarios", file=sys.stderr, flush=True)
    public = _load_jsonl(ROOT / "fixtures" / "scenarios" / f"{args.split}.jsonl")
    if args.case:
        public = [item for item in public if item["scenario_id"] == args.case]
        if not public:
            raise SystemExit(f"Scenario not found in {args.split}: {args.case}")
    if args.limit is not None:
        public = public[:args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scratch_root = ROOT / "evals" / ".scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)
    print("replay: preparing isolated base", file=sys.stderr, flush=True)
    if args.debug:
        faulthandler.dump_traceback_later(15, repeat=True, file=sys.stderr)
    existing = {item["scenario_id"]: item for item in _load_jsonl(args.output)} if args.resume and args.output.exists() else {}
    pending = [scenario for scenario in public if scenario["scenario_id"] not in existing]
    print(f"replay: {len(existing)} recorded, {len(pending)} pending", file=sys.stderr, flush=True)
    if not args.resume:
        args.output.write_text("", encoding="utf-8")
    if not pending:
        print(json.dumps({"output": str(args.output), "cases": len(existing), "pending": 0}))
        return
    if args.workers < 1 or args.workers > 4:
        raise ValueError("--workers must be between 1 and 4")
    revision_start = _source_digest()
    with tempfile.TemporaryDirectory(prefix="voicedesk-base-", dir=scratch_root) as temporary:
        base_dir = Path(temporary)
        print(f"replay: base path {base_dir}", file=sys.stderr, flush=True)
        if not base_dir.resolve().is_relative_to(scratch_root.resolve()):
            raise RuntimeError("Evaluation base directory escaped the project workspace")
        prepared = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--prepare-template"],
                                  cwd=base_dir, env=_case_environment(base_dir, args.debug), text=True,
                                  capture_output=True, timeout=120, check=False)
        if prepared.returncode != 0 or not (base_dir / "case.db").exists():
            raise RuntimeError(f"Could not prepare isolated DEMO database: {prepared.stderr[-1500:]}")
        print("replay: base ready", file=sys.stderr, flush=True)
        predictions_by_id = dict(existing)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_run_case, scenario, base_dir / "case.db", scratch_root, args.debug): scenario for scenario in pending}
            for index, future in enumerate(as_completed(futures), 1):
                scenario = futures[future]
                prediction = future.result()
                predictions_by_id[scenario["scenario_id"]] = prediction
                with args.output.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(prediction, sort_keys=True) + "\n")
                    stream.flush()
                print(f"{index}/{len(pending)} {scenario['scenario_id']}: {prediction['outcome']}", file=sys.stderr, flush=True)
        predictions = [predictions_by_id[scenario["scenario_id"]] for scenario in public]
    args.output.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions), encoding="utf-8")
    revision_end = _source_digest()
    metadata = {"output": str(args.output), "cases": len(predictions),
                "errors": sum(bool(item.get("errors")) for item in predictions),
                "workers": args.workers, "source_sha256_start": revision_start,
                "source_sha256_end": revision_end, "stable_revision": revision_start == revision_end}
    args.output.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
