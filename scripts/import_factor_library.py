#!/usr/bin/env python3
"""Import a factor knowledge-base directory into the Atlas factor store.

The loader accepts the page-level JSON layout used by the bundled sample:
``<root>/<year>/page_*.json``. Existing factors are kept; only missing names
are added, with ``source=knowledge_base``.

Examples
--------
python scripts/import_factor_library.py --stats
python scripts/import_factor_library.py --dir "$ATLAS_FACTOR_DIR"
python scripts/import_factor_library.py --dir examples/factor_library_sample
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.factors.factor_store import (  # noqa: E402
    import_knowledge_base,
    stats,
)
from invest_agent.factors.loader import default_data_dir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=None,
                        help="factor library root (default: configured/bundled sample)")
    parser.add_argument("--limit", type=int, default=None,
                        help="import at most N factors")
    parser.add_argument("--stats", action="store_true", help="show store stats and exit")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    try:
        if args.stats:
            payload = stats()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"factors: {payload['total']}")
                for source, count in sorted(payload["by_source"].items()):
                    print(f"  {source:16} {count}")
                print(f"  with IC          {payload['with_ic']}")
            return 0

        root = args.dir or default_data_dir()
        imported = import_knowledge_base(root, limit=args.limit)
        payload = {"directory": root, "scanned": imported, "stats": stats()}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"directory: {root}")
            print(f"scanned: {imported}")
            print(f"store factors: {payload['stats']['total']}")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())