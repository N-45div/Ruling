"""Desk commands.

    ruling-desk precedents          # build the precedent index from the archive (seeds 1-120)
"""

from __future__ import annotations

import argparse
import asyncio

from . import precedent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ruling-desk", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("precedents", help="build the precedent index from the archive")
    args = parser.parse_args(argv)
    if args.command == "precedents":
        count = asyncio.run(precedent.build_index())
        print(f"indexed {count} past checks at {precedent.INDEX}")


if __name__ == "__main__":
    main()
