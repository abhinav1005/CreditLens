"""Add a 'Done' bullet and set 'Next' in the newest BUILD_LOG.md entry.

    uv run python scripts/log_done.py "M1.3: generator ..." "M1.4: story profiles"
"""

import re
import sys
from pathlib import Path

path = Path("BUILD_LOG.md")
done, next_step = sys.argv[1], sys.argv[2]
text = path.read_text()
head, sep, rest = text.partition("\n---\n\n")
top, _, older = rest.partition("\n## ")
top = top.replace("\n**Decisions:**", f"\n- {done}\n**Decisions:**", 1)
top = re.sub(r"\*\*Next:\*\* .*", f"**Next:** {next_step}", top, count=1)
path.write_text(head + sep + top + ("\n## " + older if older else ""))
