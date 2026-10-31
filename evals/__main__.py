"""CreditLens eval CLI.

uv run python -m evals validate [path]
"""

import argparse
import sys
from pathlib import Path

from evals.cases import GOLDEN_PATH, load_cases, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate a case file and print counts")
    validate.add_argument("path", nargs="?", type=Path, default=GOLDEN_PATH)
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            cases = load_cases(args.path)
        except ValueError as exc:
            print(exc)
            return 1
        print(summarize(cases))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
