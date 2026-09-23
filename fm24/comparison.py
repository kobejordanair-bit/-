"""Source-scoped records for the unified world player comparison."""
from collections import defaultdict
import re
from experience import metric
from evidence import reference, value

METRICS = {'apps':'Apps','goals':'Goals','assists':'Assists','motm':'POTM','rating':'Rating',
           'cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}
# Explicit statistical scopes found in the workbook, not fuzzy competition matching.
LEAGUE_SCOPES = {'League', '联赛', '聯賽', 'LaLiga EA Sports', '2ª Federación III', 'Trendyol Süper Lig'}


def resolve_league(rows):
    """One observation per player/period/club; retain every competing source."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r['period'], r['clubId'] or r['club'])].append(r)
    result = []
    for candidates in groups.values():
        dates = {r['date'] for r in candidates}
        latest = max(dates) if None not in dates else None
        current = [r for r in candidates if r['date'] == latest] if latest else candidates
        # Same observation can be printed in both career and competition tables.
        # Merge only compatible cells, with all references retained. Never add them.
        values = {k:{r[k] for r in current if r[k] is not None} for k in METRICS}
        conflict = any(len(v)>1 for v in values.values())
        chosen = dict(current[0])
        chosen.update({k: next(iter(v)) if len(v)==1 else None for k,v in values.items()})
        chosen['fieldConflicts'] = [k for k,v in values.items() if len(v)>1]
        chosen['observations'] = candidates
        chosen['references'] = [r['source'] for r in current]
        chosen['resolution'] = ('來源衝突，待核對' if conflict else
                                '採較新快照，舊觀測不重複加總' if len(current)<len(candidates) else
                                '同一範圍的相容觀測合併，僅計一次' if len(candidates)>1 else '單一來源')
        result.append(chosen)
    return sorted(result, key=lambda r:(r['period'] or '',r['clubId'] or r['club'] or ''))


def integrate_comparison(archive, payload):
    from build_site import TECHNICAL, MENTAL, PHYSICAL
    players={p['id']:dict(league=[],club=[],profiles=[],snapshots=[],leagueSummaries=[]) for p in payload['people']['players']}
    sources = {r['Source_ID']: r for r in archive.q('SELECT Source_ID, Season_Context FROM Source_Index')}
    dates = defaultdict(set)
    profiles = archive.q('SELECT * FROM Player_Profile_Snapshots ORDER BY Snapshot_Date DESC, _row')
    summaries = archive.q('SELECT * FROM Player_Career_Summaries ORDER BY Snapshot_Date DESC, _row')
    for r in profiles + summaries:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(r['Snapshot_Date'] or '')):
            dates[(r['Source_ID'],r['Player_ID'])].add(r['Snapshot_Date'])
    def observation(r, sheet):
        context = sources.get(r['Source_ID'],{}).get('Season_Context') or ''
        known = dates[(r['Source_ID'],r['Player_ID'])] or set(re.findall(r'\d{4}-\d{2}-\d{2}',context))
        return dict({k:metric(r.get(col)) for k,col in METRICS.items()},
            season=r['Season_Display'],period=r['Season_ID'],club=r['Club_Raw'],clubId=r['Club_ID'],
            league=r.get('League_Raw') or r.get('Competition_Raw'),fact=r['Fact_ID'],
            date=next(iter(known)) if len(known)==1 else None,context=context,
            adoption=r['Statistical_Adoption_Status'],
            source=reference(r['Source_ID'],sheet,r['_row'],r['Verification_Status']))
    rows=archive.q("SELECT * FROM Player_League_Career WHERE Statistical_Adoption_Status='ADOPTED' ORDER BY Season_ID, _row")
    for r in rows:
        if r['Player_ID'] not in players:continue
        players[r['Player_ID']]['league'].append(observation(r,'Player_League_Career'))
    for r in archive.q("SELECT * FROM Player_Club_Competition_Stats WHERE Statistical_Adoption_Status='ADOPTED' ORDER BY _row"):
        if r['Player_ID'] in players and r['Competition_Raw'] in LEAGUE_SCOPES:
            players[r['Player_ID']]['league'].append(observation(r,'Player_Club_Competition_Stats'))
    for p in players.values():
        p['league'] = resolve_league(p['league'])
    # Season totals already include the source's club competitions. Never add
    # league/competition rows to these totals, or mix in national-team matches.
    for r in archive.q("SELECT * FROM Player_Club_Season_Totals WHERE Statistical_Adoption_Status='ADOPTED' ORDER BY Season_ID, _row"):
        if r['Player_ID'] in players:
            players[r['Player_ID']]['club'].append(observation(r,'Player_Club_Season_Totals'))
    for p in players.values():
        p['club'] = resolve_league(p['club'])
    for r in summaries:
        if r['Player_ID'] in players and r['Scope']=='League career total' and r['Team_Level']=='Club':
            players[r['Player_ID']]['leagueSummaries'].append(dict(
                {k:metric(r.get(col)) for k,col in METRICS.items()},date=r['Snapshot_Date'],
                source=reference(r['Source_ID'],'Player_Career_Summaries',r['_row'],r['Verification_Status'])))
    for r in profiles:
        if r['Player_ID'] not in players:continue
        players[r['Player_ID']]['profiles'].append(dict(date=value(r['Snapshot_Date']),position=value(r['Position_Raw']),
            nationality=value(r['Nationality_Raw']),club=value(r['Current_Club_Raw']),
            source=reference(r['Source_ID'],'Player_Profile_Snapshots',r['_row'],r['Verification_Status'])))
    metadata={'Player_ID','Snapshot_Date','Attribute_Schema','Source_ID','Verification_Status','_row'}
    for sheet,schema in [('Player_Attr_Snap_O','OUTFIELD'),('Player_Attr_Snap_G','GOALKEEPER')]:
        for r in archive.q(f'SELECT * FROM {sheet} ORDER BY Snapshot_Date DESC, _row'):
            if r['Player_ID'] not in players:continue
            technical=TECHNICAL if schema=='OUTFIELD' else [k for k in r if k not in metadata and k not in MENTAL+PHYSICAL]
            groups={}
            for label,keys in [('技術' if schema=='OUTFIELD' else '門將',technical),('心理',MENTAL),('體能',PHYSICAL)]:
                # Invalid, absent, and out-of-range values never become guessed attributes.
                groups[label]=[(k.replace('_',' '),metric(r[k])) for k in keys if metric(r.get(k)) is not None and 1<=metric(r[k])<=20]
            players[r['Player_ID']]['snapshots'].append(dict(id=f"{sheet}:{r['_row']}",date=value(r['Snapshot_Date']),schema=schema,
                groups=groups,source=r['Source_ID'],evidence=reference(r['Source_ID'],sheet,r['_row'],r['Verification_Status'])))
    for p in players.values():p['snapshots'].sort(key=lambda r:r['date'] or '',reverse=True)
    payload['comparison']=dict(players=players,leaguePlayers=sum(bool(p['league']) for p in players.values()),
        clubPlayers=sum(bool(p['club']) for p in players.values()),clubRows=sum(len(p['club']) for p in players.values()),
        leagueRows=sum(len(p['league']) for p in players.values()),snapshotPlayers=sum(bool(p['snapshots']) for p in players.values()),
        policy='聯賽使用兩張表明示 ADOPTED 的聯賽觀測，同球員／期間／俱樂部採唯一較新日期，相容同日欄位合併且僅計一次；不明日期或同日矛盾欄位停止加總。原檔生涯總計按快照日期獨立呈現，不混入逐季加總。')
    return payload
