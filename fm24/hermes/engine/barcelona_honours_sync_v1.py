#!/usr/bin/env python3
"""Barcelona Player Honours Sync V1 — copy-only, registry-verified and fail-closed.

The five team-honour Career aggregates are historical derived evidence, not player
competition-credit claims.  The confirmed membership policy is A1: a Barcelona
season row exists.  Club World Cup is intentionally out of scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import copy
from pathlib import Path
from shutil import copy2

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table, TableStyleInfo
from career_honours_enrichment import enrich_career_honours, settle_coverage_reconciliation_issues

CLUB_ID = 'C-0030'
POLICY = 'A1'
FIELDS = (
    'LaLiga_Team_Championships_While_At_Barcelona',
    'UCL_Team_Championships_While_At_Barcelona',
    'Copa_Team_Championships_While_At_Barcelona',
    'Supercopa_Team_Championships_While_At_Barcelona',
    'UEFA_SuperCup_Team_Championships_While_At_Barcelona',
)
SOURCE_SHEETS = ('Barcelona_History', 'Barcelona_UCL_Journey', 'National_Tournaments',
                 'UEFA_Super_Cup', 'Player_Club_Season_Totals', 'Barcelona_Player_Career')
SHEET = 'Barcelona_Player_Season_Honours'
HEADERS = ('Player_ID', 'Season_ID', 'Club_ID', 'Apps', 'Attribution_Policy',
           'LaLiga_Team_Championships_While_At_Barcelona',
           'UCL_Team_Championships_While_At_Barcelona',
           'Copa_Team_Championships_While_At_Barcelona',
           'Supercopa_Team_Championships_While_At_Barcelona',
           'UEFA_SuperCup_Team_Championships_While_At_Barcelona',
           'Authority_Lineage', 'Source_Reference', 'Verification_Status')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def norm_season(value) -> str | None:
    m = re.search(r'(\d{4})[-/](\d{2,4})', str(value or ''))
    return f'{m.group(1)}/{m.group(2)[-2:]}' if m else None


def headers(ws):
    return {c.value: c.column for c in ws[1]}


def row_dicts(ws):
    h = headers(ws)
    return [{name: row[col-1] for name, col in h.items()}
            for row in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in row)]


def fingerprint(ws) -> str:
    h = hashlib.sha256()
    for row in ws.iter_rows():
        for cell in row:
            h.update(repr(cell.value).encode('utf-8')); h.update(b'\x1e')
        h.update(b'\x1f')
    return h.hexdigest()


def title_seasons(wb):
    winners = {field: set() for field in FIELDS}
    for r in row_dicts(wb['Barcelona_History']):
        if r['LaLiga_Rank'] == 1 and str(r['Season_Status']).startswith('已完成'):
            winners[FIELDS[0]].add(norm_season(r['Season']))
    for r in row_dicts(wb['Barcelona_UCL_Journey']):
        if r['Result'] == '冠軍':
            winners[FIELDS[1]].add(norm_season(r['Season']))
    for r in row_dicts(wb['National_Tournaments']):
        season = norm_season(r['Season'])
        if r['Rank'] == 1 and r['Club'] == '巴薩':
            if r['Competition'] == '西班牙國王盃': winners[FIELDS[2]].add(season)
            if r['Competition'] == '西班牙超級盃': winners[FIELDS[3]].add(season)
    for r in row_dicts(wb['UEFA_Super_Cup']):
        if r['Winner'] == '巴薩': winners[FIELDS[4]].add(norm_season(r['Season']))
    return winners


def membership_rows(wb):
    # Season_ID remains the canonical FK. _season_key only matches title sources
    # that store a human display season (for example, 2024/25).
    return [dict(r, _season_key=norm_season(r.get('Season_ID') or r.get('Season_Display')))
            for r in row_dicts(wb['Player_Club_Season_Totals'])
            if r.get('Statistical_Adoption_Status', 'ADOPTED') == 'ADOPTED' and r.get('Player_ID') not in (None, '') and r.get('Club_ID') == CLUB_ID
            and r.get('Season_ID') not in (None, '')
            and norm_season(r.get('Season_ID') or r.get('Season_Display')) and int(norm_season(r.get('Season_ID') or r.get('Season_Display'))[:4]) >= 2023]


def expected_counts(wb, policy: str):
    if policy not in ('A1', 'A2'): raise ValueError(f'unsupported policy {policy}')
    winners = title_seasons(wb)
    totals = membership_rows(wb)
    career_ids = {r['Player_ID'] for r in row_dicts(wb['Barcelona_Player_Career'])
                  if r.get('Player_ID') not in (None, '')}
    out = {pid: {field: 0 for field in FIELDS} for pid in career_ids}
    for r in totals:
        if r['Player_ID'] not in out: continue
        if policy == 'A2' and not (r.get('Apps') is not None and r['Apps'] > 0): continue
        for field, seasons in winners.items():
            out[r['Player_ID']][field] += int(r['_season_key'] in seasons)
    return out


def audit(wb):
    career = {r['Player_ID']: r for r in row_dicts(wb['Barcelona_Player_Career'])
              if r.get('Player_ID') not in (None, '')}
    result = {}
    for policy in ('A1', 'A2'):
        expected = expected_counts(wb, policy)
        by_field = {f: {'exact': 0, 'missing_derivable': 0, 'conflict': 0} for f in FIELDS}
        nonexact = []
        for pid, computed in expected.items():
            for field, value in computed.items():
                existing = career[pid].get(field)
                status = 'exact' if existing == value else ('missing_derivable' if existing in (None, '') else 'conflict')
                by_field[field][status] += 1
                if status != 'exact':
                    nonexact.append({'player_id': pid, 'field': field, 'existing': existing, 'derived': value})
        totals = {k: sum(item[k] for item in by_field.values()) for k in ('exact', 'missing_derivable', 'conflict')}
        result[policy] = {'totals': totals, 'by_field': by_field, 'nonexact': nonexact}
    return result


def zero_app_effects(wb):
    winners = title_seasons(wb)
    career_ids = {r['Player_ID'] for r in row_dicts(wb['Barcelona_Player_Career']) if r.get('Player_ID')}
    result = []
    for r in membership_rows(wb):
        if r['Player_ID'] not in career_ids or r.get('Apps') != 0: continue
        fields = [field for field, seasons in winners.items() if r['Season_ID'] in seasons]
        if fields: result.append({'player_id': r['Player_ID'], 'season_id': r['Season_ID'], 'apps': 0, 'fields': fields})
    return result


def _copy_style(ws, source_row, target_row):
    for col in range(1, ws.max_column + 1):
        src, dst = ws.cell(source_row, col), ws.cell(target_row, col)
        if src.has_style: dst._style = copy(src._style)
        dst.number_format = src.number_format
        dst.alignment = copy(src.alignment)


def _upsert_season_honours(wb):
    winners = title_seasons(wb)
    data = []
    for r in sorted(membership_rows(wb), key=lambda x: (x['Player_ID'], x['Season_ID'])):
        values = {field: int(r['_season_key'] in seasons) for field, seasons in winners.items()}
        data.append({'Player_ID': r['Player_ID'], 'Season_ID': r['Season_ID'], 'Club_ID': CLUB_ID,
                     'Apps': r.get('Apps'), 'Attribution_Policy': POLICY, **values,
                     'Authority_Lineage': 'A1 Barcelona membership row + season-level official title authorities',
                     'Source_Reference': 'Barcelona_History; Barcelona_UCL_Journey; National_Tournaments; UEFA_Super_Cup; Player_Club_Season_Totals',
                     'Verification_Status': 'VERIFIED_A1_AUTHORITY_DERIVED'})
    if SHEET not in wb.sheetnames:
        ws = wb.create_sheet(SHEET)
        ws.append(HEADERS)
        for cell in ws[1]: cell.font = Font(bold=True)
    else:
        ws = wb[SHEET]
        if tuple(c.value for c in ws[1]) != HEADERS: raise ValueError('atomic FAIL: existing honours sheet schema differs')
    existing = {(ws.cell(i, 1).value, ws.cell(i, 2).value): i for i in range(2, ws.max_row + 1)
                if ws.cell(i, 1).value not in (None, '')}
    if len(existing) != max(0, ws.max_row - 1): raise ValueError('atomic FAIL: duplicate/blank season honours key')
    changes = 0
    for payload in data:
        key = (payload['Player_ID'], payload['Season_ID'])
        values = [payload[h] for h in HEADERS]
        if key in existing:
            row = existing[key]
            current = [ws.cell(row, c).value for c in range(1, len(HEADERS) + 1)]
            if current != values:
                for c, value in enumerate(values, 1): ws.cell(row, c).value = value
                changes += 1
        else:
            row = ws.max_row + 1
            if row > 2: _copy_style(ws, row - 1, row)
            for c, value in enumerate(values, 1): ws.cell(row, c).value = value
            changes += 1
    if ws.max_row > 1 and 'Barcelona_Player_Season_Honours_Table' not in ws.tables:
        table = Table(displayName='Barcelona_Player_Season_Honours_Table', ref=f'A1:{get_column_letter(len(HEADERS))}{ws.max_row}')
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        ws.add_table(table)
    elif ws.tables:
        next(iter(ws.tables.values())).ref = f'A1:{get_column_letter(len(HEADERS))}{ws.max_row}'
    return changes, len(data)


def _sync_career(wb):
    expected = expected_counts(wb, POLICY)
    ws = wb['Barcelona_Player_Career']; h = headers(ws); changed = 0
    found = set()
    for r in range(2, ws.max_row + 1):
        pid = ws.cell(r, h['Player_ID']).value
        if pid not in expected: continue
        if pid in found: raise ValueError(f'atomic FAIL: duplicate Career player {pid}')
        found.add(pid)
        for field, value in expected[pid].items():
            current = ws.cell(r, h[field]).value
            if current != value:
                ws.cell(r, h[field]).value = value; changed += 1
    if found != set(expected): raise ValueError(f'atomic FAIL: missing Career rows {sorted(set(expected)-found)}')
    return changed


def sync_workbook(path: Path):
    """Sync an already-authorized candidate workbook; never resolves ACTIVE state."""
    wb = load_workbook(path, data_only=False)
    if "Canonical_Award_Facts" in wb.sheetnames and "Workbook_Schema_Metadata" in wb.sheetnames:
        from modern_honours import sync
        result = sync(wb, FIELDS, POLICY)
        wb.save(path); wb.close()
        return result
    # Only authority/source sheets are immutable. Career and the two derived
    # honours sheets are intentional targets of this common post-write phase.
    immutable_sources = tuple(s for s in SOURCE_SHEETS if s != 'Barcelona_Player_Career')
    raw_before = {s: fingerprint(wb[s]) for s in immutable_sources}
    comparison = audit(wb)
    # Career fields are derived; recompute after membership/stat updates.
    season_changes, season_rows = _upsert_season_honours(wb)
    career_changes = _sync_career(wb)
    enrichment = enrich_career_honours(wb)
    reconciliation_changes = settle_coverage_reconciliation_issues(wb)
    raw_after = {s: fingerprint(wb[s]) for s in immutable_sources}
    if raw_before != raw_after:
        raise RuntimeError('atomic FAIL: authority/source sheet mutation detected')
    wb.save(path)
    return {'pass': True, 'policy': POLICY, 'audit': comparison,
            'zero_app_effects': zero_app_effects(wb), 'barcelona_season_rows': season_rows,
            'season_honours_changes': season_changes, 'first_run_career_changes': career_changes,
            **enrichment, 'reconciliation_status_changes': reconciliation_changes,
            'club_world_cup_status': 'DERIVED_FROM_EXISTING_BARCELONA_CLUB_WORLD_CUP_AUTHORITY'}


def sync_from_registry(registry_path: Path, output: Path, *, allow_existing_output=False):
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    if registry.get('status') != 'ACTIVE': raise ValueError('registry is not ACTIVE')
    baseline = Path(registry['canonical_workbook'])
    actual = sha256(baseline)
    if actual != registry.get('sha256'): raise ValueError('ACTIVE canonical SHA-256 mismatch')
    if output.exists() and not allow_existing_output: raise FileExistsError(f'NO_OVERWRITE_TARGET_EXISTS:{output}')
    if not output.exists(): copy2(baseline, output)
    report = sync_workbook(output)
    report.update({'baseline': str(baseline), 'baseline_sha256': actual})
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', type=Path, default=Path('/opt/data/FM24_World_Current.json'))
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(sync_from_registry(args.registry, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
