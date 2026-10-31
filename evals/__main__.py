"""CreditLens eval CLI.

uv run python -m evals validate [path]
uv run python -m evals run --suite golden --model claude-sonnet-5-5 --prompt-version v1
"""

import argparse
import os
import sys
from pathlib import Path

from evals.cases import DATASETS_DIR, GOLDEN_PATH, load_cases, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a case file and print counts")
    validate.add_argument("path", nargs="?", type=Path, default=GOLDEN_PATH)

    run = sub.add_parser("run", help="run a suite and write reports/<run_id>/")
    run.add_argument(
        "--suite", default="golden", help="dataset name in evals/datasets/ (without .jsonl)"
    )
    run.add_argument(
        "--model", default=None, help="model id (default: assistant.model in config.yaml)"
    )
    run.add_argument(
        "--prompt-version", default=None, help="system prompt version (default: config)"
    )
    run.add_argument(
        "--tags", default=None, help="only cases with ALL of these comma-separated tags"
    )
    run.add_argument("--max-cost-usd", type=float, default=None)
    run.add_argument("--concurrency", type=int, default=None)
    run.add_argument(
        "--no-cache", action="store_true", help="ignore and don't write the response cache"
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            cases = load_cases(args.path)
        except ValueError as exc:
            print(exc)
            return 1
        print(summarize(cases))
        return 0

    if args.command == "run":
        from assistant.config import load_config
        from evals.runner import BudgetExceeded, run_suite

        config = load_config()
        cases = load_cases(DATASETS_DIR / f"{args.suite}.jsonl")
        if args.tags:
            wanted = set(args.tags.split(","))
            cases = [c for c in cases if wanted <= set(c.tags)]
        if not cases:
            print("no cases to run")
            return 1
        in_ci = os.environ.get("CI") == "true"
        limit = args.max_cost_usd or (
            config.evals.max_cost_usd_ci if in_ci else config.evals.max_cost_usd_local
        )
        try:
            summary = run_suite(
                cases,
                suite=args.suite,
                model=args.model or config.assistant.model,
                prompt_version=args.prompt_version or config.assistant.system_prompt_version,
                max_cost_usd=limit,
                concurrency=args.concurrency,
                use_cache=not args.no_cache,
            )
        except BudgetExceeded as exc:
            print(f"refusing to run: {exc}")
            return 1
        print(f"run {summary['run_id']}: overall {summary['n_passed']}/{summary['n_cases']}")
        for cat, c in summary["categories"].items():
            print(f"  {cat:<18} {c['passed']:>3}/{c['n']:<3} {100 * c['pass_rate']:5.1f}%")
        cost = summary["cost"]
        measured, spent = cost["measured_total_usd"], cost["api_spend_this_run_usd"]
        print(f"  measured cost ${measured:.4f} (this run spent ${spent:.4f})")
        print(f"  report: {summary['out_dir']}/report.md")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
