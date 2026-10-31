#!/usr/bin/env bash
# Mark a BUILD_STATUS.md task done and set the next task.
# Usage: scripts/mark_task.sh <done_id> <next_id>
set -euo pipefail
done_id="$1"; next_id="$2"
sed -i '' -E "s/^\| ${done_id//./\\.}( 👤)? \| \[[ ~!]\] \|/| ${done_id}\1 | [x] |/" BUILD_STATUS.md
sed -i '' -E "s/^\*\*Next task:\*\* .*/**Next task:** ${next_id}/" BUILD_STATUS.md
grep -E "^\| ${done_id//./\\.}( 👤)? \|" BUILD_STATUS.md | cut -c1-60
