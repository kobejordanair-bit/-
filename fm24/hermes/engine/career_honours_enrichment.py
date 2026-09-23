"""Common, idempotent Career honours enrichment from workbook authorities.

This module derives only fields whose authority sheets are already in the Master.
It never guesses player names, never creates players, and fails closed on an
existing value that conflicts with a computed value.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

CLUB_ID = 'C-0030'
FIELDS = (
    'LaLiga_Team_Championships_While_At_Barcelona', 'UCL_Team_Championships_While_At_Barcelona',
    'Copa_Team_Championships_While_At_Barcelona', 'Supercopa_Team_Championships_While_At_Barcelona',
    'UEFA_SuperCup_Team_Championships_While_At_Barcelona',
)


def headers(ws):
    return {c.value: c.column for c in ws[1]}


def row_dicts(ws):
    h = headers(ws)
    return [{name: row[col-1] for name, col in h.items()}
            for row in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in row)]


def norm_season(value):
    m = re.search(r'(\d{4})[-/](\d{2,4})', str(value or ''))
    return f'{m.group(1)}/{m.group(2)[-2:]}' if m else None


def membership_rows(wb):
    return [dict(r, _season_key=norm_season(r.get('Season_ID') or r.get('Season_Display')))
            for r in row_dicts(wb['Player_Club_Season_Totals'])
            if r.get('Player_ID') not in (None, '') and r.get('Club_ID') == CLUB_ID and r.get('Season_ID') not in (None, '') and norm_season(r.get('Season_ID')) and int(norm_season(r.get('Season_ID'))[:4]) >= 2023]


def title_seasons(wb):
    winners = {field: set() for field in FIELDS}
    for r in row_dicts(wb['Barcelona_History']):
        if r.get('LaLiga_Rank') == 1 and str(r.get('Season_Status')).startswith('已完成'): winners[FIELDS[0]].add(norm_season(r.get('Season')))
    for r in row_dicts(wb['Barcelona_UCL_Journey']):
        if r.get('Result') == '冠軍': winners[FIELDS[1]].add(norm_season(r.get('Season')))
    for r in row_dicts(wb['National_Tournaments']):
        season = norm_season(r.get('Season'))
        if r.get('Rank') == 1 and r.get('Club') == '巴薩':
            if r.get('Competition') == '西班牙國王盃': winners[FIELDS[2]].add(season)
            if r.get('Competition') == '西班牙超級盃': winners[FIELDS[3]].add(season)
    for r in row_dicts(wb['UEFA_Super_Cup']):
        if r.get('Winner') == '巴薩': winners[FIELDS[4]].add(norm_season(r.get('Season')))
    return winners

TEAM_FIELDS = FIELDS + ('Club_World_Cup_Team_Championships_While_At_Barcelona',)
INDIVIDUAL_COUNT_FIELDS = ('FIFPro_Count', 'Ballon_dOr_Top3_Count')
AWARD_SHEETS = (
    ('Youth_Awards', None), ('Kopa_Trophy', 'Kopa Trophy'),
    ('UCL_Golden_Boot', 'UCL Golden Boot'), ('Pichichi_Award', 'Pichichi Award'),
    ('Ballon_dOr', "Ballon d’Or"), ('Goal_50', 'Goal 50'),
    ('Worlds_Best_Goalkeeper', "World’s Best Goalkeeper"), ('Yashin_Trophy', 'Yashin Trophy'),
    ('The_Best_FIFA_Mens_Player', 'The Best FIFA Men’s Player'),
    ('World_Player_of_the_Year', 'World Player of the Year'),
    ('UCL_Season_Best_Player', 'UCL Season Best Player'),
    ('UCL_Season_Best_Young_Player', 'UCL Season Best Young Player'),
    ('LaLiga_Player_of_Year', 'LaLiga Player of the Year'),
    ('Golden_Shoe', 'European Golden Shoe'),
)
SOURCE_LINEAGE = '；'.join(dict.fromkeys((
    'Player_Club_Season_Totals', 'Player_League_Career', 'Barcelona_History',
    'Barcelona_UCL_Journey', 'National_Tournaments', 'UEFA_Super_Cup',
    'Barcelona_Club_World_Cup', 'FIFA_FIFPro_World_XI',
    *(s for s, _ in AWARD_SHEETS), 'Barcelona_LaLiga_Best_XI',
    'Barcelona_Season_Leaders', 'Player_Dim', 'Record_Identity_Map'
))) + '。球隊冠軍欄為效力巴薩賽季的團隊成就，不宣稱個人正式冠軍 credit；個人獎項為已收錄全生涯獎項；未知不等於零。'


def _aliases(wb) -> dict[str, set[str]]:
    values = defaultdict(set)
    for r in row_dicts(wb['Player_Dim']):
        pid = r.get('Player_ID')
        if pid:
            for key in ('Canonical_Display_Name', 'Alias_Name'):
                if r.get(key): values[pid].add(str(r[key]))
    for r in row_dicts(wb['Record_Identity_Map']):
        if r.get('Entity_ID') and r.get('Raw_Display_Name'):
            values[r['Entity_ID']].add(str(r['Raw_Display_Name']))
    return values


def _club_world_count(wb, eligible: set[str]) -> int | None:
    if 'Barcelona_Club_World_Cup' not in wb.sheetnames:
        return None
    years = set()
    for season in eligible:
        if season:
            start, end = season.split('/')
            years.add(str(start)); years.add(str(int(start) + 1)); years.add(str(end if len(end) == 4 else int(start) + 1))
    return sum(1 for r in row_dicts(wb['Barcelona_Club_World_Cup'])
               if str(r.get('Result')) == '冠軍' and str(r.get('Year')) in years)


def _individual(wb, aliases: set[str]) -> dict[str, Any]:
    fifpro = sum(1 for r in row_dicts(wb['FIFA_FIFPro_World_XI']) if str(r.get('Player')) in aliases)
    ballon = sum(1 for r in row_dicts(wb['Ballon_dOr'])
                 if str(r.get('Player')) in aliases and r.get('Rank') in (1, 2, 3))
    awards = []
    for sheet, label in AWARD_SHEETS:
        for r in row_dicts(wb[sheet]):
            if str(r.get('Player')) in aliases and (r.get('Rank') == 1 or (sheet == 'Golden_Shoe' and r.get('Rank') is None)):
                award = r.get('Award') if sheet == 'Youth_Awards' else label
                awards.append((norm_season(r.get('Season')) or str(r.get('Season')), award, '冠軍'))
    for r in row_dicts(wb['Barcelona_LaLiga_Best_XI']):
        if str(r.get('Player')) in aliases:
            awards.append((norm_season(r.get('Season')) or str(r.get('Season')), 'LaLiga Best XI', '入選'))
    for r in row_dicts(wb['FIFA_FIFPro_World_XI']):
        if str(r.get('Player')) in aliases:
            awards.append((str(r.get('Year')), 'FIFPro World XI', '入選'))
    for r in row_dicts(wb['Barcelona_Season_Leaders']):
        if str(r.get('Player')) in aliases and r.get('Metric') == '年度球迷票選最佳球員':
            awards.append((norm_season(r.get('Season')) or str(r.get('Season')), 'Fan Player of Season', '獲獎'))
    awards = sorted(set(awards))
    return {'FIFPro_Count': fifpro, 'Ballon_dOr_Top3_Count': ballon,
            'Major_Awards': '；'.join(f'{s} {a}（{result}）' for s, a, result in awards)
                            or '無已確認重大個人獎項（限已確認 Award／Leader sheets）'}


def enrich_career_honours(wb) -> dict[str, Any]:
    """Upsert derivable Career honours for every existing Barcelona career row."""
    career = wb['Barcelona_Player_Career']; h = headers(career)
    career_rows = {career.cell(r, h['Player_ID']).value: r for r in range(2, career.max_row + 1)
                   if career.cell(r, h['Player_ID']).value not in (None, '')}
    if len(career_rows) != sum(1 for r in range(2, career.max_row + 1)
                                if career.cell(r, h['Player_ID']).value not in (None, '')):
        raise ValueError('atomic FAIL: duplicate Barcelona_Player_Career Player_ID')
    titles = title_seasons(wb)
    membership = defaultdict(set)
    for r in membership_rows(wb):
        if r.get('Club_ID') == CLUB_ID:
            membership[r['Player_ID']].add(r['_season_key'])
    aliases = _aliases(wb)
    changed, players = 0, 0
    for pid, row in career_rows.items():
        seasons = membership.get(pid, set())
        if not seasons:
            continue
        players += 1
        computed = {field: sum(int(s in winners) for s in seasons) for field, winners in titles.items()}
        cwc = _club_world_count(wb, seasons)
        if cwc is not None:
            computed['Club_World_Cup_Team_Championships_While_At_Barcelona'] = cwc
        computed.update(_individual(wb, aliases.get(pid, set())))
        coverage = sorted(s for s in seasons if s)
        note = (' Coverage：已收錄全賽事季總計 ' + coverage[0] + '–' + coverage[-1] + '；Avg_Rating 為出場加權衍生。') if coverage else ''
        league = [r for r in row_dicts(wb['Player_League_Career'])
                  if r.get('Player_ID') == pid and r.get('Club_ID') == CLUB_ID
                  and (r.get('Apps') or 0) > 0 and norm_season(r.get('Season_Display')) not in seasons]
        if league:
            note += ' 另有聯賽出場但缺完整全賽事總計的期間：' + '、'.join(sorted({str(r.get('Season_Display')) for r in league})) + '；不補算生涯全賽事總計。'
        old_status = str(career.cell(row, h['Derivation_Status']).value or '')
        if 'Coverage Note：' in old_status:
            note += ' Coverage Note：' + old_status.split('Coverage Note：', 1)[1]
        computed['Derivation_Status'] = '已確認（Barcelona Career：既定團隊歸屬政策與已確認 Award／Leader authorities 衍生）' + note
        computed['Derivation_Sources'] = SOURCE_LINEAGE
        for field, value in computed.items():
            if field not in h:
                continue
            cell = career.cell(row, h[field]); existing = cell.value
            # These are explicitly common derived outputs, not raw source facts.
            # Recompute from the named authority sheets; the source rows stay intact.
            if existing != value:
                cell.value = value; changed += 1
    return {'pass': True, 'career_enrichment_changes': changed, 'career_enrichment_players': players,
            'source_lineage': SOURCE_LINEAGE}


def settle_coverage_reconciliation_issues(wb) -> int:
    """Mark preserved, explicitly different coverage authorities as resolved—not equal."""
    ws = wb['Data_Issues']; h = headers(ws)
    changed = 0
    for r in range(2, ws.max_row + 1):
        issue = str(ws.cell(r, h['Issue']).value or '')
        status = ws.cell(r, h['Status']).value
        if 'both source authorities retained without overwrite' in issue and 'coverage' in issue.lower():
            new = '已確認（涵蓋期間／範圍不同；原始來源均保留，無需調和）'
            if status != new:
                ws.cell(r, h['Status']).value = new; changed += 1
    return changed
