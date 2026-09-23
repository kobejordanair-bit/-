"""Maintain membership against existing v2 honour facts, preserving award curation.

Player-stat screenshots contain no new personal awards. Never replay an older
award extractor over Canonical_Award_Facts-derived curation.
"""
from collections import defaultdict
from generic_importer import headers, dictrow, refresh


def sync(wb, fields, policy):
    def rows(sheet):
        ws = wb[sheet]; h = headers(ws)
        return [(i, {k: r[c-1] for k, c in h.items()})
                for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2)]
    name = 'Barcelona_Player_Season_Honours'
    ws = wb[name]; h = headers(ws)
    existing = {(r['Player_ID'], r['Season_ID']): (i, r) for i, r in rows(name)}
    if len(existing) != ws.max_row - 1:
        raise ValueError('DUPLICATE_MEMBERSHIP_HONOUR_KEY')
    by_season = defaultdict(set)
    for _, r in rows(name):
        if r['Attribution_Policy'] == policy:
            by_season[r['Season_ID']].add(tuple(r.get(f) for f in fields))
    master = {r['Season_ID']: r for _, r in rows('Barcelona_Season_Master')}
    source_fields = ('LaLiga_Position', 'UCL_Result', 'Copa_Result', 'Supercopa_Result', 'UEFA_SuperCup_Result')
    changes = 0; new_players = set(); pending = []
    for _, r in rows('Player_Club_Season_Totals'):
        if (r.get('Statistical_Adoption_Status') != 'ADOPTED' or r.get('Club_ID') != 'C-0030'
                or not str(r.get('Season_ID', '')).startswith('PER-S-')
                or int(r['Season_ID'][6:10]) < 2023):
            continue
        key = (r['Player_ID'], r['Season_ID'])
        if key in existing:
            i, old = existing[key]
            if old.get('Apps') != r.get('Apps'):
                ws.cell(i, h['Apps']).value = r.get('Apps'); changes += 1
            continue
        choices = by_season[r['Season_ID']]
        if len(choices) > 1:
            raise ValueError('CONFLICTING_EXISTING_SEASON_HONOURS:' + r['Season_ID'])
        if choices:
            values = next(iter(choices))
            lineage = 'Existing same-season A1 honour facts; new source-confirmed Barcelona membership'
        else:
            season = master.get(r['Season_ID'], {})
            # Only affirmative title evidence is inferred here. Unknown/non-final
            # competition results never become a zero championship assertion.
            status = str(season.get('Derivation_Status') or '')
            final = status == 'FINAL' or status.startswith('FINAL_')
            values = tuple(1 if (final and season.get(f) == 1 if f == 'LaLiga_Position' else season.get(f) == '冠軍') else None
                           for f in source_fields)
            lineage = 'Barcelona_Season_Master affirmative titles; unknown title results remain null'
        data = dict(Player_ID=r['Player_ID'], Season_ID=r['Season_ID'], Club_ID='C-0030', Apps=r.get('Apps'),
                    Attribution_Policy=policy, **dict(zip(fields, values)), Authority_Lineage=lineage,
                    Source_Reference='Barcelona_Player_Season_Honours; Barcelona_Season_Master; Player_Club_Season_Totals',
                    Verification_Status='DERIVED_A1_EXISTING_FACTS' if None not in values else 'PARTIAL_TITLES_UNKNOWN')
        ws.append(dictrow(ws, data)); existing[key] = (ws.max_row, data)
        new_players.add(r['Player_ID']); changes += 1
        if None in values:
            pending.append(dict(player=r['Player_ID'], season=r['Season_ID'], reason='Some team-title facts are not yet known'))
    refresh(ws)
    career = wb['Barcelona_Player_Career']; ch = headers(career); career_changes = 0
    memberships = defaultdict(list)
    for _, r in rows(name):
        memberships[r['Player_ID']].append(r)
    for i, r in rows('Barcelona_Player_Career'):
        if r['Player_ID'] not in memberships:
            continue
        for field in fields:
            values = [m.get(field) for m in memberships[r['Player_ID']]]
            value = sum(values) if all(v is not None for v in values) else None
            if r.get(field) != value:
                career.cell(i, ch[field]).value = value; career_changes += 1
    return dict(pass_=True, **{'pass': True}, policy=policy, season_honours_changes=changes,
                first_run_career_changes=career_changes, personal_awards='PRESERVED_CURRENT_MASTER',
                pending=pending)
