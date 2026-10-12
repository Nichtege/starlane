"""Shared test helpers: a small, made-up vault and a config for it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aos.config import load_config

TODAY_ISO = "2026-10-09"  # Friday, ISO week 2026-W41

# The dashboard's interface-language runtime (tr, trc, trn, trm), cut from the page itself, for the Node tests that run
# slices of the script: without a document it falls back to English, so the slices behave like the bare template.
_DASH = (Path(__file__).resolve().parent.parent / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
_TRM = "const trm = msg => msg;"
JS_I18N = _DASH[_DASH.index("const I18N = (() => {"): _DASH.index(_TRM) + len(_TRM)] + "\n"

# Follows the default Conventions (English frontmatter keys, headings and folders).
FILES = {
    "index.md": """---
type: index
---
# Index
- [[Projects/alpha]] main project
- [[AI/brain-map]]
- [[Journal/2026-W41]] · [[Journal/2026-W40]]
- [[Resources/knowledge]]
- [[AI/Sessions/2026-10-08-alpha-test]]
""",
    "CLAUDE.md": "# Rules\nExample `[[Projects/<project-note>]]` inside code is ignored.\n",
    "README.md": "# Readme\n",
    "AI/brain-map.md": """---
type: overview
created: 2026-10-03
project: "[[Projects/alpha]]"
---
# Brain map

Part of [[Projects/alpha]]

- [[Projects/alpha]] · 1 KB · main project · always first
- [[Resources/knowledge]] · 40 KB · knowledge (size is wrong) · rarely
""",
    "Projects/alpha.md": """---
type: project
created: 2026-10-02
status: active
deadline: 2026-11-10
tags: [project, test]
---
# Alpha project
See [[Projects/alpha/schedule|Schedule]] and [[Resources/knowledge#Section|Knowledge]].
""",
    "Projects/alpha/schedule.md": """---
type: plan
created: 2026-10-02
---
# Schedule Alpha

## Week 0 · Fri 2.10 – Sun 4.10
- [x] Done
- [ ] Left over from week 0

## Week 1 · Mon 5.10 – Sun 11.10
- [ ] Finish the outline
- [ ] ~~Struck out~~
- **Tue 6.10. Quiz** (past)

## Week 2 · Mon 12.10 – Sun 18.10
- [ ] Write chapter 4
- **Tue 13.10. Team review** prepare
- Submission on 10.11.2026
""",
    "Journal/2026-W41.md": """---
type: week
created: 2026-10-05
projects: ["[[Projects/alpha]]"]
---
# Week 2026-W41

Part of [[Projects/alpha]]

## Weekly goal
- [ ] Outline is done

## Done
- Something

## Weekly review
_Goal reached?_
""",
    "Journal/2026-W40.md": """---
type: week
created: 2026-09-28
---
# Week 2026-W40

## Weekly goal
- [x] Start

## Weekly review
_Goal reached? Honest assessment._
""",
    "Resources/knowledge.md": """---
type: knowledge
created: 2026-10-01
---
# Knowledge
## Section
Text with [[Does not exist]] and `[[in code]]`.
""",
    "AI/Sessions/2026-10-08-alpha-test.md": """---
type: session
created: 2026-10-08
project: "[[Projects/alpha]]"
---
# Session Alpha

Part of [[Projects/alpha]]
""",
    "Inbox/README.md": "# Inbox\n\n- Raw idea to sort\n",
    "Ideas/README.md": "# Ideas\n\n## Quick list\n- 2026-10-01 Idea A\n- 2026-10-02 Idea B\n\n## Worked out\n",
}


def write_vault(root: Path, extra: dict[str, str] | None = None, remove: tuple[str, ...] = ()) -> Path:
    files = {**FILES, **(extra or {})}
    for rel in remove:
        files.pop(rel, None)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return root


class TempVaultCase(unittest.TestCase):
    """Creates a fresh vault + config in a temp folder for every test."""

    extra: dict[str, str] = {}
    remove: tuple[str, ...] = ()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.vault_dir = write_vault(self.root / "vault", self.extra, self.remove)
        self.cfg_path = self.root / "aos.toml"
        self.write_config()

    def write_config(self, routines: str | None = None) -> None:
        (self.root / "routines.toml").write_text(routines if routines is not None else DEFAULT_ROUTINES, encoding="utf-8")
        self.cfg_path.write_text(
            f'[vault]\npath = "{self.vault_dir.as_posix()}"\nname = "TestVault"\n'
            '[machine]\nname = "testpc"\n[paths]\ndata = "data"\nroutines = "routines.toml"\n'
            '[skills]\ndirs = ["skills"]\n',  # never the real ~/.claude/skills in tests
            encoding="utf-8",
        )
        self.cfg = load_config(self.cfg_path)


DEFAULT_ROUTINES = """
[[routine]]
id = "digest"
schedule = "daily 06:30"
command = "digest"
max_failures = 2
max_runs_per_day = 3

[[routine]]
id = "dashboard"
schedule = "every 15m"
command = "dashboard"

[[routine]]
id = "git-pull"
schedule = "every 10m"
command = "git-pull"
enabled = false

[[routine]]
id = "server-only"
schedule = "daily 07:00"
command = "mapcheck"
machine = "someone-else"
"""
