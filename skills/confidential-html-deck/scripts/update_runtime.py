#!/usr/bin/env python3
"""Replace the DECK-RUNTIME block of an existing deck with the one from the template.

Usage:  python3 update_runtime.py path/to/deck.html [--template path/to/deck-template.html]
Only the text between <!-- DECK-RUNTIME:BEGIN --> and <!-- DECK-RUNTIME:END --> changes.
"""
import re
import sys
from pathlib import Path

PAT = re.compile(r"<!-- DECK-RUNTIME:BEGIN -->.*?<!-- DECK-RUNTIME:END -->", re.S)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    deck = Path(args[0])
    tpl = Path(args[args.index("--template") + 1]) if "--template" in args else Path(__file__).resolve().parent.parent / "assets" / "deck-template.html"
    new = PAT.search(tpl.read_text(encoding="utf-8"))
    src = deck.read_text(encoding="utf-8")
    if not new:
        sys.exit("Template has no runtime block.")
    if not PAT.search(src):
        sys.exit("Deck has no runtime block markers; add them around the runtime <style>/<script> first.")
    out = PAT.sub(lambda _: new.group(0), src, count=1)
    if out == src:
        print("Runtime already up to date.")
        return
    deck.write_text(out, encoding="utf-8")
    print(f"Runtime in {deck.name} replaced with the template version.")


if __name__ == "__main__":
    main()
