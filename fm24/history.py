"""P1 reader views and P2 evidence. Never promote source claims into facts."""
from collections import defaultdict

from evidence import Periods, reference, value
from resolver import ClubResolver, league_key
from table_roles import COMPLETED_P1_P2


def integrate_history(archive, payload):
    tables = {}
    history_tables = dict(COMPLETED_P1_P2, Retirement_Career_History=('補充', '退役生涯分段；保留來源口徑，不重算摘要。'))
    for table, (priority, rule) in history_tables.items():
        rows = archive.q(f'SELECT * FROM "{table}" ORDER BY _row')
        columns = [k for k in rows[0] if k != '_row'] if rows else []
        tables[table] = dict(priority=priority, rule=rule, columns=columns, rows=[
            dict(row=r['_row'], values={k: value(r[k]) for k in columns},
                 source=reference(r.get('Source_ID'), table, r['_row'], r.get('Verification_Status')))
            for r in rows])
    def rows(table):
        return tables[table]['rows']
    def refs(table, records=None):
        return [dict(sheet=table, row=r['row']) for r in (rows(table) if records is None else records)]

    periods = Periods(archive.q('SELECT * FROM Period_Dim ORDER BY _row'))
    tournaments = []
    assigned_groups, assigned_matches = set(), set()
    contexts = rows('National_Tournament_Context')
    source_contexts = defaultdict(list)
    for c in contexts:
        source_contexts[c['values']['Source_ID']].append(c)
    # Source association is authoritative; conflicting contexts are left unassigned.
    for c in contexts:
        v = c['values']
        source = v['Source_ID']
        unique = bool(source) and len(source_contexts[source]) == 1
        groups = [r for r in rows('National_Tournament_Groups') if unique and r['values']['Source_ID'] == source]
        matches = [r for r in rows('National_Tournament_Matches') if unique and r['values']['Source_ID'] == source]
        assigned_groups.update(r['row'] for r in groups)
        assigned_matches.update(r['row'] for r in matches)
        teams = defaultdict(list)
        for r in groups:
            if r['values']['Team_Raw']:
                teams[r['values']['Team_Raw'].strip()].append(r)
        group_issues = [dict(team=team, groups=list(dict.fromkeys(r['values']['Group_Raw'] for r in rs)),
                            records=refs('National_Tournament_Groups', rs))
                        for team, rs in teams.items()
                        if len({r['values']['Group_Raw'] for r in rs}) > 1]
        tournaments.append(dict(id=f"context-{c['row']}", name=v['Canonical_Tournament'],
            period=v['Canonical_Period'], host=v['Canonical_Host'], context=c,
            groups=refs('National_Tournament_Groups', groups), matches=refs('National_Tournament_Matches', matches),
            groupIssues=group_issues,
            association='unique_source_context' if unique else 'ambiguous_context'))
    tournaments.sort(key=lambda t: (t['period'] or '', t['name'] or ''), reverse=True)

    retired = []
    profiles = rows('Retirement_Profiles')
    for profile in profiles:
        v = profile['values']
        sections = {}
        # One source block describes one retirement observation. Player_ID alone
        # must not combine later snapshots, or the distinct scopes disappear.
        for table in ('Retirement_Career_Totals','Retirement_Career_History','Retirement_Milestones','Retirement_Narratives',
                      'Retirement_Extraction_Issues','Retirement_Honours_Claims'):
            linked = [r for r in rows(table) if all(r['values'].get(k) == v.get(k)
                for k in ('Player_ID','Source_ID','Source_Block_Index'))]
            sections[table] = refs(table, linked)
        retired.append(dict(id=f"retired-{profile['row']}", playerId=v['Player_ID'], name=v['Name_Raw'],
            profile=profile, sections=sections))
    for p in [*payload['people']['players'], *payload['players']]:
        p['retirementIds'] = [r['id'] for r in retired if r['playerId'] and r['playerId'] == p['id']]

    clubs = ClubResolver(archive.con)
    madrid_id = clubs.resolve('皇家馬德里')
    standings = archive.q('SELECT * FROM Domestic_League_Standings ORDER BY Snapshot DESC, _row')
    comparisons = []
    for row in rows('Real_Madrid_LaLiga_History'):
        v = row['values']
        period_id = periods.resolve(v['Season'])
        candidates = [r for r in standings if madrid_id and clubs.resolve(r['Club_Raw']) == madrid_id
            and league_key(r['Competition_Raw']) == 'LALIGA'
            and (periods.resolve(r['Season']) == period_id if period_id else r['Season'] == v['Season'])
            and 'FINAL' in (r['Season_Status'] or '')]
        latest_date = candidates[0]['Snapshot'] if candidates else None
        latest = [r for r in candidates if r['Snapshot'] == latest_date]
        final = latest[0] if len(latest) == 1 else None
        comparisons.append(dict(season=v['Season'], history=row,
            final=dict(rank=value(final['Rank']), played=value(final['Played']), points=value(final['Points']),
                snapshot=final['Snapshot'], evidence=reference(final.get('Source_ID'),
                'Domestic_League_Standings',final['_row'],final['Season_Status'])) if final else None,
            status='final_available' if final else 'no_unique_final'))

    for s in payload['seasons']:
        s['historyRefs'] = refs('Barcelona_History', [r for r in rows('Barcelona_History')
            if periods.resolve(r['values']['Season']) == s['id']])
    by_locator = {(table, str(r['row'])):r for table in tables for r in rows(table)}
    for fs in payload['honours']['facts'].values():
        for f in fs:
            loc = (f['primary']['sheet'], str(f['primary']['row']))
            row = by_locator.get(loc)
            if row and loc[0] == 'Bundesliga_VDV_Player':
                v = row['values']
                f['performance'] = dict(apps=v['Appearances'], goals=v['Goals'], assists=v['Assists'],
                    rating=v['Rating'], nationality=v['Nationality_Raw'], age=v['Age'], position=v['Position_Raw'])
    payload['reference'] = dict(tables=tables, rowCount=sum(len(t['rows']) for t in tables.values()))
    payload['history'] = dict(tournaments=tournaments, retirements=retired, madrid=comparisons,
        unassignedGroups=refs('National_Tournament_Groups',[r for r in rows('National_Tournament_Groups') if r['row'] not in assigned_groups]),
        unassignedMatches=refs('National_Tournament_Matches',[r for r in rows('National_Tournament_Matches') if r['row'] not in assigned_matches]))
    return payload
