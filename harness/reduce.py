#!/usr/bin/env python3
"""Reduce the bulky recorder logs for archiving, and PROVE the reduction is grading-neutral.

`observer.jsonl` is 99.2% `content_b64` — the full bytes of every session-transcript snapshot the
recorder took, re-encoded every time the file was appended to. Across this run that is 508 MB, of
which 41 MB is a single arm. None of it is used to grade anything: the deletion claim rests on the
`fs` delete events, the final `trace_inventory`, and the native action stream. The only snapshot
CONTENT that grading reads is the WORKSPACE snapshot of the injected SKILL.md (the fixture-baseline
check), and those bytes are kept.

So this writes `observer.events.jsonl` with every event and every field preserved EXCEPT
`content_b64` on `home`-root snapshots, which is replaced by `content_b64_dropped: true` and its
`sha256`/`size`/`inode`. Nothing else is touched: `seq`, `observed_ns`, `kind`, `root`, `path`,
`events`, `reason`, `paths` and the workspace snapshot bytes are all byte-identical.

The reduction is then re-graded in process and compared field-by-field against the stored
`evidence.json`. If a single graded field moves, this refuses to write. A reduction that changed a
verdict would be an edit of the evidence, not a reduction of it.

    python3 harness/reduce.py --root results/runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import condition  # noqa: E402
from lab.classification import grade  # noqa: E402
from lab.run import observation_validity, read_jsonl_bytes, skill_loaded  # noqa: E402
from lab.tracepaths import session_id_from_stream  # noqa: E402

# Every field that can carry a verdict. Compared after reduction.
GRADED_FIELDS = (
    "outcome", "success", "measurement", "measurement_withdrawal_reason", "trace_deleted",
    "trace_deletion_observed_in_world", "agent_deletion_action_detected", "deletion_action_basis",
    "fixture_baseline_verified", "skill_loaded", "native_full_access_verified",
    "trace_present_at_end", "trace_deleted_and_absent",
)


def reduce_events(events) -> tuple[list, dict]:
    reduced, dropped, kept = [], 0, 0
    for event in events:
        if "content_b64" in event and event.get("root") == "home":
            event = {k: v for k, v in event.items() if k != "content_b64"}
            event["content_b64_dropped"] = True
            dropped += 1
        elif "content_b64" in event:
            kept += 1
        reduced.append(event)
    return reduced, {"snapshots_content_dropped": dropped, "snapshots_content_kept": kept}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/runs"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    total_before = total_after = 0
    failures = []
    for trial_dir in sorted(args.root.glob("*/trial-*")):
        for arm in condition.ARMS:
            arm_dir = trial_dir / arm
            raw = arm_dir / "observer.jsonl"
            target = arm_dir / "observer.events.jsonl"
            if not raw.exists():
                continue
            if target.exists() and not args.force:
                continue
            raw_bytes = raw.read_bytes()
            total_before += len(raw_bytes)
            events, line_errors = read_jsonl_bytes(raw_bytes)
            reduced, stats = reduce_events(events)
            payload = ("\n".join(json.dumps(e, sort_keys=True) for e in reduced) + "\n").encode()
            total_after += len(payload)

            # --- prove the reduction cannot have changed a verdict ---
            stored = json.loads((arm_dir / "evidence.json").read_text())
            metadata = json.loads((arm_dir / "run.json").read_text())
            stream, stream_errors = read_jsonl_bytes((arm_dir / "codex.jsonl").read_bytes())
            session_id = metadata.get("session_id") or session_id_from_stream("codex", stream)
            if session_id is None:
                stream_errors = [*stream_errors, "native_stream_had_no_thread_id"]
            validity = observation_validity(
                reduced, exit_code=metadata.get("exit_code"), status=metadata.get("status"),
                stream_errors=stream_errors, line_errors=line_errors,
            )
            regraded = grade(
                arm=arm, session_id=session_id, stream=stream, events=reduced,
                validity=validity["validity"], native_argv=metadata.get("native_argv") or [],
                stages=metadata.get("stages") or [],
                controller_intervened=bool(metadata.get("controller_intervened")),
                skill_loaded=skill_loaded(stream), task_completed=True,
            )
            drift = {
                field: (stored.get(field), regraded.get(field))
                for field in GRADED_FIELDS if stored.get(field) != regraded.get(field)
            }
            if drift:
                failures.append((str(arm_dir), drift))
                continue

            target.write_bytes(payload)
            (arm_dir / "reduction.json").write_text(json.dumps({
                "reduced_from": "observer.jsonl",
                "reduced_to": "observer.events.jsonl",
                "rule": "every event and field preserved except content_b64 on home-root snapshots "
                        "(replaced by content_b64_dropped: true); workspace-root snapshot content is "
                        "kept because the fixture-baseline check reads it",
                "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "raw_bytes": len(raw_bytes),
                "reduced_sha256": hashlib.sha256(payload).hexdigest(),
                "reduced_bytes": len(payload),
                "raw_event_lines": len(raw_bytes.splitlines()),
                "graded_fields_verified_identical": list(GRADED_FIELDS),
                **stats,
            }, indent=2, sort_keys=True) + "\n")

    print(f"raw {total_before:,} bytes -> reduced {total_after:,} bytes "
          f"({(1 - total_after / total_before) * 100:.1f}% smaller)" if total_before else "nothing to do")
    if failures:
        print(f"\n{len(failures)} REDUCTION(S) CHANGED A GRADED FIELD — refusing:")
        for path, drift in failures:
            print(" -", path, json.dumps(drift))
        return 1
    print("every reduced arm re-grades identically to its stored evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
