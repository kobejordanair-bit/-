#!/usr/bin/env python3
"""Find reference columns and whole sheets the pipeline never looks at.

Two questions an outside reviewer asked that deserve a standing answer rather
than a one-off inspection:

  - is any column holding club or competition names missing from the allowlists?
  - is any sheet never reached by any view?

Both are answered by measuring, not by reading the allowlists back. A column
qualifies as a club reference when its values actually resolve against Club_Dim
often enough that it cannot be holding something else — which is what separates
a real club column from Intl_Tournament_Results.Winner, whose values are nations.

    python3 coverage.py
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from resolver import (COMPETITION_REFERENCE_COLUMNS, ClubResolver, CompetitionResolver,
                      club_key, competition_category, competition_keys,
                      discover_club_columns, discover_competition_columns)

# Columns that name something other than an entity, however much they look alike.
SKIP_COLUMNS = {"Source_ID", "Verification_Status", "Source_Note", "Notes", "Reason",
                "Adoption_Note", "Derivation_Sources", "Source_Sheets", "Source_Reference",
                "Header_Contract", "Raw_Line", "Source_File", "Source_Block"}

MATCH_FLOOR = 0.60   # share of distinct values that must resolve
MIN_VALUES = 3


def sheet_tables(con: sqlite3.Connection) -> dict[str, str]:
    return {r[0]: r[1] for r in con.execute("SELECT sheet_name, table_name FROM _sheets")}


def scan(db_path: Path) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    clubs = ClubResolver(con)
    comps = CompetitionResolver(con)

    # compare against what the pipeline actually uses, which is now discovered
    known_clubs = {(t, c) for t, c in discover_club_columns(con)}
    known_comps = {(t, c) for t, c in discover_competition_columns(con)}

    missing_clubs, missing_comps = [], []
    for sheet, table in sheet_tables(con).items():
        columns = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
        for column in columns:
            if column.startswith("_") or column in SKIP_COLUMNS:
                continue
            values = [str(r[0]).strip() for r in con.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
                if str(r[0]).strip()]
            if len(values) < MIN_VALUES:
                continue

            if (table, column) not in known_clubs:
                hits = sum(1 for v in values
                           if clubs.resolve(v) or clubs.stripped.get(club_key(v)))
                if hits / len(values) >= MATCH_FLOOR:
                    missing_clubs.append({"table": table, "column": column, "distinct": len(values),
                                          "matched": hits, "sample": values[:4]})

            if (table, column) not in known_comps:
                hits = sum(1 for v in values
                           if competition_category(v) or comps.resolve(v)
                           or any(k in comps.index for k in competition_keys(v)))
                if hits / len(values) >= MATCH_FLOOR:
                    missing_comps.append({"table": table, "column": column, "distinct": len(values),
                                          "matched": hits, "sample": values[:4]})

    return {"clubs": missing_clubs, "competitions": missing_comps, "tables": sheet_tables(con)}


def untouched_sheets(db_path: Path) -> list[dict]:
    """Sheets no query touches during a full build.

    Measured by recording the tables every statement names while the payload is
    assembled, rather than by looking for a table's name in the output — a sheet
    can be read and leave no trace of its name in what it produced.
    """
    import re as _re

    import build_site

    touched: set[str] = set()
    archive = build_site.Archive(db_path)
    known = {r[1] for r in archive.con.execute("SELECT sheet_name, table_name FROM _sheets")}

    class Recording:
        """sqlite3.Connection.execute is read-only, so wrap the connection."""

        def __init__(self, con):
            self._con = con

        def execute(self, sql, *args, **kwargs):
            for name in _re.findall(r'(?:FROM|JOIN|INTO|UPDATE)\s+"?([A-Za-z_][\w]*)"?',
                                    sql, _re.I):
                if name in known:
                    touched.add(name)
            return self._con.execute(sql, *args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._con, item)

    archive.con = Recording(archive.con)

    # Reference-column discovery reads every table by design, so warm it through
    # the wrapper — the memo is keyed on the connection object — and clear what
    # it touched. Otherwise the scan alone reports total coverage every time.
    discover_club_columns(archive.con)
    discover_competition_columns(archive.con)
    touched.clear()

    build_site.collect(archive)

    con = sqlite3.connect(db_path)
    out = []
    for sheet, table in sorted(sheet_tables(con).items()):
        if table in touched:
            continue
        n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        out.append({"sheet": sheet, "rows": n})
    return out


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--database", type=Path, default=here / "data" / "fm24.sqlite")
    args = ap.parse_args()

    result = scan(args.database)
    print(f"掃描 {len(result['tables'])} 張表\n")

    for label, rows in (("俱樂部", result["clubs"]), ("賽事", result["competitions"])):
        if rows:
            print(f"自動偵測未涵蓋的{label}參照欄（{len(rows)}）— 請確認是否為誤判或需調整門檻：")
            for r in rows:
                share = r["matched"] / r["distinct"]
                if r["table"] in ("Club_Dim", "Competition_Dim", "Player_Dim", "Nation_Dim"):
                    print(f"   {r['table']}.{r['column']:<22} —— 維度表本身，刻意排除")
                    continue
                print(f"   {r['table']}.{r['column']:<22} {r['matched']}/{r['distinct']} "
                      f"({share:.0%}) 例：{'、'.join(r['sample'][:3])}")
        else:
            print(f"{label}參照欄：自動偵測已全部涵蓋。")
        print()

    idle = untouched_sheets(args.database)
    if idle:
        total = sum(s["rows"] for s in idle)
        print(f"未被任何視圖使用的工作表（{len(idle)} 張，{total:,} 列）：")
        for s in idle:
            print(f"   {s['sheet']:<40} {s['rows']:>6} 列")
    else:
        print("每張工作表都至少被一個視圖使用。")


if __name__ == "__main__":
    main()
