"""Strict, source-scoped metrics for interactive comparisons. No missing-to-zero."""
import math
from evidence import reference


def metric(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def integrate_experience(archive, payload):
    seasons = {}
    for r in archive.q('SELECT * FROM Barcelona_Season_Master ORDER BY _row'):
        values = {k: metric(r[column]) for k, column in {
            'points':'LaLiga_Points', 'w':'LaLiga_W', 'd':'LaLiga_D', 'l':'LaLiga_L',
            'gf':'LaLiga_GF', 'ga':'LaLiga_GA', 'trophies':'Total_Trophies',
        }.items()}
        values['played'] = sum(values[k] for k in ('w','d','l')) if all(values[k] is not None for k in ('w','d','l')) else None
        seasons[r['Season_ID']] = dict(values, source=reference(sheet='Barcelona_Season_Master', row=r['_row']))
    players = {}
    for r in archive.q('SELECT * FROM Barcelona_Player_Career ORDER BY _row'):
        players[r['Player_ID']] = dict(
            {k:metric(r[col]) for k,col in {'apps':'Apps','goals':'Goals','assists':'Assists',
                'motm':'MOTM','rating':'Avg_Rating','cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}.items()},
            source=reference(sheet='Barcelona_Player_Career', row=r['_row']), seasons=[])
    for r in archive.q("SELECT * FROM Player_Club_Season_Totals WHERE Club_ID='C-0030' AND Statistical_Adoption_Status='ADOPTED' ORDER BY Season_ID, _row"):
        if r['Player_ID'] not in players:
            continue
        players[r['Player_ID']]['seasons'].append(dict(
            {k:metric(r[col]) for k,col in {'apps':'Apps','goals':'Goals','assists':'Assists','motm':'POTM','rating':'Rating',
                'cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}.items()},
            season=r['Season_Display'], source=reference(r['Source_ID'], 'Player_Club_Season_Totals', r['_row'], r['Verification_Status'])))
    payload['experience'] = {'seasons':seasons, 'players':players,
        'scope':'巴塞隆納主表與正式採用逐季觀測；缺值不轉零，不從原始重複列重算生涯。'}
    return payload
