#!/usr/bin/env python3
"""bloat_lint — register enforcer (P3). Flag prose-bloat in docs.

Hedging, filler, pleasantries, emoji = bloat that hides the load-bearing line.
Heuristic, not a parser: flags lines for human/agent review, never auto-edits.

Severity:
  HARD (exit 1): emoji, pleasantries — never valid in this register.
  SOFT (advisory, exit 0): filler, hedging, weak qualifiers — often idiomatic
        ("just" = merely, "actually" = in reality). Reported for review.
  --strict : promote SOFT to HARD too (seed-file grade).

Definition docs that *list* the banned words (the style + philosophy + this
tool's own home) are exempt — they must contain the words to forbid them.

Usage: bloat_lint [ROOT] [--json] [--strict] [--exclude SUBSTR]
Exit: 0 clean (or soft-only) / 1 hard hit (or any hit under --strict).
Code blocks and inline code are skipped (technical terms exact).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

FILLER = ["just", "really", "basically", "actually", "simply", "very",
          "quite", "essentially", "obviously", "of course"]
HEDGE = ["i think", "i believe", "perhaps", "maybe", "sort of", "kind of",
         "it seems", "we might", "arguably", "in my opinion"]
PLEASANTRY = ["sure", "certainly", "happy to", "great question", "feel free",
              "as you can see", "please note that", "it's worth noting"]
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2700-\u27bf]"
)
WEAK = ["should probably", "you may want to", "might want to", "in order to"]

# Docs whose job is to LIST the banned words — exempt (like secret_scan skips self).
EXEMPT = ("copilot-communications-style.md", "copilot-engineering-philosophy.md")


def word_set_hits(low: str, words: list[str]) -> list[str]:
    hits = []
    for w in words:
        if " " in w:
            if w in low:
                hits.append(w)
        elif re.search(rf"\b{re.escape(w)}\b", low):
            hits.append(w)
    return hits


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    strict = "--strict" in argv
    exclude = lib.parse_exclude(argv)
    pos = lib.pos_args(argv)
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()

    flags: list[dict] = []
    scanned = 0
    for md in lib.walk_files(root, suffixes=(".md",), exclude=exclude):
        if any(e in str(md) for e in EXEMPT):
            continue
        scanned += 1
        in_code = False
        for n, line in enumerate(lib.read_text(md).splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            # strip inline code spans
            bare = re.sub(r"`[^`]*`", "", line)
            low = bare.lower()
            hard, soft = [], []
            soft += [f"filler:{w}" for w in word_set_hits(low, FILLER)]
            soft += [f"hedge:{w}" for w in word_set_hits(low, HEDGE)]
            hard += [f"pleasantry:{w}" for w in word_set_hits(low, PLEASANTRY)]
            if EMOJI.search(bare):
                hard.append("emoji")
            if strict:
                soft += [f"weak:{w}" for w in word_set_hits(low, WEAK)]
            if hard or soft:
                flags.append({"file": lib.rel(md), "line": n,
                              "hard": hard, "soft": soft})

    n_hard = sum(1 for f in flags if f["hard"])
    n_soft = sum(1 for f in flags if f["soft"] and not f["hard"])
    fail = (n_hard > 0) or (strict and flags)
    items = ([f"{f['file']}:{f['line']} {'HARD ' if f['hard'] else 'soft '}"
              f"{','.join(f['hard'] + f['soft'])}" for f in flags]
             if not json_mode else flags)
    lib.emit(items, json_mode, not fail,
             f"{scanned} md scanned, {n_hard} hard, {n_soft} advisory")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
