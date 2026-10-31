# Reviewing golden cases

Claude Code drafted every case in `evals/datasets/golden.jsonl` and marked them
`"authored_by": "llm_drafted"`. A drafted case doesn't count as reviewed until a human checks
it. Reports show a warning while any are unreviewed.

For each case:

1. **Is the question realistic?** Would a real user ask it this way?
2. **Are the expectations right?** For example, should this answer really have to call that
   tool, contain that word, or end with the disclaimer? Remove expectations that are too
   strict and add any that are missing.
3. **Are the numbers right?** `numeric_facts` come from the tool outputs (see
   `scripts/draft_golden_v1.py`). Spot-check a few with:
   `uv run python -c "from credit.tools.impl import call_tool; print(call_tool('get_utilization', {'profile_id': 'story_001'}))"`
4. **Edit the line in place**, then set `"authored_by": "llm_drafted_human_reviewed"`.
5. Run `uv run python -m evals validate`. It must pass, and the warning count should drop.

After the first case is reviewed, `scripts/draft_golden_v1.py` refuses to overwrite the file.
Edit `golden.jsonl` directly from then on.
