"""Versioned deterministic selection policy. Original observations are append-only.

Fact sheets are selected/materialized views. Import_Observations retains both
old and submitted rows whenever they differ; the selected row is reproducible.
No LLM, fuzzy names, or guessed missing counters are used.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date
from generic_importer import ImportFailure, headers, dictrow, refresh

POLICY = 'FM_SELECTION_V1'
LEDGER = 'Import_Observations'
LEDGER_HEADER = ('Observation_ID', 'Policy', 'Family', 'Target_Sheet', 'Source_ID',
                 'Snapshot_Date', 'Existing_JSON', 'Submitted_JSON', 'Selected_JSON', 'Rules_JSON')
COUNTS = {'Apps', 'Starts', 'Sub_Appearances', 'Goals', 'Assists', 'POTM', 'Yellow', 'Red',
          'Fouls', 'Fouled', 'Senior_NT_Caps', 'Senior_NT_Goals', 'U21_Caps', 'U21_Goals',
          'U20_Caps', 'U20_Goals', 'Goals_Conceded', 'Clean_Sheets'}
from screenshot_provenance import FIELDS, selected_metadata
META = {'Source_ID', 'Verification_Status'} | FIELDS
IDENTITY = {'Player_ID', 'DOB', 'Nationality_Nation_ID', 'Nation_ID', 'Club_ID',
            'Season_ID', 'Team_Level', 'Scope', 'Snapshot_Date'}
NAME_FIELDS = {'Player_Name_Raw', 'Club_Raw', 'Country_Raw', 'Nationality_Raw',
               'Current_Club_Raw', 'Senior_NT_Raw', 'U21_NT_Raw'}

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)

def equivalent(a, b):
    if a == b: return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-10
    return False

def evidence_same(old, submitted):
    from governed_identity import normalized_candidate_form
    for k, v in submitted.items():
        if k in META: continue
        a = old.get(k)
        if equivalent(a, v): continue
        if k in NAME_FIELDS and a and v and normalized_candidate_form(a) == normalized_candidate_form(v): continue
        return False
    return True

def source_snapshot(wb, sid):
    ws = wb['Source_Index']; h = headers(ws)
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[h['Source_ID']-1] == sid:
            dates = re.findall(r'\d{4}-\d{2}-\d{2}', str(row[h['Season_Context']-1] or ''))
            if len(set(dates)) == 1:
                return dates[0]
    return None

def select_row(old, submitted, *, family, old_snapshot, snapshot):
    """Same-key direct source vs direct source: ties preserve current adoption.

    Later dated seasonal observations may update accumulating stats. Older or
    undated competing values never displace newer known evidence. Missing
    fields can be filled. A large conflict is isolated to the field.
    """
    from governed_identity import normalized_candidate_form
    chosen = dict(old); rules = {}
    later = bool(old_snapshot and snapshot > old_snapshot and family not in {'PLAYER', 'LEAGUE_CAREER_TOTAL'})
    older = bool(old_snapshot and snapshot < old_snapshot)
    for k, v in submitted.items():
        a = old.get(k)
        if k in META or equivalent(a, v): continue
        if v is None:
            rules[k] = 'KEEP_EXISTING_UNKNOWN_SUBMISSION'; continue
        if a is None:
            chosen[k] = v; rules[k] = 'FILL_MISSING_DIRECT_SOURCE'; continue
        if k in NAME_FIELDS and normalized_candidate_form(a) == normalized_candidate_form(v):
            rules[k] = 'NORMALIZED_EQUIVALENT_KEEP_LITERAL'; continue
        if k=='Team_Level' and a in ('成年隊（使用者確認預設）','成年隊（預設）') and v=='Senior':
            rules[k]='EXPLICIT_LEGACY_SENIOR_POLICY_KEEP_LITERAL'; continue
        if k in IDENTITY:
            raise ImportFailure('IDENTITY_OR_SCOPE_CONFLICT:' + k)
        if k in COUNTS and type(a) in (int, float) and type(v) in (int, float):
            if later:
                chosen[k] = v; rules[k] = 'LATEST_DATED_DIRECT_SOURCE'
            elif abs(a-v) <= 2:
                rules[k] = 'SMALL_COUNTER_DIFF_KEEP_EXISTING_EQUAL_PRIORITY'
            else:
                rules[k] = 'LARGE_DIFF_ISOLATED_KEEP_EXISTING'
        elif later:
            chosen[k] = v; rules[k] = 'LATEST_DATED_DIRECT_SOURCE'
        else:
            rules[k] = 'OLDER_SOURCE_KEEP_EXISTING' if older else 'NON_COUNTER_DIFF_ISOLATED_KEEP_EXISTING'
    # Apps components and the raw representation are an indivisible tuple.
    group = ('Apps_Raw', 'Apps', 'Starts', 'Sub_Appearances')
    if 'Apps_Raw' in submitted:
        for k in group:
            if any(rules.get(f, '').startswith(('SMALL_', 'LARGE_', 'NON_COUNTER_', 'OLDER_')) for f in group):
                for f in group:
                    chosen[f] = old.get(f)
                    if not equivalent(old.get(f), submitted.get(f)):
                        rules[f] = 'APPS_GROUP_KEEP_EXISTING'
                break
    if any(not equivalent(chosen.get(k), old.get(k)) for k in chosen if k not in META):
        chosen['Source_ID'] = submitted['Source_ID']
        chosen['Verification_Status'] = 'SOURCE_SELECTED_WITH_OBSERVATION_LINEAGE'
    selected_metadata(old, submitted, chosen)
    return chosen, rules

def observation(family, sheet, old, incoming, selected, rules, snapshot):
    record = {'Policy': POLICY, 'Family': family, 'Target_Sheet': sheet,
              'Source_ID': incoming['Source_ID'], 'Snapshot_Date': snapshot,
              'Existing_JSON': dump(old), 'Submitted_JSON': dump(incoming),
              'Selected_JSON': dump(selected), 'Rules_JSON': dump(rules)}
    record['Observation_ID'] = hashlib.sha256(dump(record).encode()).hexdigest()
    return record

def append_observations(wb, records):
    if not records: return
    if LEDGER not in wb.sheetnames: wb.create_sheet(LEDGER).append(LEDGER_HEADER)
    ws = wb[LEDGER]; existing = {r[0] for r in ws.iter_rows(min_row=2, values_only=True)}
    for record in records:
        if record['Observation_ID'] not in existing:
            if any(len(str(v)) > 32767 for v in record.values()): raise ImportFailure('OBSERVATION_CELL_TOO_LARGE')
            ws.append(dictrow(ws, record)); existing.add(record['Observation_ID'])

def period_fields(token):
    token = str(token)
    m = re.fullmatch(r'(\d{4})[/-](\d{2}|\d{4})(\*)?', token)
    if m:
        start = int(m[1]); end = int(m[2]) if len(m[2]) == 4 else (start // 100) * 100 + int(m[2])
        if end <= start and len(m[2]) == 2: end += 100
        if end != start + 1: raise ImportFailure('PERIOD_INVALID:' + token)
        pid, display, kind = f'PER-S-{start}-{end%100:02d}', f'{start}/{end%100:02d}', 'Season'
    elif re.fullmatch(r'\d{4}', token):
        start = end = int(token); pid, display, kind = f'PER-Y-{token}', token, 'Calendar Year'
    else: raise ImportFailure('PERIOD_INVALID:' + token)
    if not 1000 <= start <= 9998: raise ImportFailure('PERIOD_OUT_OF_RANGE:' + token)
    return {'Period_ID': pid, 'Source_Period_Display': token, 'Period_Type': kind,
            'Start_Year': start, 'End_Year': end, 'Canonical_Period_Display': display,
            'Verification_Status': 'SOURCE_OBSERVED_PERIOD_V1'}

def ensure_observed_periods(wb, tokens):
    ws = wb['Period_Dim']; h = headers(ws); added = []
    for token in sorted(set(tokens)):
        p = period_fields(token)
        rows = [{k:r[c-1] for k,c in h.items()} for r in ws.iter_rows(min_row=2, values_only=True)]
        exact = {r['Period_ID'] for r in rows if r.get('Source_Period_Display') == token and r.get('Period_Type') == p['Period_Type']}
        if len(exact) > 1: raise ImportFailure('PERIOD_AMBIGUOUS:' + token)
        if exact: continue
        equivalents = {r['Period_ID'] for r in rows if r.get('Canonical_Period_Display') == p['Canonical_Period_Display'] and r.get('Period_Type') == p['Period_Type']}
        if len(equivalents) > 1: raise ImportFailure('PERIOD_AMBIGUOUS:' + token)
        if equivalents: p['Period_ID'] = next(iter(equivalents))
        ws.append(dictrow(ws,p)); added.append(p)
    if added: refresh(ws)
    return added
