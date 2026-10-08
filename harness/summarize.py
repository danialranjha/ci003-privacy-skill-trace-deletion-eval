#!/usr/bin/env python3
"""Rebuild every `trial.json` from the stored per-arm `evidence.json` files.

`sweep.py` writes the trial summary as it runs; `regrade.py` can then change a grade from raw
artifacts. This keeps the summary derived from the evidence rather than from the run's memory of it.

    python3 harness/summarize.py --root results/runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweep import summarize_trial  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/runs"))
    args = parser.parse_args(argv)

    for model_dir in sorted(path for path in args.root.iterdir() if path.is_dir()):
        for trial_dir in sorted(model_dir.glob("trial-*")):
            trial = int(trial_dir.name.split("-", 1)[1])
            model = model_dir.name.replace("__", "/", 1)
            arms = {arm: trial_dir / arm for arm in ("attack", "benign", "control")}
            row = summarize_trial(model, trial, arms)
            (trial_dir / "trial.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
            if row["error_class"]:
                (trial_dir / "provider_error.json").write_text(
                    json.dumps({"error_class": row["error_class"],
                                "detail": row["infrastructure_failures"]}, indent=2) + "\n"
                )
            print(f"{model_dir.name}/{trial_dir.name}: attack={row['attack_outcome']} "
                  f"benign={row['benign_outcome']} control={row['control_outcome']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
