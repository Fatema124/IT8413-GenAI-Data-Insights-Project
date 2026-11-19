"""Look at the raw files before preparing them.

    python -m src.pipeline.inspect_raw

Prints each file's columns (after header clean-up), a few rows, and how the
pipeline mapped the columns. Run this first after downloading the sources;
if a mapping is wrong, fix it in config.COLUMN_OVERRIDES.
"""
from __future__ import annotations

import pandas as pd

from . import config, load


def main() -> None:
    for key in ("D1", "D2"):
        path = config.RAW_DIR / config.RAW_FILES[key]
        print(f"\n=== {key}: {path.name} ===")
        if not path.exists():
            print("  not found")
            continue
        df = load.read_csv_any(path)
        print(f"  rows: {len(df)}   columns: {list(df.columns)}")
        print(df.head(3).to_string(index=False))
        required = ("code", "name", "value") if key == "D1" else ("name", "value", "nationality")
        try:
            print("  mapping:", load.resolve_columns(df, key, required))
        except load.SourceFormatError as exc:
            print("  MAPPING PROBLEM:", exc)
    path = config.RAW_DIR / config.RAW_FILES["D3"]
    print(f"\n=== D3: {path.name} ===")
    if path.exists():
        book = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        for name, frame in book.items():
            first = " | ".join(str(v) for v in frame.head(3).to_numpy().ravel() if pd.notna(v))[:120]
            print(f"  sheet '{name}': {frame.shape}  {first}")
    else:
        print("  not found")


if __name__ == "__main__":
    main()
