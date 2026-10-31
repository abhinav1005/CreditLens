"""CreditLens eval CLI.

uv run python -m evals validate [path]
uv run python -m evals run --suite golden --model claude-sonnet-5-5 --prompt-version v1
"""

import argparse
import os
import sys
from pathlib import Path

from evals.cases import DATASETS_DIR, GOLDEN_PATH, Category, load_cases, summarize


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
    run.add_argument("--categories", default=None, help="only these comma-separated categories")
    run.add_argument("--max-cost-usd", type=float, default=None)
    run.add_argument("--concurrency", type=int, default=None)
    run.add_argument(
        "--no-cache", action="store_true", help="ignore and don't write the response cache"
    )
    run.add_argument(
        "--judge",
        choices=["off", "report", "gate"],
        default="off",
        help="LLM judge: off, report (shown only), gate (counts toward pass/fail)",
    )
    run.add_argument("--judge-version", default="v1")
    run.add_argument("--run-id", default=None, help="fixed run id (CI uses this to find the run)")
    run.add_argument(
        "--guardrails",
        choices=["on", "off"],
        default=None,
        help="override config.yaml guardrails.enabled (for on/off comparisons)",
    )

    pool = sub.add_parser(
        "build-pool", help="build the labeling pool from several model/prompt runs"
    )
    pool.add_argument("--models", default="claude-sonnet-5-5,claude-haiku-5-5")
    pool.add_argument("--prompts", default="v1,v1-degraded")
    pool.add_argument("--max-cost-usd", type=float, default=3.0)

    label = sub.add_parser("label", help="hand-label pool items (blind to judge and model)")
    label.add_argument("--labeler", required=True, help="your name, recorded on each label")
    label.add_argument("--batch", type=int, default=25)

    cal = sub.add_parser("calibrate-judge", help="judge vs human agreement per dimension")
    cal.add_argument("--judge-version", default="v1")
    cal.add_argument("--labeler", default=None, help="use only this labeler's labels")
    cal.add_argument("--max-cost-usd", type=float, default=3.0)

    cmp_ = sub.add_parser("compare", help="newly failing / newly passing cases between two runs")
    cmp_.add_argument("run_a")
    cmp_.add_argument("run_b")

    prom = sub.add_parser("promote", help="turn a logged transcript into a golden case")
    prom.add_argument("transcript_id")
    prom.add_argument("--category", required=True, choices=[c.value for c in Category])
    prom.add_argument("--note", required=True, help="what was wrong (becomes rubric_notes)")
    prom.add_argument("--must-not-contain", action="append", default=[])
    prom.add_argument("--must-contain", action="append", default=[])

    base = sub.add_parser("baseline", help="make a smoke run the committed CI baseline")
    base.add_argument("run_id")

    gate = sub.add_parser("gate", help="fail (exit 1) if a smoke run regressed vs the baseline")
    gate.add_argument("run_id")
    gate.add_argument("--comment-file", type=Path, default=None, help="write the PR comment here")

    gr = sub.add_parser("guardrail", help="precision/recall of one guardrail on its test set")
    gr.add_argument("name", choices=["pii", "injection", "compliance"])
    gr.add_argument("--split", choices=["dev", "test", "all"], default="test")

    e2e = sub.add_parser("guardrail-e2e", help="attack success with guardrails on vs off")
    e2e.add_argument("run_on")
    e2e.add_argument("run_off")
    e2e.add_argument("--label", required=True, help="scenario name, e.g. v1 or v1-degraded")

    lat = sub.add_parser("latency", help="sequential, fresh-call latency run per model")
    lat.add_argument("--models", required=True)
    lat.add_argument("--tags", default="smoke")
    lat.add_argument("--max-cost-usd", type=float, default=2.0)
    lat.add_argument("--prompt-caching", choices=["on", "off"], default=None)
    lat.add_argument("--label", default="", help="suffix for the output file, e.g. -cache-on")

    mx = sub.add_parser("matrix", help="quality x cost x latency table across models")
    mx.add_argument("--models", required=True)
    mx.add_argument("--max-cost-usd", type=float, default=3.0, help="limit per model")
    mx.add_argument("--judge", choices=["off", "report"], default="report")

    args = parser.parse_args(argv)

    if args.command == "latency":
        from evals.matrix import latency_run

        wanted = set(args.tags.split(","))
        cases = [c for c in load_cases() if wanted <= set(c.tags)]
        for model in args.models.split(","):
            pc = None if args.prompt_caching is None else args.prompt_caching == "on"
            r = latency_run(
                cases, model, max_cost_usd=args.max_cost_usd, label=args.label, prompt_caching=pc
            )
            print(
                f"{model}{args.label}: n={r['n']} total p50 {r['total_ms']['p50']:.0f}ms"
                f" p95 {r['total_ms']['p95']:.0f}ms ttft p50 {r['ttft_ms']['p50']}"
                f" spent ${r['cost_usd']:.3f}"
            )
        return 0

    if args.command == "matrix":
        from evals.matrix import COMPARISON, matrix

        matrix(
            load_cases(),
            args.models.split(","),
            max_cost_usd=args.max_cost_usd,
            judge_mode=args.judge,
        )
        print(COMPARISON.with_suffix(".md").read_text())
        return 0

    if args.command == "guardrail-e2e":
        from evals.guardrail_e2e import run_e2e

        print(run_e2e(args.run_on, args.run_off, args.label).read_text())
        return 0

    if args.command == "guardrail":
        from evals.guardrail_eval import run_guardrail_eval

        report, path = run_guardrail_eval(args.name, args.split)
        fp = report.get("negative_false_positive_rate", report.get("false_positive_rate"))
        print(f"{args.name} [{args.split}] recall {report['recall']} FP rate {fp} → {path}")
        return 0

    if args.command == "gate":
        from evals.compare import find_run
        from evals.gate import gate_run

        result = gate_run(find_run(args.run_id))
        print(result.markdown)
        if args.comment_file:
            args.comment_file.write_text(result.markdown)
        return 0 if result.passed else 1

    if args.command == "baseline":
        from evals.baseline import BASELINE_DIR, set_baseline

        meta = set_baseline(args.run_id)
        print(
            f"baseline = {meta['run_id']} "
            f"({meta['overall_pass_rate']:.1%} of {meta['n_cases']}) in {BASELINE_DIR}"
        )
        return 0

    if args.command == "compare":
        from evals.compare import compare_results, find_run, load_results, render_comparison

        a, b = find_run(args.run_a), find_run(args.run_b)
        print(render_comparison(compare_results(load_results(a), load_results(b)), a.name, b.name))
        return 0

    if args.command == "promote":
        from evals.promote import promote

        case = promote(
            args.transcript_id, args.category, args.note, args.must_not_contain, args.must_contain
        )
        print(f"added {case['id']} to golden.jsonl (validate with: python -m evals validate)")
        return 0

    if args.command == "calibrate-judge":
        from evals.calibrate import MAIN_DIMENSION, calibrate, write_report

        report = calibrate(args.judge_version, args.labeler, max_cost_usd=args.max_cost_usd)
        if report["n_judged"] == 0:
            print("no labeled items yet: run `python -m evals label --labeler NAME` first")
            return 1
        path = write_report(report)
        for group in ("test", "dev"):
            m = report["results"].get(group, {}).get(MAIN_DIMENSION)
            if m and m["n"]:
                print(
                    f"{group:<5} {MAIN_DIMENSION}: kappa {m['kappa']}"
                    f" CI {m['kappa_ci95']} (n={m['n']})"
                )
        print(f"report: {path}")
        return 0

    if args.command == "label":
        from evals.labeler import label_items, load_labels
        from evals.labeling import load_pool

        cases = {c.id: c for c in load_cases()}
        mine = [lab for lab in load_labels() if lab["labeler"] == args.labeler]
        n = label_items(
            load_pool(),
            cases,
            {lab["item_id"] for lab in mine},
            args.labeler,
            batch=args.batch,
            done_count=len(mine),
        )
        print(f"labeled {n} this session")
        return 0

    if args.command == "build-pool":
        from collections import Counter

        from evals.labeling import POOL_PATH, build_pool, write_pool

        items = build_pool(
            args.models.split(","), args.prompts.split(","), max_cost_usd=args.max_cost_usd
        )
        write_pool(items)
        print(f"wrote {len(items)} items to {POOL_PATH}")
        for (model, prompt), n in sorted(
            Counter((i["model"], i["prompt_version"]) for i in items).items()
        ):
            print(f"  {model:<22} {prompt:<12} {n}")
        return 0

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
        if args.categories:
            cats = set(args.categories.split(","))
            cases = [c for c in cases if c.category.value in cats]
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
                judge_mode=args.judge,
                judge_version=args.judge_version,
                tags=sorted(args.tags.split(",")) if args.tags else None,
                guardrails_enabled=None if args.guardrails is None else args.guardrails == "on",
                run_id=args.run_id,
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
