"""P1/P2 row-level preservation and non-adoption contracts."""
from collections import Counter
from pathlib import Path
import pytest

from build_site import Archive, collect
from history import integrate_history
from table_roles import COMPLETED_P1_P2, PENDING_INTEGRATION
from evidence import value

DB=Path(__file__).parent/'data/fm24.sqlite'


@pytest.fixture(scope='module')
def archive():
    if not DB.exists(): pytest.skip('run etl.py first')
    a=Archive(DB)
    yield a
    a.con.close()


@pytest.fixture(scope='module')
def payload(archive): return collect(archive)


@pytest.mark.parametrize('table',list(COMPLETED_P1_P2))
def test_every_source_cell_is_preserved(archive,payload,table):
    source=archive.q(f'SELECT * FROM "{table}" ORDER BY _row')
    output=payload['reference']['tables'][table]
    assert len(source)==len(output['rows'])
    for before,after in zip(source,output['rows']):
        assert before['_row']==after['row']
        assert {k:value(v) for k,v in before.items() if k!='_row'}==after['values']


def test_plan_is_completed_without_claiming_all_tables_adopted(payload):
    assert not PENDING_INTEGRATION
    assert len(payload['reference']['tables'])==24
    assert payload['reference']['rowCount']==707


def test_explicit_world_cup_context_overrides_raw_heading(payload):
    t=next(t for t in payload['history']['tournaments'] if t['period']=='2034')
    assert t['host']=='日本'
    assert t['context']['values']['Raw_Heading']=='2038FIFA World Cup'
    assert '南非' in t['context']['values']['Raw_Metadata']
    assert t['groups'] and t['matches']


def test_all_tournament_rows_reached_once(payload):
    for key,unassigned,table,count in [('groups','unassignedGroups','National_Tournament_Groups',208),
                                      ('matches','unassignedMatches','National_Tournament_Matches',141)]:
        actual=[r['row'] for t in payload['history']['tournaments'] for r in t[key]]
        actual += [r['row'] for r in payload['history'][unassigned]]
        assert len(actual)==len(set(actual))==count
        assert Counter(actual)==Counter(r['row'] for r in payload['reference']['tables'][table]['rows'])


def test_duplicate_group_team_is_flagged_without_changing_source(payload):
    t=next(t for t in payload['history']['tournaments'] if t['period']=='2034')
    issue=next(i for i in t['groupIssues'] if i['team']=='新西兰')
    assert len(issue['groups'])==2
    assert len(issue['records'])==2
    assert len(t['groups'])==48


def test_match_date_ranges_and_deciders_not_inferred(payload):
    rs=payload['reference']['tables']['National_Tournament_Matches']['rows']
    assert any(',' in (r['values']['Date_Raw'] or '') for r in rs)
    assert any(r['values']['Result_Note_Raw'] for r in rs)
    assert all('winner' not in r and 'advanced' not in r for r in rs)


def test_madrid_final_does_not_use_old_29_match_snapshot(payload):
    m=next(m for m in payload['history']['madrid'] if m['season']=='2034/35')
    assert m['history']['values']['Matches']=='29'
    assert m['history']['values']['Points']=='74'
    assert m['final'] is not None
    assert m['final']['played']=='38'
    assert m['final']['snapshot'] != '2035-03-27'
    assert len(payload['history']['madrid'])==12


def test_retirement_scopes_stay_distinct(payload):
    r=next(r for r in payload['history']['retirements'] if r['playerId']=='P-0291')
    assert r['profile']['values']['Career_Apps_Raw']=='352'
    refs=r['sections']['Retirement_Career_Totals']
    assert len(refs)==1
    t=next(t for t in payload['reference']['tables'][refs[0]['sheet']]['rows'] if t['row']==refs[0]['row'])
    assert t['values']['Apps_Raw']=='384'
    assert '退役' in r['profile']['values']['Status_Raw']


def test_retirement_sections_all_linked(payload):
    sections=['Retirement_Career_Totals','Retirement_Milestones','Retirement_Narratives',
              'Retirement_Extraction_Issues','Retirement_Honours_Claims']
    for table in sections:
        refs=[r['row'] for p in payload['history']['retirements'] for r in p['sections'][table]]
        assert Counter(refs)==Counter(r['row'] for r in payload['reference']['tables'][table]['rows'])
    claims=payload['reference']['tables']['Retirement_Honours_Claims']['rows']
    assert all(r['values']['Adoption_Status']=='PRESERVED_NOT_SEASONALLY_ADOPTED' for r in claims)


def test_vdv_details_attached_to_existing_facts(payload):
    fs=payload['honours']['facts']['Bundesliga VDV Spieler der Saison']
    assert len(fs)==3
    assert [f['rank'] for f in fs]==['1','2','3']
    assert fs[0]['performance']['apps']=='27'
    assert fs[0]['performance']['goals']=='9'
    assert fs[0]['performance']['assists']=='8'
    assert fs[0]['performance']['rating']=='7.6'


def test_evidence_never_adds_awards_or_replaces_career_totals(archive,payload):
    assert sum(len(fs) for fs in payload['honours']['facts'].values())==1132
    assert len(payload['clasico'])==46
    assert all(r['values']['Matches']=='44' for r in payload['reference']['tables']['Barcelona_RealMadrid_H2H']['rows'])
    baseline={p['id']:p for p in archive.players()}
    for p in payload['players']:
        for field in ['apps','goals','assists','titles']:
            assert p[field]==baseline[p['id']][field]


def test_ambiguous_tournament_source_is_not_assigned(archive,payload):
    from copy import deepcopy
    class DuplicateContext:
        con=archive.con
        def q(self,sql):
            rs=archive.q(sql)
            if 'FROM "National_Tournament_Context"' in sql:
                rs.append(dict(rs[0],_row=900))
            return rs
    result=integrate_history(DuplicateContext(),deepcopy(payload))
    ambiguous=[t for t in result['history']['tournaments'] if t['association']=='ambiguous_context']
    assert len(ambiguous)==2
    assert all(not t['groups'] and not t['matches'] for t in ambiguous)
    assert result['history']['unassignedGroups'] and result['history']['unassignedMatches']
