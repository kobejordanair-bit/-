"""Reader-facing P0 evidence. Links never create another statistical fact.

Worksheet row numbers are Excel locators, not original TXT line numbers.
Period aliases come exclusively from Period_Dim; ambiguous aliases stay unknown.
"""
from collections import Counter, defaultdict
import re


def value(v):
    return None if v is None or str(v).strip() in ('', 'NULL', 'null') else str(v).strip()


def numeric(v):
    try:
        return float(v) if value(v) is not None else None
    except (ValueError, TypeError):
        return None


class Periods:
    def __init__(self, rows):
        self.by_id = {}
        self.aliases = defaultdict(set)
        for r in rows:
            pid = r['Period_ID']
            p = self.by_id.setdefault(pid, dict(id=pid, display=r['Canonical_Period_Display'],
                type=r['Period_Type'], start=numeric(r['Start_Year']), end=numeric(r['End_Year']),
                aliases=set(), status=r['Verification_Status']))
            for alias in (pid, r['Source_Period_Display'], r['Canonical_Period_Display']):
                if value(alias):
                    self.aliases[alias].add(pid)
                    if alias != pid:
                        p['aliases'].add(alias)

    def resolve(self, raw):
        ids = self.aliases.get(raw, set())
        return next(iter(ids)) if len(ids) == 1 else None

    def display(self, raw):
        return self.by_id.get(self.resolve(raw), {}).get('display') or raw

    def records(self):
        return [dict(p, aliases=sorted(p['aliases']), sourceDisplay=' / '.join(sorted(p['aliases'])))
                for p in sorted(self.by_id.values(), key=lambda p: (p['start'] or 0, p['id']))]


def reference(source=None, sheet=None, row=None, status=None, **extra):
    return dict(source=value(source), sheet=value(sheet), row=row, status=value(status), **extra)


def link_awards(facts, links):
    """Resolve the two observed key formats, then a unique exact source locator.

    A locator is only a fallback for historical keys not reconstructed from the
    current identity. It must identify one canonical row and one Fact_Key.
    """
    by_key, by_locator, fact_locators = defaultdict(list), defaultdict(set), Counter()
    for l in links:
        by_key[l['Fact_Key']].append(l)
        by_locator[(l['Source_ID'], l['Origin_Sheet'], l['Origin_Row'])].add(l['Fact_Key'])
    for f in facts:
        fact_locators[(f['Source_ID'], f['Origin_Sheet'], f['Origin_Row'])] += 1
    matched, used = {}, set()
    for f in facts:
        keys = {
            f"{f['Award']}|{f['Season']}|{f['Player_ID'] or f['Player_Raw']}|{f['Rank']}",
            f"{f['Season']}|{f['Award']}|{f['Rank']}|{f['Player_Raw']}|{f['Source_ID']}",
        } & by_key.keys()
        mode = 'Fact_Key'
        if not keys:
            loc = (f['Source_ID'], f['Origin_Sheet'], f['Origin_Row'])
            candidates = by_locator.get(loc, set())
            if fact_locators[loc] == 1 and len(candidates) == 1:
                keys = candidates
                mode = 'exact_source_locator'
        matched[f['_row']] = (keys, mode)
    # Never attach a shared ambiguous key to more than one canonical fact.
    owners = Counter(k for keys, _ in matched.values() for k in keys)
    out = []
    for f in facts:
        keys, mode = matched[f['_row']]
        keys = sorted(k for k in keys if owners[k] == 1)
        evidence = []
        for k in keys:
            for l in by_key[k]:
                used.add(l['_row'])
                evidence.append(reference(l['Source_ID'], l['Origin_Sheet'], l['Origin_Row'],
                    l['Verification_Status'], factKey=k, role=l['Link_Role'],
                    linkRow=l['_row'], match=mode))
        raw_rank = value(f['Rank'])
        selection = raw_rank == '入選' or (raw_rank or '').startswith('SELECTION-')
        out.append(dict(key=f"CAF:{f['_row']}", award=f['Award'], season=f['Season'],
            player=f['Player_Raw'], id=f['Player_ID'], club=f['Club_Raw'], resolved=bool(f['Player_ID']),
            rank=raw_rank, kind='selection' if selection else 'winner' if raw_rank == '1' else 'placing',
            evidence=evidence, factKeys=keys,
            primary=reference(f['Source_ID'], f['Origin_Sheet'], f['Origin_Row'], f['Verification_Status']),
            canonicalRow=f['_row']))
    unmatched = [dict(factKey=l['Fact_Key'], linkRow=l['_row'], role=l['Link_Role'],
        **reference(l['Source_ID'], l['Origin_Sheet'], l['Origin_Row'], l['Verification_Status']))
        for l in links if l['_row'] not in used]
    return out, unmatched


STAT_FIELDS = {'Apps': 'Apps', 'Starts': 'Starts', 'Goals': 'Goals', 'Assists': 'Assists',
               'Avg_Rating': 'Rating', 'MOTM': 'POTM', 'Clean_Sheets': 'Clean_Sheets',
               'Yellow': 'Yellow', 'Red': 'Red', 'Goals_Conceded': 'Goals_Conceded'}
TITLE_FIELDS = {
    '西甲': 'LaLiga_Team_Championships_While_At_Barcelona',
    '歐冠': 'UCL_Team_Championships_While_At_Barcelona',
    '國王盃': 'Copa_Team_Championships_While_At_Barcelona',
    '西超盃': 'Supercopa_Team_Championships_While_At_Barcelona',
    '歐超盃': 'UEFA_SuperCup_Team_Championships_While_At_Barcelona',
}


def integrate(archive, payload):
    periods = Periods(archive.q('SELECT * FROM Period_Dim ORDER BY _row'))
    payload['sources']['periods'] = periods.records()
    facts, unlinked = link_awards(archive.q('SELECT * FROM Canonical_Award_Facts ORDER BY _row'),
                                 archive.q('SELECT * FROM Award_Fact_Source_Links ORDER BY _row'))
    by_award, by_player = defaultdict(list), defaultdict(list)
    for f in facts:
        f['periodId'] = periods.resolve(f['season'])
        f['periodDisplay'] = periods.display(f['season'])
        by_award[f['award']].append(f)
        if f['id']:
            by_player[f['id']].append(f)
    def fact_order(f):
        period = periods.by_id.get(f['periodId'], {})
        raw_year = re.search(r'\d{4}', f['season'] or '')
        year = period.get('start') or (int(raw_year.group()) if raw_year else 0)
        rank = re.search(r'\d+', f['rank'] or '')
        return (-year, int(rank.group()) if rank else 0, f['canonicalRow'])
    for group in [*by_award.values(), *by_player.values()]:
        group.sort(key=fact_order)
    payload['honours']['facts'] = dict(by_award)
    # Legacy consumers retain winners; their counts remain based on facts only.
    payload['honours']['winners'] = {k: [f for f in fs if f['kind'] == 'winner'] for k, fs in by_award.items()}
    payload['honours']['index'] = [dict(award=r['Award'], category=r['Category'], sheet=r['Worksheet'],
        status=r['Data_Status'], grain=r['Record_Grain'], note=r['Notes'], row=r['_row'],
        canonicalCount=len(by_award.get(r['Award'], []))) for r in archive.q('SELECT * FROM Award_Index ORDER BY _row')]
    payload['sources']['unlinkedAwardEvidence'] = unlinked
    payload['sources']['awardLinkSummary'] = dict(total=sum(len(f['evidence']) for f in facts) + len(unlinked),
        linked=sum(len(f['evidence']) for f in facts), unlinked=len(unlinked),
        factsWithLinks=sum(bool(f['evidence']) for f in facts), factsWithoutLinks=sum(not f['evidence'] for f in facts))
    for p in payload['people']['players']:
        p['awards'] = by_player.get(p['id'], [])

    provenance, transfers = defaultdict(list), defaultdict(list)
    unassigned = []
    for r in archive.q('SELECT * FROM Season_Master_Field_Provenance ORDER BY _row'):
        record = dict(group=r['Field_Group'], date=r['Source_Date'], coverage=r['Coverage'],
            adoption=r['Final_Result_Status'], evidence=reference(r['Source_ID'], r['Source_Sheet'],
            status=r['Final_Result_Status']), row=r['_row'])
        provenance[periods.resolve(r['Season'])].append(record)
    for r in archive.q('SELECT * FROM Barcelona_Transfer_Totals ORDER BY _row'):
        record = dict(direction=r['Direction'], total=value(r['Displayed_Total']), note=r['Notes'],
            evidence=reference(r['Source_ID'], 'Barcelona_Transfer_Totals', r['_row'], r['Verification_Status']))
        transfers[periods.resolve(r['Season'])].append(record)
    for s in payload['seasons']:
        pid = periods.resolve(s['id'])
        s['provenance'] = provenance.pop(pid, []) if pid else []
        s['transferTotals'] = transfers.pop(pid, []) if pid else []
    for name, groups in [('Season_Master_Field_Provenance', provenance), ('Barcelona_Transfer_Totals', transfers)]:
        for pid, records in groups.items():
            unassigned.append(dict(sheet=name, periodId=pid, records=records))

    adopted = defaultdict(list)
    for r in archive.q("SELECT * FROM Player_Club_Season_Totals WHERE Club_ID='C-0030' AND Statistical_Adoption_Status='ADOPTED'"):
        adopted[(r['Player_ID'], periods.resolve(r['Season_ID']))].append(r)
    stats, honours, notes = defaultdict(list), defaultdict(list), []
    for r in archive.q('SELECT * FROM Barcelona_Player_Season_Stats ORDER BY _row'):
        if not r['Player_ID'] or not periods.resolve(r['Season_ID']):
            notes.append(dict(row=r['_row'], text=r['Season_ID'], playerId=r['Player_ID']))
            continue
        key = (r['Player_ID'], periods.resolve(r['Season_ID']))
        matches = adopted.get(key, [])
        diff = []
        if len(matches) == 1:
            for a, b in STAT_FIELDS.items():
                if numeric(r[a]) != numeric(matches[0][b]):
                    diff.append(dict(field=a, worksheet=value(r[a]), adopted=value(matches[0][b])))
        stats[r['Player_ID']].append(dict(season=periods.display(r['Season_ID']), periodId=key[1],
            fields={k: value(r[k]) for k in [*STAT_FIELDS, 'Minutes', 'Major_Awards', 'Squad_Role']},
            comparison='no_unique_adopted' if len(matches) != 1 else 'different' if diff else 'consistent',
            differences=diff, adoptedRows=[m['_row'] for m in matches],
            evidence=reference(r['Source_ID'], 'Barcelona_Player_Season_Stats', r['_row'], r['Verification_Status'])))
    for r in archive.q('SELECT * FROM Barcelona_Player_Season_Honours ORDER BY _row'):
        honours[r['Player_ID']].append(dict(season=periods.display(r['Season_ID']),
            periodId=periods.resolve(r['Season_ID']), apps=value(r['Apps']), policy=r['Attribution_Policy'],
            titles={k: numeric(r[v]) for k, v in TITLE_FIELDS.items()},
            lineage=r['Authority_Lineage'], sourceTables=r['Source_Reference'],
            evidence=reference(sheet='Barcelona_Player_Season_Honours', row=r['_row'], status=r['Verification_Status'])))
    for p in payload['players']:
        p['seasonVerification'] = stats.get(p['id'], [])
        p['seasonHonours'] = honours.get(p['id'], [])
    for p in payload['people']['players']:
        p['seasonVerification'] = stats.pop(p['id'], [])
        p['seasonHonours'] = honours.pop(p['id'], [])
    payload['sources']['seasonStatsNotes'] = notes
    payload['sources']['unassignedEvidence'] = unassigned + [dict(sheet=sheet, playerId=pid, records=rs)
        for sheet, group in [('Barcelona_Player_Season_Stats', stats), ('Barcelona_Player_Season_Honours', honours)]
        for pid, rs in group.items()]
    # The registry counter is intentionally scoped; it is not a global source audit.
    payload['sources']['citationScope'] = ['Canonical_Award_Facts', 'Player_Club_Season_Totals',
        'Domestic_League_Standings', 'World_Timeline', 'El_Clasico_Match_History']
    return payload
