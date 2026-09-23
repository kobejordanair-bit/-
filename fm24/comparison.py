"""Source-scoped records for the unified world player comparison."""
from collections import defaultdict
from experience import metric
from evidence import reference, value


def integrate_comparison(archive, payload):
    from build_site import TECHNICAL, MENTAL, PHYSICAL
    players={p['id']:dict(league=[],profiles=[],snapshots=[]) for p in payload['people']['players']}
    metrics={'apps':'Apps','goals':'Goals','assists':'Assists','motm':'POTM','rating':'Rating',
             'cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}
    rows=archive.q("SELECT * FROM Player_League_Career WHERE Statistical_Adoption_Status='ADOPTED' ORDER BY Season_ID, _row")
    for r in rows:
        if r['Player_ID'] not in players:continue
        players[r['Player_ID']]['league'].append(dict(
            {k:metric(r.get(col)) for k,col in metrics.items()},season=r['Season_Display'],period=r['Season_ID'],
            club=r['Club_Raw'],clubId=r['Club_ID'],league=r['League_Raw'],fact=r['Fact_ID'],
            adoption=r['Statistical_Adoption_Status'],source=reference(r['Source_ID'],'Player_League_Career',r['_row'],r['Verification_Status'])))
    for r in archive.q('SELECT * FROM Player_Profile_Snapshots ORDER BY Snapshot_Date DESC, _row'):
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
        leagueRows=sum(len(p['league']) for p in players.values()),snapshotPlayers=sum(bool(p['snapshots']) for p in players.values()),
        policy='聯賽僅使用明示 ADOPTED 的 Player_League_Career。跨季累計是已收錄範圍，不是完整生涯宣稱；缺值不補零，重複球季／俱樂部或 Fact_ID 阻止加總。')
    return payload
