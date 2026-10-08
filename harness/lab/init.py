"""Populate a fresh home + workspace volume from inside a no-network initializer container.

Runs as root ONLY to create the fixture and hand it to uid 1000; it never touches the agent's
trace tree (nothing exists yet) and it never runs while the agent does.
"""

import argparse
import os
from pathlib import Path

from . import condition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=condition.ARMS)
    args = parser.parse_args()

    home = Path("/home/agent")
    workspace = Path("/workspace")
    for root in (home, workspace, Path("/relay")):
        root.mkdir(parents=True, exist_ok=True)
        os.chown(root, 1000, 1000)

    condition.initialize(home, workspace, args.arm)

    for path in sorted(home.rglob("*")) + sorted(workspace.rglob("*")):
        os.chown(path, 1000, 1000)
    print(f"initialized arm={args.arm}", flush=True)


if __name__ == "__main__":
    main()
