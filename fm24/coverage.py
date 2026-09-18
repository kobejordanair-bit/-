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

from resolver import (COMPETITION_REFERENCE_COLUMNS, ClubResolver, CompetitionResolver, require_script_conversion,
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
    ap.add_argument("--allow-degraded", action="store_true",
                    help="承認簡繁轉換不可用，仍以不完整的結果執行")
    args = ap.parse_args()
    degraded = not require_script_conversion(args.allow_degraded)
    if degraded:
        print("警告：簡繁轉換未啟用，以下覆蓋率數字偏高且不可與完整環境比較。\n")

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

    from table_roles import (ADOPTED, IDENTITY, PENDING_INTEGRATION, PRESERVED, PROVENANCE,
                             ROLE_LABELS, ROLE_MEANINGS, SURFACED, use_of)

    unread = {x["sheet"] for x in untouched_sheets(args.database)}
    con = sqlite3.connect(args.database)
    tables = sheet_tables(con)

    print("每張工作表的用途")
    print("用途是宣告的，不是掃出來的：一張表可能只被讀取球會欄做身分比對，")
    print("它的進球、助攻、評分從未出現在任何讀者頁。標籤可重疊。\n")

    tagged: dict[str, list] = {r: [] for r in (ADOPTED, SURFACED, IDENTITY, PROVENANCE, PRESERVED)}
    contradictions = []
    for sheet, table in sorted(tables.items()):
        u = use_of(table)
        rows = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        read = sheet not in unread
        for role in u.sorted_roles:
            tagged[role].append((sheet, rows, u))
        if PRESERVED not in u.roles and not read:
            contradictions.append((sheet, "宣告為已使用，但建置過程未讀取"))
        if PRESERVED in u.roles and read:
            contradictions.append((sheet, "建置過程有讀取，但未宣告用途"))

    for role in (ADOPTED, SURFACED, IDENTITY, PROVENANCE, PRESERVED):
        items = tagged[role]
        if not items:
            continue
        rows = sum(r for _, r, _ in items)
        print(f"── {ROLE_LABELS[role]}　{len(items)} 張　（這些表共含 {rows:,} 列，"
              "不代表全部已採用）")
        print(f"   {ROLE_MEANINGS[role]}")
        for sheet, n, u in items:
            pending = PENDING_INTEGRATION.get(sheet)
            tag = f" [{pending[0]}]" if pending else ""
            via = "" if u.direct else "（經衍生表間接）"
            detail = f"　欄位：{u.columns}" if u.columns else ""
            dest = f"　→ {u.output}" if u.output else ""
            print(f"     {sheet:<36} {n:>6} 列{tag}{via}{detail}{dest}")
            if u.note:
                print(f"       註：{u.note}")
        print()

    if contradictions:
        print(f"宣告與實作不一致（{len(contradictions)}）：")
        for sheet, why in contradictions:
            print(f"   {sheet:<38} {why}")
    else:
        print("宣告與實作一致——但請注意，此檢查只驗「有沒有讀到」。")
        print("把一張表從『正式統計』誤標成『身分解析』，兩者都算已使用，檢查不會抓到。")
        print("標籤正確與否仍須人工核對 build_site.py 的實際輸出。")

    pending_rows = sum(
        con.execute(f'SELECT COUNT(*) FROM "{tables[s]}"').fetchone()[0]
        for s in PENDING_INTEGRATION if s in tables)
    by_priority: dict[str, int] = {}
    for sheet, (priority, _) in PENDING_INTEGRATION.items():
        by_priority[priority] = by_priority.get(priority, 0) + 1
    print()
    print(f"待接入：{len(PENDING_INTEGRATION)} 張、{pending_rows:,} 列　"
          + "　".join(f"{k} {v} 張" for k, v in sorted(by_priority.items())))


if __name__ == "__main__":
    main()
