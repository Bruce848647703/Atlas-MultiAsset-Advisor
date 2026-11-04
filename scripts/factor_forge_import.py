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
    src.add_argument("--pdf", help="research-report PDF (needs PyMuPDF)")
    parser.add_argument("--source", default="", help="report / institution / date")
    parser.add_argument("--name", default="", help="override factor code name")
    parser.add_argument("--index", type=int, default=0,
                        help="which PDF brief candidate to use (default 0)")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="write into the Atlas factor store")
    parser.add_argument("--evaluate", action="store_true",
                        help="validate IC on the Atlas monthly asset panel")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    if not factor_forge.available():
        print("factor-forge unavailable: set FACTOR_FORGE_ROOT or place "
              "factor-forge next to Atlas.", file=sys.stderr)
        return 2

    if args.pdf:
        pack = factor_forge.forge_pdf(args.pdf, source=args.source, max_briefs=5)
        if args.json:
            print(json.dumps(pack, ensure_ascii=False, indent=1))
            return 0 if pack.get("available") else 1
        if not pack.get("available"):
            print(pack.get("reason", "PDF parse failed"), file=sys.stderr)
            return 1
        briefs = pack.get("briefs") or []
        if not briefs:
            print("no factor brief found in PDF", file=sys.stderr)
            return 1
        for i, b in enumerate(briefs):
            print(f"[{i}] {b['factor'].get('name')} "
                  f"({b['factor'].get('operator')}) score={b.get('score')}")
        out = briefs[min(max(args.index, 0), len(briefs) - 1)]
        if args.do_import:
            out = dict(out)
            out.update(factor_forge.import_factor(
                out["factor"], out["code"], source=args.source, overwrite=False))
    else:
        brief = args.text
        if args.file:
            with open(args.file, encoding="utf-8") as fh:
                brief = fh.read()
        if args.do_import:
            out = factor_forge.import_to_atlas(brief, source=args.source,
                                               name=args.name, overwrite=False)
        else:
            out = factor_forge.forge(brief, source=args.source, name=args.name)
        if args.evaluate and out.get("available"):
            out["atlas_eval"] = factor_forge.evaluate_on_atlas(
                out["factor"], out["code"])

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
    ev = out.get("atlas_eval")
    if ev:
        if ev.get("available"):
            print(f"  atlas IC  : mean={ev['mean_ic']:+.3f} ICIR={ev['icir']:+.2f} "
                  f"t={ev['t_stat']:+.2f} periods={ev['n_periods']}")
        else:
            print(f"  atlas IC  : unavailable — {ev.get('reason')}")
    if out.get("record"):
        print(f"  imported  : {out['record'].get('name')} (source=factor_forge)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())