# Factor library

Atlas has two complementary factor layers:

1. **Knowledge base** (`examples/factor_library_sample/`): page-level JSON
   documents parsed into a searchable catalog.
2. **Persistent store** (`data/factor_store.json`): every imported, collected,
   learned or forged factor with provenance and optional IC.

## Bundled knowledge base

The bundled sample currently ships **29 factors across 15 categories**:

```text
examples/factor_library_sample/
  2026/
    page_0003.json
    page_0004.json
    page_0100.json
    page_0200.json
```

Each page follows the extraction format:

```json
{
  "year": 2026,
  "page_no": 200,
  "calendar_month": "2026-02",
  "signals": [
    {
      "signal_name_cn": "现金流收益率",
      "signal_type_cn": "估值因子",
      "manual_factor_name": "cashflow_yield",
      "formula": "CFO / MarketCap",
      "variables": [],
      "raw_text": "...与未来收益正相关...",
      "confidence_note": "清晰"
    }
  ]
}
```

`loader.py` deduplicates by name, indexes categories, flags high-frequency
families and mines return direction from phrases such as `正相关` / `负相关`.
It never fabricates a direction when the rationale is ambiguous.

## Persistent store

`factor_store.py` keeps a single JSON list. Writes are serialized with an
advisory file lock and replaced atomically. A corrupt payload is quarantined as
`factor_store.json.corrupt-<timestamp>` rather than overwritten.

Each record carries:

```json
{
  "name": "cashflow_yield",
  "name_cn": "现金流收益率",
  "category": "估值因子",
  "formula": "CFO / MarketCap",
  "direction": 1,
  "source": "knowledge_base",
  "added_date": "2026-11-20",
  "ic": null,
  "rationale": "..."
}
```

Sources currently include `knowledge_base`, `broker_report`, `empirical` and
`factor_forge`. Learned factors may carry `ic` and generated `code`.

## Factor lens

`lens.py` ranks the 26-asset universe with a missing-aware composite:

- return proxies: momentum (+), short reversal (−), low volatility (−),
  drawdown (−);
- live ETF factors: valuation percentile (−), liquidity (+), money flow (+).

Assets without live data keep only the return proxies and renormalize. The
result includes factor coverage and provenance; it is research evidence, not an
optimizer input.

## Updating the library

```bash
# show the current store
python scripts/import_factor_library.py --stats

# import the bundled sample (adds missing names only)
python scripts/import_factor_library.py --dir examples/factor_library_sample

# import a full external library
ATLAS_FACTOR_DIR=/path/to/library python scripts/import_factor_library.py \
  --dir "$ATLAS_FACTOR_DIR"
```

Equivalent API:

```python
from invest_agent.factors.factor_store import import_knowledge_base
from invest_agent.factors.loader import default_data_dir

import_knowledge_base(default_data_dir())
```

Existing records are never overwritten by import (`overwrite=False`), so
measured IC and forged code survive a library refresh.

## Adding a factor

1. Add it to the appropriate `page_*.json` with a formula and rationale that
   states the expected direction.
2. Run `python scripts/import_factor_library.py --dir examples/factor_library_sample`.
3. If it is computable from available data, add a lens proxy and tests.
4. If it needs daily/fundamental data, leave it as knowledge and list it under
   the skipped families rather than faking values.

## Validation

- Loader deduplication, category grouping, direction mining and missing
  directories.
- Store concurrency, corrupt-store quarantine, atomic writes and bulk-import
  single-write behavior.
- Lens coverage, missing-data renormalization and live-factor provenance.
- Custom forged factors are separate from the knowledge catalog; they are
  evaluated only when their required fields exist.

## Limitations

- The bundled library is a curated sample, not the full 1,000+ external
  library.
- Direction mining is phrase-based; ambiguous rationales stay `0`.
- Fundamental, analyst and high-frequency factors are knowledge-only for the
  monthly multi-asset universe.
- IC estimates depend on the available history and are not a guarantee of
  future performance.