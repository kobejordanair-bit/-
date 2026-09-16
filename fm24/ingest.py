#!/usr/bin/env python3
"""Fold an exported import batch back into fm24.sqlite, append-only.

The archive page writes pending batches to its own store; exporting produces a
FM24_IMPORT_BATCH_V1 JSON file. This script appends those rows to SQLite as new
observations. Nothing existing is ever updated or deleted — the workbook's own
contract is OBSERVATION_FACTS_V2, and an import is just another observation.

Usage:
    python3 ingest.py fm24-imports-2035-06-02.json                      # dry run
    python3 ingest.py fm24-imports-2035-06-02.json --commit
    python3 ingest.py fm24-identity-decisions-2035-06-02.json --identity --commit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "FM24_IMPORT_BATCH_V1"
IDENTITY_SCHEMA = "FM24_IDENTITY_DECISIONS_V1"
IDENTITY_TABLE = "Ingest_Identity_Decisions"

# Where each import kind lands. Imports go to their own tables rather than into
# the mirrored workbook sheets, so a rebuild from the .xlsx never silently
# clobbers them and the merge back into the workbook stays a deliberate step.
# The Ingest_ prefix is deliberately distinct from the workbook's own
# Import_Observations sheet, so etl.py can carry these across a rebuild
# without ever colliding with a mirrored sheet name.
TARGETS = {
    "season": "Ingest_Season_Stats",
    "profile": "Ingest_Player_Profiles",
    "standings": "Ingest_Standings",
    "award": "Ingest_Award_Facts",
    "raw": "Ingest_Raw",
}

BASE_COLUMNS = [
    "Observation_ID", "Batch_ID", "Imported_At", "Ingested_At", "Kind",
    "Raw_Name", "Resolved_Player_ID", "Resolution_Status", "Missing_Fields",
    "Verification_Status", "Payload_JSON",
]


def observation_id(batch_id: str, index: int, values: dict) -> str:
    """Stable id: re-ingesting the same export is a no-op rather than a duplicate."""
    blob = json.dumps({"b": batch_id, "i": index, "v": values}, sort_keys=True, ensure_ascii=False)
    return "OBS-IMP-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


def ensure_table(con: sqlite3.Connection, table: str, extra: list[str]) -> None:
    existing = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
    if not existing:
        cols = ", ".join(f'"{c}" TEXT' for c in BASE_COLUMNS + extra)
        con.execute(f'CREATE TABLE "{table}" ({cols}, PRIMARY KEY ("Observation_ID"))'
                    .replace(", PRIMARY KEY", ", PRIMARY KEY", 1))
        con.execute(f'CREATE UNIQUE INDEX "ux_{table}_obs" ON "{table}" ("Observation_ID")')
        return
    for column in extra:
        if column not in existing:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT')


def next_player_id(con: sqlite3.Connection) -> str:
    """Mint the next P-nnnn, considering both the workbook and earlier decisions."""
    highest = 0
    for table, column in (("Player_Dim", "Player_ID"), (IDENTITY_TABLE, "Assigned_Player_ID")):
        try:
            rows = con.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" LIKE ?', ("P-%",))
            for (value,) in rows:
                try:
                    highest = max(highest, int(str(value).split("-")[1]))
                except (IndexError, ValueError):
                    continue
        except sqlite3.OperationalError:
            continue
    return f"P-{highest + 1:04d}"


IDENTITY_DDL = (
    f'CREATE TABLE IF NOT EXISTS "{IDENTITY_TABLE}" ('
    '"Decision_ID" TEXT PRIMARY KEY, "Raw_Name" TEXT, "Action" TEXT, '
    '"Assigned_Player_ID" TEXT, "Matched_Player_Name" TEXT, "Affected_Rows" TEXT, '
    '"Build_Verdict" TEXT, "Top_Score" TEXT, "Decided_At" TEXT, "Applied_At" TEXT)'
)

VERB = {"confirm": "確認", "new": "新建", "reject": "跳過"}


def ingest_identity(payload_path: Path, db_path: Path, commit: bool) -> int:
    """Apply resolution-console decisions.

    A decision is recorded, never applied destructively: a confirmation becomes a
    controlled alias row awaiting merge, and 'new' mints the next free P-nnnn.
    Nothing in the mirrored workbook tables is rewritten.
    """
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if payload.get("schema") != IDENTITY_SCHEMA:
        print(f"error: expected schema {IDENTITY_SCHEMA}, got {payload.get('schema')!r}", file=sys.stderr)
        return 2

    decisions = payload.get("decisions", [])
    if not decisions:
        print("nothing to apply: export contains no decisions", file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    con.execute(IDENTITY_DDL)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    applied = skipped = minted = 0

    for decision in sorted(decisions, key=lambda d: d.get("decidedAt") or ""):
        raw = decision.get("raw")
        if not raw:
            continue
        decision_id = "IDD-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        if con.execute(f'SELECT 1 FROM "{IDENTITY_TABLE}" WHERE "Decision_ID"=?', (decision_id,)).fetchone():
            skipped += 1
            continue

        action = decision.get("action")
        player_id = decision.get("playerId")
        if action == "new":
            player_id = next_player_id(con)
            minted += 1
        elif action == "reject":
            player_id = None

        con.execute(
            f'INSERT INTO "{IDENTITY_TABLE}" VALUES (?,?,?,?,?,?,?,?,?,?)',
            (decision_id, raw, action, player_id, decision.get("playerName"),
             str(decision.get("rows") or ""), decision.get("verdict"),
             str(decision.get("topScore") or ""), decision.get("decidedAt"), now))
        applied += 1
        print(f"  {VERB.get(action, action):<4} {raw:<26} -> {player_id or '—'}")

    if commit:
        con.commit()
        print(f"\napplied {applied} decisions ({minted} new Player_IDs minted), {skipped} already present")
        print(f"stored in {IDENTITY_TABLE}; the workbook itself is untouched")
    else:
        con.rollback()
        print(f"\nDRY RUN: would apply {applied} ({minted} new IDs), skip {skipped}"
              "\nre-run with --commit to write")
    con.close()
    return 0


def ingest(payload_path: Path, db_path: Path, commit: bool) -> int:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        print(f"error: expected schema {SCHEMA}, got {payload.get('schema')!r}", file=sys.stderr)
        return 2

    batches = payload.get("batches", [])
    if not batches:
        print("nothing to ingest: export contains no batches", file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = skipped = 0

    for batch in batches:
        kind = batch.get("kind", "raw")
        table = TARGETS.get(kind, TARGETS["raw"])
        rows = batch.get("rows", [])
        if not rows:
            continue

        extra = sorted({k for r in rows for k in (r.get("values") or {})})
        ensure_table(con, table, extra)

        for index, row in enumerate(rows):
            values = row.get("values") or {}
            obs = observation_id(batch["id"], index, values)
            if con.execute(f'SELECT 1 FROM "{table}" WHERE "Observation_ID"=?', (obs,)).fetchone():
                skipped += 1
                continue
            record = {
                "Observation_ID": obs,
                "Batch_ID": batch["id"],
                "Imported_At": batch.get("createdAt"),
                "Ingested_At": now,
                "Kind": kind,
                "Raw_Name": row.get("rawName"),
                "Resolved_Player_ID": row.get("resolvedId"),
                "Resolution_Status": row.get("resolution"),
                "Missing_Fields": "、".join(row.get("missing") or []) or None,
                "Verification_Status": batch.get("verificationStatus", "使用者匯入（待併入工作簿）"),
                "Payload_JSON": json.dumps(values, ensure_ascii=False, sort_keys=True),
                **{k: str(v) for k, v in values.items()},
            }
            columns = ", ".join(f'"{c}"' for c in record)
            marks = ", ".join("?" * len(record))
            con.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({marks})', list(record.values()))
            inserted += 1

        print(f"  {batch['id']}  {kind:<10} -> {table}  ({len(rows)} rows)")

    if commit:
        con.commit()
        print(f"\ncommitted: {inserted} new observations, {skipped} already present")
    else:
        con.rollback()
        print(f"\nDRY RUN: would insert {inserted}, skip {skipped} already present"
              "\nre-run with --commit to write")
    con.close()
    return 0


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload", type=Path, help="the exported fm24-imports-*.json")
    ap.add_argument("-d", "--database", type=Path, default=here / "data" / "fm24.sqlite")
    ap.add_argument("--commit", action="store_true", help="actually write (default is a dry run)")
    ap.add_argument("--identity", action="store_true",
                    help="the payload is a resolution-console decisions export, not an import batch")
    args = ap.parse_args()
    if not args.database.exists():
        print(f"error: {args.database} not found — run etl.py first", file=sys.stderr)
        raise SystemExit(2)
    run = ingest_identity if args.identity else ingest
    raise SystemExit(run(args.payload, args.database, args.commit))


if __name__ == "__main__":
    main()
