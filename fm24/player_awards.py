"""Player honour ledger, derived from structured authorities, never narratives.

CAF is a partial authority, not the universe of personal honours. Preserve its
global statistics while joining independent award sheets by workbook identities.
One honour may have several source rows; those rows are evidence, not new wins.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import re
from evidence import Periods, reference, value


# Explicit semantic equivalences: no fuzzy award or player-name matching.
AWARD_SHEETS = {
    'Ballon_dOr': 'Ballon d’Or',
    'Goal_50': 'Goal 50',
    'Worlds_Best_Goalkeeper': "World's Best Goalkeeper",
    'Yashin_Trophy': 'Yashin Trophy',
    'Kopa_Trophy': 'Kopa Trophy',
    'The_Best_FIFA_Mens_Player': 'The Best FIFA Men’s Player',
    'World_Player_of_the_Year': 'World Player of the Year',
    'FIFA_FIFPro_World_XI': 'FIFPro World XI',
    'Youth_Awards': None,  # NxGn and Golden Boy are distinct awards.
    'UCL_Season_Best_Player': '欧洲冠军联赛 赛季最佳球员',
    'UCL_Season_Best_Young_Player': '欧洲冠军联赛 赛季最佳年轻球员',
    'UCL_Golden_Boot': '欧洲冠军联赛 UEFA Champions League Golden Boot',
    'Pichichi_Award': 'LaLiga EA Sports Pichichi',
    'LaLiga_Player_of_Year': 'LaLiga EA Sports Jugador del año',
    'Barcelona_LaLiga_Best_XI': 'LaLiga EA Sports Equipo de la temporada',
    'Barcelona_Season_Leaders': 'Fan Player of Season',
    'Golden_Shoe': 'European Golden Shoe',
    'Premier_League_Golden_Boot': 'Premier League Golden Boot',
    'Premier_League_PFA_POTY': "PFA Players' Player of the Year",
    'PL_PFA_Young_POTY': 'PFA Young Player of the Year',
    'PL_PFA_Team_of_Year': 'PFA Team of the Year',
    'Serie_A_Team_of_Year': 'Serie A Team of the Year',
    'Serie_A_MVP_Young': 'Serie A Young Player of the Year',
    'Serie_A_MVP_Player': 'Serie A Player of the Year',
    'Serie_A_Capocannoniere': 'Serie A Capocannoniere',
    'Bundesliga_Elf_des_Jahres': 'Bundesliga Elf des Jahres',
    'Bundesliga_Torjagerkanone': 'Bundesliga Torjägerkanone',
    'Bundesliga_VDV_Newcomer': 'Bundesliga VDV Newcomer der Saison',
    'Bundesliga_VDV_Player': 'Bundesliga VDV Spieler der Saison',
    'Ligue1_UNFP_Best_XI': 'Ligue 1 UNFP Best XI',
    'Ligue1_UNFP_MVP': 'Ligue 1 UNFP MVP',
    'Ligue1_Golden_Boot': 'Ligue 1 Golden Boot',
}
ALIASES = {
    'Premier League PFA Player of the Year': "PFA Players' Player of the Year",
    'Premier League PFA Young Player of the Year': 'PFA Young Player of the Year',
    'Premier League PFA Premier League Team of the Year': 'PFA Team of the Year',
}
SELECTION_SHEETS = {'FIFA_FIFPro_World_XI', 'Barcelona_LaLiga_Best_XI',
    'PL_PFA_Team_of_Year', 'Serie_A_Team_of_Year', 'Bundesliga_Elf_des_Jahres', 'Ligue1_UNFP_Best_XI'}


def signature(f):
    # Calendar years and seasons deliberately remain distinct Period_Dim IDs.
    return (f['id'], ALIASES.get(f['award'], f['award']),
            f['periodId'] or f['season'], f['kind'],
            None if f['kind'] == 'selection' else f['rank'])


def integrate_player_awards(archive, payload):
    periods = Periods(archive.q('SELECT * FROM Period_Dim ORDER BY _row'))
    def period_id(raw):
        found = periods.resolve(raw)
        if found:
            return found
        match = re.fullmatch(r'(\d{4})-(\d{4})', str(raw or ''))
        if match and int(match[2]) == int(match[1]) + 1:
            return periods.resolve(f'{match[1]}/{match[2][-2:]}')
        return None

    def period_display(raw):
        return periods.by_id.get(period_id(raw), {}).get('display') or raw
    players = {p['id']: p for p in payload['people']['players']}
    identities = defaultdict(list)
    aliases = defaultdict(set)
    for p in players.values():
        for name in [p['name'], *p['aliases']]:
            if value(name):
                aliases[value(name)].add(p['id'])
    for r in archive.q('SELECT * FROM Record_Identity_Map ORDER BY _row'):
        if r['Entity_Role'] == 'Player' and r['Entity_ID'] in players:
            identities[(r['Origin_Sheet'], str(r['Origin_Row']))].append(r)

    identity_issues = []
    def identity(sheet, row, name, period):
        maps = identities.get((sheet, str(row)), [])
        valid = [r for r in maps if value(r['Raw_Display_Name']) == value(name)
                 and period_id(period) and r['Period_ID'] == period_id(period)]
        ids = {r['Entity_ID'] for r in valid}
        exact = aliases.get(value(name), set())
        if maps and len(valid) != len(maps):
            identity_issues.append(dict(sheet=sheet, row=row, name=name, period=period,
                reason='來源列姓名或期間與舊身分對照不符'))
        if len(ids) == 1 and (not exact or exact == ids):
            return next(iter(ids)), 'Record_Identity_Map'
        if not ids and len(exact) == 1:
            return next(iter(exact)), 'Player_Dim_exact_alias'
        return None, None

    ledger, locators, skipped = {}, {}, []

    def add(f):
        key = signature(f)
        if key in ledger:
            old = ledger[key]
            refs = [old['primary'], *old['evidence']]
            seen = {(r['sheet'], str(r['row']), r['source']) for r in refs}
            for r in [f['primary'], *f['evidence']]:
                loc = (r['sheet'], str(r['row']), r['source'])
                if loc not in seen:
                    old['evidence'].append(r)
                    seen.add(loc)
            old.setdefault('performance', f.get('performance'))
            return old
        ledger[key] = f
        return f

    for facts in payload['honours']['facts'].values():
        for original in facts:
            # Coach prizes are not personal player honours.
            if 'Mánager' in original['award']:
                continue
            f = deepcopy(original)
            loc = (f['primary']['sheet'], str(f['primary']['row']))
            mapped, route = identity(*loc, f['player'], f['season'])
            if f['id'] and mapped and f['id'] != mapped:
                skipped.append(dict(reason='球員 ID 與來源身分對照衝突', evidence=f['primary']))
                continue
            f['id'] = f['id'] or mapped
            if f['id'] not in players:
                skipped.append(dict(reason='尚無唯一受控球員身分', evidence=f['primary']))
                continue
            f['resolved'] = True
            f['periodId'] = period_id(f['season'])
            f['season'] = f['periodDisplay'] = period_display(f['season'])
            f['identityRoute'] = 'Canonical_Award_Facts' if original['id'] else route
            locators[loc] = add(f)

    tables = payload['reference']['tables']
    counts = {}
    for sheet, award in AWARD_SHEETS.items():
        rows = archive.q(f'SELECT * FROM "{sheet}" ORDER BY _row')
        columns = [k for k in rows[0] if k != '_row'] if rows else []
        tables.setdefault(sheet, dict(priority='獎項', rule='結構化獎項來源；多來源只計一次，未唯一綁定不猜測。',
            columns=columns, rows=[dict(row=r['_row'], values={k: value(r[k]) for k in columns},
                source=reference(r.get('Source_ID'), sheet, r['_row'], r.get('Verification_Status'))) for r in rows]))
        report = Counter()
        for r in rows:
            report['rows'] += 1
            if sheet == 'Barcelona_Season_Leaders' and r['Metric'] != '年度球迷票選最佳球員':
                report['notAward'] += 1
                continue
            ref = reference(r.get('Source_ID'), sheet, r['_row'], r.get('Verification_Status'))
            loc = (sheet, str(r['_row']))
            raw_period = r.get('Season') or r.get('Year')
            pid, route = identity(*loc, r.get('Player') or r.get('Player_Raw'), raw_period)
            if loc in locators:
                report['canonicalSource'] += 1
                continue
            if not pid:
                skipped.append(dict(reason='尚無唯一受控球員身分', evidence=ref))
                report['unassigned'] += 1
                continue
            rank = '入選' if sheet in SELECTION_SHEETS else '1' if sheet == 'Barcelona_Season_Leaders' else value(r.get('Rank'))
            if not rank:
                skipped.append(dict(reason='來源未提供名次', evidence=ref))
                report['missingRank'] += 1
                continue
            f = dict(key=f'{sheet}:{r["_row"]}', award=award or r['Award'],
                season=period_display(raw_period), periodId=period_id(raw_period),
                periodDisplay=period_display(raw_period), id=pid, player=players[pid]['name'],
                club=r.get('Club') or r.get('Club_Raw'), rank=rank,
                kind='selection' if rank == '入選' else 'winner' if rank == '1' else 'placing',
                resolved=True, identityRoute=route, evidence=[], primary=ref,
                performance={k: value(next((r[c] for c in cols if value(r.get(c)) is not None), None))
                    for k, cols in {'apps':['Appearances','Apps'], 'goals':['Goals'],
                        'assists':['Assists'], 'rating':['Average_Rating','Rating'],
                        'nationality':['Nationality','Nationality_Raw'], 'age':['Age'],
                        'position':['Position','Position_Raw']}.items()})
            before = len(ledger)
            add(f)
            report['added' if len(ledger) > before else 'merged'] += 1
        counts[sheet] = dict(report)

    grouped = defaultdict(list)
    for f in ledger.values():
        grouped[f['id']].append(f)
    summaries = {r['Player_ID']: r for r in archive.q('SELECT * FROM Barcelona_Player_Career ORDER BY _row')}
    for pid, p in players.items():
        p['awards'] = sorted(grouped[pid], key=lambda f: (f['periodDisplay'] or '', f['award']), reverse=True)
        p['awardCounts'] = {k: sum(f['kind'] == k for f in p['awards']) for k in ['winner', 'selection', 'placing']}
        r = summaries.get(pid)
        p['awardSummary'] = dict(text=r['Major_Awards'],
            evidence=reference(sheet='Barcelona_Player_Career', row=r['_row'], status=r['Derivation_Status'])) if r and value(r['Major_Awards']) else None
    payload['people']['players'].sort(key=lambda p: (-len(p['awards']), -p['apps'], p['name']))
    payload['people']['withAwards'] = sum(bool(p['awards']) for p in players.values())
    skipped = list({(x['evidence']['sheet'], str(x['evidence']['row'])): x for x in skipped}.values())
    payload['people']['awardCoverage'] = dict(sheets=counts, records=len(ledger),
        unassigned=skipped, identityIssues=identity_issues,
        policy='CAF＋結構化獎項表；核對來源列姓名及期間，或 Player_Dim 完全一致且唯一的既有別名；不模糊配對。生涯摘要不另計次數。')
    payload['reference']['rowCount'] = sum(len(t['rows']) for t in tables.values())
    return payload
