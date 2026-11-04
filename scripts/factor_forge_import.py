#!/usr/bin/env python3
"""Factor Forge CLI: research brief -> Factor JSON -> code -> Atlas factor store.

Examples:
    python scripts/factor_forge_import.py --file /path/to/brief.txt --source "某券商 2026"
    python scripts/factor_forge_import.py --file brief.txt --import
    python scripts/factor_forge_import.py --text "资本利得突出量..." --name CGO --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from invest_agent.integrations import factor_forge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="text file containing the factor brief")
    src.add_argument("--text", help="factor brief inline")
    parser.add_argument("--source", default="", help="report / institution / date")
    parser.add_argument("--name", default="", help="override factor code name")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="write into the Atlas factor store")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    if not factor_forge.available():
        print("factor-forge unavailable: set FACTOR_FORGE_ROOT or place "
              "factor-forge next to Atlas.", file=sys.stderr)
        return 2

    brief = args.text
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            brief = fh.read()

    if args.do_import:
        out = factor_forge.import_to_atlas(brief, source=args.source,
                                           name=args.name, overwrite=False)
    else:
        out = factor_forge.forge(brief, source=args.source, name=args.name)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if out.get("available") else 1
    if not out.get("available"):
        print(out.get("reason", "forge failed"), file=sys.stderr)
        return 1

    fac = out["factor"]
    print(f"{fac.get('name')} ({fac.get('name_cn')})")
    print(f"  category  : {fac.get('category')}")
    print(f"  operator  : {fac.get('operator')}")
    print(f"  direction : {fac.get('direction'):+d} {fac.get('direction_note', '')}")
    print(f"  formula   : {fac.get('formula', '')[:120]}")
    print(f"  fields    : "
          f"{[v.get('data_field') for v in fac.get('variables', []) if v.get('data_field')]}")
    val = out.get("validation") or {}
    if val:
        print(f"  validate  : {'PASS' if val.get('ok') else 'WARN'} — {val.get('message')}")
    if out.get("record"):
        print(f"  imported  : {out['record'].get('name')} (source=factor_forge)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())