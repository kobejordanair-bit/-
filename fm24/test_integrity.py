"""Regression contracts for read-side integrity repairs; Master stays unchanged."""
from collections import Counter
from pathlib import Path
import pytest
from build_site import Archive, collect
from data_rules import issue_bucket, snapshot_order, snapshot_state, transfer_direction
from evidence import value
from resolver import ClubResolver

@pytest.fixture(scope='module')
def archive():
    a=Archive(Path(__file__).parent/'data/fm24.sqlite')
    yield a
    a.con.close()

@pytest.fixture(scope='module')
def payload(archive): return collect(archive)

@pytest.mark.parametrize('status,expected',[
    ('已解決','resolved'),('已確認（使用者文字）','resolved'),
    ('RESOLVED; P-0097 MERGED_INTO P-0096; NEVER_REUSE','resolved'),
    ('來源備註／已完整保留','preserved'),('SOURCE_REPORTED_NULL','preserved'),
    ('PRESERVED_NOT_CORRECTED','review'),('待人工確認','review'),(None,'review'),('UNRECOGNIZED','review')])
def test_issue_status_not_assumed_open_or_closed(status,expected):
    assert issue_bucket(status)==expected

def test_all_issue_cells_and_original_status_preserved(archive,payload):
    before=archive.q('SELECT * FROM Data_Issues ORDER BY _row')
    report=payload['integrity']
    assert report['issueTotal']==366==len(report['issueRows'])
    for a,b in zip(before,report['issueRows']):
        assert b['row']==a['_row']
        assert b['values']=={k:value(v) for k,v in a.items() if k!='_row'}
    assert sum(r['count'] for r in report['issueBuckets'])==366
    assert all(r['count']>0 for r in report['issueBuckets'])
    assert sum(report['findingCounts'].values())==len(report['findings'])

def test_source_history_does_not_set_active_error_count(payload):
    g=payload['integrity']
    assert g['findingCounts']['handled']>0
    assert g['findingCounts']['review']>0
    assert g['findingCounts']['source_limit']>0
    assert next(r for r in g['issueRows'] if r['values']['Issue_ID']=='ISS-001')['bucket']=='resolved'

def test_unknown_snapshot_is_not_provisional():
    assert snapshot_state(['NOT_STATED_IN_SOURCE'])=='unknown'
    assert snapshot_state([None])=='unknown'
    assert snapshot_state(['NOT_FINAL'])=='unknown'
    assert snapshot_state(['FINAL_SOURCE_ADOPTED','NOT_STATED_IN_SOURCE'])=='mixed'
    assert snapshot_state(['FINAL_SOURCE_ADOPTED'])=='final'

def test_latest_final_precedes_newer_provisional():
    rows=[dict(final=True,snapshot='2035-06-02'),dict(final=False,snapshot='2035-06-09'),
          dict(final=True,snapshot='2035-06-06')]
    assert sorted(rows,key=snapshot_order,reverse=True)[0]['snapshot']=='2035-06-06'

def test_world_uses_latest_final_for_both_default_and_champion(archive,monkeypatch):
    original=archive.q
    def q(sql,*args):
        rows=original(sql,*args)
        if 'FROM Domestic_League_Standings' in sql and 'ORDER BY Competition_Raw' in sql:
            finals=[r for r in rows if r['Competition_Raw']=='LaLiga EA Sports' and r['Season']=='2034/35'
                    and (r['Season_Status'] or '').startswith('FINAL')]
            rows += [dict(r,Snapshot='2035-06-08') for r in finals]
        return rows
    monkeypatch.setattr(archive,'q',q)
    w=archive.world()
    key='LaLiga EA Sports|2034/35'
    assert w['snapshots'][key][0]['snapshot']=='2035-06-08'
    assert w['champions'][key]['snapshot']=='2035-06-08'

def test_confirmed_champion_joins_controlled_club_aliases(payload):
    c=payload['world']['champions']['LaLiga EA Sports|2023/24']
    assert c['confirmedElsewhere'] is True
    assert c['state']=='unknown'

def test_snapshot_report_distinguishes_multiplicity_from_provisional_final(payload):
    groups=payload['world']['snapshots']
    multiple=[v for v in groups.values() if len(v)>1]
    paired=[v for v in multiple if any(r['state']=='final' for r in v)
            and any(r['state']=='provisional' for r in v)]
    assert len(multiple)==16
    assert len(paired)==5

def test_ambiguous_club_never_picks_arbitrary_id(archive):
    r=ClubResolver(archive.con)
    assert r.resolve('南安普頓') is None
    assert r.resolve('南安普顿') is None
    exact={x['id'] for x in r.candidates('南安普頓') if x['score']==1.0}
    assert exact=={'C-0119','C-0195'}

def test_null_club_is_not_an_unregistered_team(payload):
    assert all(r['raw'].lower()!='null' for r in payload['clubs']['unresolved'])

def test_duplicate_club_reference_counts_not_multiplied_by_columns(archive,payload):
    for group in payload['clubs']['duplicates']:
        for member in group['members']:
            for t in member['tables']:
                assert t['n']==archive.one(f'SELECT COUNT(*) n FROM "{t["table"]}" WHERE Club_ID=?',member['id'])['n']

def test_unknown_transfer_direction_is_not_outbound(archive,monkeypatch):
    assert transfer_direction('LOAN') is None
    original=archive.q
    def q(sql,*args):
        rows=original(sql,*args)
        if sql=='SELECT * FROM Barcelona_Transfers':
            rows.append(dict(rows[0],Direction='UNKNOWN',_row=99999))
        return rows
    monkeypatch.setattr(archive,'q',q)
    seasons=archive.seasons()
    assert sum(len(s['transfersUnknown']) for s in seasons)==1
    assert all(t['row']!=99999 for s in seasons for t in s['transfersOut'])

def test_host_venue_split_is_lossless_and_cohost_not_a_country(payload):
    rows=[r for r in payload['world']['intl'] if r['venue']]
    assert len(rows)==5
    assert all(r['hostRaw']==r['host']+'；'+r['venue'] for r in rows)
    assert payload['meta']['nation_dimension_count']==49
    assert payload['meta']['nation_count']==47

def test_unique_alias_links_do_not_rewrite_award_ids(archive,payload):
    g=payload['integrity']
    assert len(g['aliasMatches'])==8
    assert {r['playerId'] for r in g['aliasMatches']}=={'P-0002','P-0308'}
    assert g['unresolvedAwards']==472
    assert sum(len(fs) for fs in payload['honours']['facts'].values())==1132
    for r in g['aliasMatches']:
        assert archive.one('SELECT Player_ID FROM Canonical_Award_Facts WHERE _row=?',r['row'])['Player_ID'] is None

def test_no_master_statistic_backfilled_or_overwritten(archive,payload):
    season=next(s for s in payload['seasons'] if s['season']=='2034/35')
    assert season['gf'] is None and season['ga'] is None
    before=archive.one('SELECT LaLiga_GF,LaLiga_GA FROM Barcelona_Season_Master WHERE Season=?','2034/35')
    assert before=={'LaLiga_GF':None,'LaLiga_GA':None}

def test_declared_actions_have_real_routes(payload):
    valid={'world','leagues','squad','seasons','clubs','comps','resolve','tournaments','reference'}
    assert all(f['view'] in valid for f in payload['integrity']['findings'])
