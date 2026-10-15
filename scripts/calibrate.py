"""Print the engine's per-match aggregates against the public targets.

Usage: uv run python scripts/calibrate.py [first_seed] [count]
Defaults to the 200 development seeds 5001-5200 (see docs/eval-plan.md).
"""

import sys

from ruling.sim.calibration import TARGETS, run


def main() -> None:
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    means = run(range(first, first + count))
    print(f"{'aggregate':14} {'mean':>8}  {'target':>13}  status  basis")
    for key, value in means.items():
        target = TARGETS[key]
        status = "ok" if target.low <= value <= target.high else "MISS"
        basis = target.note if target.sourced else "estimate (no single public figure)"
        print(f"{key:14} {value:8.3f}  {target.low:>5} - {target.high:<5}  {status:6}  {basis}")


if __name__ == "__main__":
    main()
