#!/usr/bin/env python3
"""FM24 World Master workbook -> SQLite.

The workbook is a star-schema warehouse that happens to live in .xlsx: dimension
sheets (Player_Dim, Club_Dim, ...), fact sheets carrying Source_ID /
Verification_Status / Observation_ID lineage, and quality sheets (Data_Issues,
Award_Resolution_Status). This script mirrors it into SQLite 1:1 so downstream
tools can query instead of scrolling.

Usage:
    python3 etl.py <workbook.xlsx> [-o fm24.sqlite]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import openpyxl

# Sheets whose header row sits somewhere other than row 1 would go here; the
# v6.4.0 workbook is uniform, so the map is empty but the hook stays.
HEADER_ROW_OVERRIDES: dict[str, int] = {}

RESERVED = {"index", "order", "group", "table", "select", "from", "where"}


def slug_column(name: str, position: int, seen: set[str]) -> str:
    """Make a SQL-safe column name, keeping CJK headers addressable."""
    if name is None or str(name).strip() == "":
        base = f"col_{position}"
    else:
        text = unicodedata.normalize("NFKC", str(name)).strip()
        base = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", text).strip("_")
        if not base or base[0].isdigit():
            base = f"c_{base}" if base else f"col_{position}"
    if base.lower() in RESERVED:
        base = f"{base}_"
    candidate, n = base, 2
    while candidate.lower() in seen:
        candidate = f"{base}_{n}"
        n += 1
    seen.add(candidate.lower())
    return candidate


def slug_table(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name)).strip()
    return re.sub(r"[^0-9A-Za-z一-鿿]+", "_", text).strip("_")


def normalise(value):
    """Excel cell -> SQLite value. Dates become ISO strings, blanks become NULL."""
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()[:10] if not isinstance(value, dt.datetime) else value.isoformat(sep=" ")
    if isinstance(value, str):
        cleaned = value.replace(" ", " ").strip()
        return cleaned or None
    return value


def load(workbook_path: Path, db_path: Path) -> None:
    print(f"reading {workbook_path.name} ...", file=sys.stderr)
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)

    # Imported observations live in Import_* tables and are NOT in the workbook,
    # so a rebuild must carry them across rather than drop them with everything else.
    carried = []
    if db_path.exists():
        old = sqlite3.connect(db_path)
        try:
            names = [r[0] for r in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Ingest|_%' ESCAPE '|'")]
            for name in names:
                ddl = old.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0]
                rows = list(old.execute(f'SELECT * FROM "{name}"'))
                cols = [d[0] for d in old.execute(f'SELECT * FROM "{name}" LIMIT 0').description]
                carried.append((name, ddl, cols, rows))
        except sqlite3.Error:
            carried = []
        finally:
            old.close()
        db_path.unlink()

    con = sqlite3.connect(db_path)
    # PRAGMAs first: the carry-over inserts below open a transaction, and a
    # safety-level change inside one is an error.
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    for name, ddl, cols, rows in carried:
        con.execute(ddl)
        if rows:
            marks = ", ".join("?" * len(cols))
            con.executemany(f'INSERT INTO "{name}" VALUES ({marks})', rows)
        print(f"  carried over {name:<30} {len(rows):>6} imported rows", file=sys.stderr)
    con.execute(
        """CREATE TABLE _sheets (
               sheet_name TEXT PRIMARY KEY,
               table_name TEXT NOT NULL,
               row_count  INTEGER NOT NULL,
               columns    TEXT NOT NULL
           )"""
    )

    total_rows = 0
    for ws in wb.worksheets:
        table = slug_table(ws.title)
        header_row = HEADER_ROW_OVERRIDES.get(ws.title, 1)

        rows = ws.iter_rows(values_only=True)
        header = None
        for i, row in enumerate(rows, start=1):
            if i == header_row:
                header = row
                break
        if header is None:
            print(f"  skip {ws.title}: no header", file=sys.stderr)
            continue

        seen: set[str] = set()
        columns = [slug_column(h, i, seen) for i, h in enumerate(header)]
        if not columns:
            continue

        # Every column is TEXT on purpose: the workbook mixes "0(2)" with 2 and
        # "85%" with 0.85, and coercing here would silently destroy source form.
        ddl = ", ".join(f'"{c}" TEXT' for c in columns)
        con.execute(f'CREATE TABLE "{table}" ({ddl}, _row INTEGER)')

        placeholders = ", ".join("?" * (len(columns) + 1))
        insert = f'INSERT INTO "{table}" VALUES ({placeholders})'
        batch, count = [], 0
        for excel_row, row in enumerate(rows, start=header_row + 1):
            values = [normalise(v) for v in row[: len(columns)]]
            values += [None] * (len(columns) - len(values))
            if all(v is None for v in values):
                continue
            batch.append([None if v is None else str(v) for v in values] + [excel_row])
            count += 1
            if len(batch) >= 2000:
                con.executemany(insert, batch)
                batch.clear()
        if batch:
            con.executemany(insert, batch)

        con.execute(
            "INSERT INTO _sheets VALUES (?,?,?,?)",
            (ws.title, table, count, "\t".join(str(h) if h is not None else "" for h in header)),
        )
        total_rows += count
        print(f"  {ws.title:<38} {count:>6} rows", file=sys.stderr)

    # Indexes on the join keys that every downstream query reaches for.
    for table, column in [
        ("Player_Club_Season_Totals", "Player_ID"),
        ("Player_Club_Competition_Stats", "Player_ID"),
        ("Player_National_Team_Stats", "Player_ID"),
        ("Player_League_Career", "Player_ID"),
        ("Canonical_Award_Facts", "Player_ID"),
        ("Record_Identity_Map", "Entity_ID"),
        ("World_Timeline", "Period_ID"),
        ("Domestic_League_Standings", "Season"),
    ]:
        try:
            con.execute(f'CREATE INDEX "ix_{table}_{column}" ON "{table}" ("{column}")')
        except sqlite3.OperationalError:
            pass  # sheet or column absent in this workbook revision

    con.commit()
    con.close()
    wb.close()
    print(f"\nwrote {db_path} ({total_rows:,} rows)", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workbook", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path(__file__).parent / "data" / "fm24.sqlite")
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    load(args.workbook, args.output)


if __name__ == "__main__":
    main()
