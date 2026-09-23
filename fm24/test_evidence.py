"""P0 contracts against the workbook and adversarial, small link fixtures."""
from collections import Counter
from pathlib import Path
import json

import pytest

from build_site import Archive, build, collect, export_json
from evidence import Periods, link_awards

DB = Path(__file__).parent / 'data/fm24.sqlite'


@pytest.fixture(scope='module')
def archive():
    if not DB.exists():
        pytest.skip('run etl.py first')
    a = Archive(DB)
    yield a
    a.con.close()


@pytest.fixture(scope='module')
def payload(archive):
    return collect(archive)


def fact(**kw):
    return dict(dict(_row=2, Award='Boot', Season='2034/35', Player_ID='P-1', Player_Raw='A',
        Rank='1', Club_Raw='Club', Source_ID='S1', Origin_Sheet='Awards', Origin_Row='2',
        Verification_Status='verified'), **kw)


def link(**kw):
    return dict(dict(_row=2, Fact_Key='Boot|2034/35|P-1|1', Origin_Sheet='Awards', Origin_Row='2',
        Source_ID='S1', Link_Role='detail', Verification_Status='verified'), **kw)


def test_multiple_sources_do_not_add_awards():
    facts, unmatched = link_awards([fact()], [link(), link(_row=3, Source_ID='S2')])
    assert len(facts) == 1 and len(facts[0]['evidence']) == 2 and not unmatched


def test_raw_key_format():
    fs, unmatched = link_awards([fact()], [link(Fact_Key='2034/35|Boot|1|A|S1')])
    assert fs[0]['evidence'][0]['match'] == 'Fact_Key' and not unmatched


def test_exact_locator_preserves_historical_key():
    fs, unmatched = link_awards([fact()], [link(Fact_Key='legacy')])
    assert fs[0]['factKeys'] == ['legacy'] and not unmatched
    assert fs[0]['evidence'][0]['match'] == 'exact_source_locator'


def test_ambiguous_locator_is_not_guessed():
    fs, unmatched = link_awards([fact()], [link(Fact_Key='legacy1'),link(_row=3,Fact_Key='legacy2')])
    assert not fs[0]['evidence'] and len(unmatched) == 2


def test_shared_key_is_not_attached_twice():
    fs, unmatched = link_awards([fact(), fact(_row=3)], [link()])
    assert all(not f['evidence'] for f in fs) and len(unmatched) == 1


def test_unrelated_same_row_number_does_not_link():
    fs, unmatched = link_awards([fact()], [link(Fact_Key='legacy',Source_ID='another')])
    assert not fs[0]['evidence'] and len(unmatched) == 1


def test_period_aliases_do_not_duplicate_logical_periods(archive, payload):
    periods=Periods(archive.q('SELECT * FROM Period_Dim'))
    assert periods.resolve('2034/35') == periods.resolve('2034-2035') == 'PER-S-2034-35'
    assert periods.resolve('2034') != periods.resolve('2034/35')
    assert periods.resolve('unrecorded') is None
    records=payload['sources']['periods']
    assert len(records) == len({p['id'] for p in records}) == 54


def test_all_award_facts_and_all_evidence_preserved(archive,payload):
    fs=[f for group in payload['honours']['facts'].values() for f in group]
    assert len(fs) == len({f['key'] for f in fs}) == 1132
    actual=[e['linkRow'] for f in fs for e in f['evidence']]
    actual += [e['linkRow'] for e in payload['sources']['unlinkedAwardEvidence']]
    assert Counter(actual) == Counter(r['_row'] for r in archive.q('SELECT * FROM Award_Fact_Source_Links'))
    assert len(payload['honours']['index']) == 45
    assert len([f for f in fs if not f['evidence']]) == 33  # Golden Shoe has primary sources, no link rows.


def test_selection_order_never_becomes_rank_one(payload):
    fs=payload['honours']['facts']['LaLiga EA Sports Equipo de la temporada']
    assert len(fs) == 276 and all(f['kind']=='selection' for f in fs)
    assert not payload['honours']['winners']['LaLiga EA Sports Equipo de la temporada']


def test_every_season_provenance_row_reaches_its_season(archive,payload):
    rows=[r for s in payload['seasons'] for r in s['provenance']]
    assert Counter(r['row'] for r in rows) == Counter(r['_row'] for r in archive.q('SELECT * FROM Season_Master_Field_Provenance'))
    assert any(r['date']=='來源未提供日期' for r in rows)
    assert len({r['date'] for r in rows}) > 1


def test_transfer_totals_are_source_strings(archive,payload):
    actual={r['evidence']['row']:r['total'] for s in payload['seasons'] for r in s['transferTotals']}
    assert actual == {r['_row']:r['Displayed_Total'] for r in archive.q('SELECT * FROM Barcelona_Transfer_Totals')}
    assert len(actual)==24


def test_all_stats_rows_are_visible_without_double_counting(archive,payload):
    actual=[r for p in payload['people']['players'] for r in p['seasonVerification']]
    assert len(actual)==178
    assert len(payload['sources']['seasonStatsNotes'])==1
    assert all(r['comparison']=='consistent' for r in actual)
    assert not payload['sources']['unassignedEvidence']
    baseline={p['id']:p for p in archive.players()}
    for p in payload['players']:
        for key in ['apps','goals','assists','titles','seasonStats']:
            assert p[key] == baseline[p['id']][key]


def test_honours_preserve_policy_and_zero_appearance_members(payload):
    hs=[r for p in payload['people']['players'] for r in p['seasonHonours']]
    assert len(hs)==178 and all(r['policy']=='A1' for r in hs)
    assert any(r['apps']=='0' and r['titles']['西甲']==1 for r in hs)
    assert all('世俱盃' not in r['titles'] for r in hs)


def test_missing_stat_is_not_zero(payload):
    p=next(p for p in payload['people']['players'] if p['id']=='P-0256')
    assert p['seasonVerification'][-1]['fields']['Apps']=='0'
    assert p['seasonVerification'][-1]['fields']['Goals'] is None


@pytest.mark.parametrize('failure',['different','no_unique_adopted'])
def test_conflicting_evidence_is_visible_and_never_overwrites(archive,payload,failure):
    from copy import deepcopy
    from evidence import integrate
    class Changed:
        def q(self,sql):
            rows=archive.q(sql)
            if failure=='different' and 'FROM Barcelona_Player_Season_Stats' in sql:
                for r in rows:
                    if r['Player_ID']=='P-0061':
                        r['Goals']='999'
            if failure=='no_unique_adopted' and "Statistical_Adoption_Status='ADOPTED'" in sql:
                rows += [dict(r) for r in rows if r['Player_ID']=='P-0061']
            return rows
    result=integrate(Changed(),deepcopy(payload))
    p=next(p for p in result['players'] if p['id']=='P-0061')
    before=next(p for p in payload['players'] if p['id']=='P-0061')
    assert all(r['comparison']==failure for r in p['seasonVerification'])
    assert p['goals']==before['goals'] and p['seasonStats']==before['seasonStats']
    if failure=='different':
        assert all(any(d['worksheet']=='999' for d in r['differences']) for r in p['seasonVerification'])


def test_local_paths_not_exported(archive,payload):
    text=json.dumps(payload,ensure_ascii=False)
    assert 'Local_Path' not in text
    for row in archive.q('SELECT Local_Path FROM Source_Index'):
        path=row['Local_Path']
        if path and len(path)>10:
            assert path not in text


@pytest.mark.parametrize('entry',['archive','build','json','coverage','audit'])
def test_programmatic_entrypoints_refuse_missing_opencc(monkeypatch,tmp_path,entry):
    import resolver
    monkeypatch.setattr(resolver,'SCRIPT_CONVERSION_AVAILABLE',False)
    with pytest.raises(resolver.ScriptConversionUnavailable):
        if entry=='archive': Archive(DB)
        elif entry=='build': build(DB,tmp_path/'x.html',Path(__file__).parent/'template.html')
        elif entry=='json': export_json(DB,tmp_path/'x.json')
        elif entry=='coverage':
            from coverage import scan
            scan(DB)
        else:
            from audit_brief import generate
            generate(DB)
    assert not list(tmp_path.iterdir())


def test_explicit_degraded_export_is_marked(monkeypatch,tmp_path):
    import resolver
    monkeypatch.setattr(resolver,'SCRIPT_CONVERSION_AVAILABLE',False)
    monkeypatch.setattr(resolver,'_convert',lambda s:s)
    path=tmp_path/'data.json'
    export_json(DB,path,allow_degraded=True)
    p=json.loads(path.read_text(encoding='utf-8'))
    assert p['meta']['degraded'] and p['meta']['buildWarnings']
    assert p['meta']['scriptConversion'] is False


def test_embedded_data_cannot_close_script(monkeypatch,tmp_path):
    import build_site
    monkeypatch.setattr(build_site,'collect',lambda a:{'sample':'</script><script>alert(1)</script>'})
    out=tmp_path/'page.html'
    build(DB,out,Path(__file__).parent/'template.html',standalone=True)
    html=out.read_text(encoding='utf-8')
    assert '\\u003c/script>' in html and '</script><script>alert' not in html
