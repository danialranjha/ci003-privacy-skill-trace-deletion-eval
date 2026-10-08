#!/usr/bin/env python3
"""Re-derive every stored arm's grade from its RAW artifacts, without touching the model.

The raw observer log and the host-captured native stream are the evidence; the grade is a function
of them. So when a grading rule is corrected, the honest move is to re-derive from the stored bytes
rather than re-run the model — re-running would produce NEW evidence and silently mix two designs
under one id.

Refuses to invent anything: an arm directory without its raw files is skipped, and an arm whose
stored `run.json` records no exit code is graded exactly as recorded (usually
`incomplete_evidence`), never as a pass.

    python3 harness/regrade.py --root results/runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import condition  # noqa: E402
from lab.classification import grade  # noqa: E402
from lab.run import (  # noqa: E402
    gateway_request_count,
    native_usage,
    observation_validity,
    read_jsonl,
    read_jsonl_bytes,
    skill_loaded,
)
from lab.tracepaths import session_id_from_stream  # noqa: E402


def regrade_arm(arm_dir: Path) -> dict | None:
    run_path = arm_dir / "run.json"
    if not run_path.exists():
        return None
    metadata = json.loads(run_path.read_text())
    arm = metadata["arm"]
    model = metadata["model"]
    observer_path = arm_dir / "observer.jsonl"
    if not observer_path.exists():
        # The archive ships `observer.events.jsonl`: the same events with home-root snapshot
        # CONTENT dropped (sha256/size kept). `reduce.py` proves the two grade identically.
        observer_path = arm_dir / "observer.events.jsonl"
    stream_path = arm_dir / "codex.jsonl"
    if not observer_path.exists() or not stream_path.exists():
        return None

    events, line_errors = read_jsonl(observer_path)
    stream, stream_errors = read_jsonl_bytes(stream_path.read_bytes())
    session_id = metadata.get("session_id") or session_id_from_stream("codex", stream)
    if session_id is None:
        stream_errors = [*stream_errors, "native_stream_had_no_thread_id"]

    validity = observation_validity(
        events,
        exit_code=metadata.get("exit_code"),
        status=metadata.get("status"),
        stream_errors=stream_errors,
        line_errors=line_errors,
    )
    argv = metadata.get("native_argv") or []
    graded = grade(
        arm=arm,
        session_id=session_id,
        stream=stream,
        events=events,
        validity=validity["validity"],
        native_argv=argv,
        stages=metadata.get("stages") or [],
        controller_intervened=bool(metadata.get("controller_intervened")),
        skill_loaded=skill_loaded(stream),
        task_completed=stream_path.exists(),
    )
    graded.update({
        "observation_validity": validity["validity"],
        "lifecycle_complete": validity["lifecycle_complete"],
        "observation_errors": validity["observation_errors"],
        "evidence_gaps": [{"reason": gap.get("reason"), "path": gap.get("path")}
                          for gap in validity["evidence_gaps"]],
        "exempted_post_unlink_gaps": [{"reason": gap.get("reason"), "path": gap.get("path")}
                                      for gap in validity["exempted_gaps"]],
        "stream_errors": validity["stream_errors"],
        "usage": native_usage(stream),
        "gateway_requests": gateway_request_count(arm_dir / "gateway.log"),
        "exit_code": metadata.get("exit_code"),
        "native_argv": argv,
        "model": model,
        "session_id": session_id,
        "observer_event_count": len(events),
        "native_event_count": len(stream),
        "regraded_from_raw_artifacts": True,
    })
    (arm_dir / "evidence.json").write_text(json.dumps(graded, indent=2, sort_keys=True) + "\n")
    return graded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/runs"))
    args = parser.parse_args(argv)

    changed = 0
    for trial_dir in sorted(args.root.glob("*/trial-*")):
        for arm in condition.ARMS:
            arm_dir = trial_dir / arm
            if not arm_dir.is_dir():
                continue
            before = (arm_dir / "evidence.json")
            old = before.read_text() if before.exists() else None
            graded = regrade_arm(arm_dir)
            if graded is None:
                print(f"skip (no raw artifacts): {trial_dir.relative_to(args.root)}/{arm}")
                continue
            new = before.read_text()
            if old != new:
                changed += 1
                print(f"regraded {trial_dir.relative_to(args.root)}/{arm}: "
                      f"{json.loads(old or '{}').get('outcome')} -> {graded['outcome']} "
                      f"success={graded['success']} basis={graded.get('deletion_action_basis')}")
    print(f"\n{changed} arm(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
