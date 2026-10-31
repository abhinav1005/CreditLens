#!/usr/bin/env bash
# Mark a BUILD_STATUS.md task done and set the next task.
# Usage: scripts/mark_task.sh <done_id> "<next task text>"
set -euo pipefail
exec ~/.local/bin/uv run python - "$1" "$2" <<'PY'
import re, sys
from pathlib import Path
done_id, next_text = sys.argv[1], sys.argv[2]
p = Path("BUILD_STATUS.md")
s = p.read_text()
pattern = re.compile(r"^\| " + re.escape(done_id) + r"( 👤)? \| \[[ ~!]\] \|", re.M)
s, n = pattern.subn(lambda m: f"| {done_id}{m.group(1) or ''} | [x] |", s)
if n != 1 and not re.search(r"^\| " + re.escape(done_id) + r"( 👤)? \| \[x\] \|", s, re.M):
    sys.exit(f"task {done_id} not found")
s = re.sub(r"^\*\*Next task:\*\* .*$", lambda m: f"**Next task:** {next_text}", s, count=1, flags=re.M)
p.write_text(s)
print(f"{done_id} done; next: {next_text}")
PY
