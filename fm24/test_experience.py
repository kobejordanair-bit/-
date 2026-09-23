"""Interactive views must preserve source scope and missingness."""
import json
from pathlib import Path
import pytest
from build_site import Archive
from experience import metric, integrate_experience

@pytest.mark.parametrize('raw,expected',[(None,None),('',None),('NULL',None),('nan',None),('inf',None),('0',0),('7.25',7.25)])
def test_numeric_missingness(raw,expected):
    assert metric(raw)==expected

@pytest.fixture(scope='module')
def archive():
    a=Archive(Path(__file__).parent/'data/fm24.sqlite')
    yield a
    a.con.close()

@pytest.fixture(scope='module')
def data(archive): return integrate_experience(archive,{})['experience']

def test_all_season_metrics_match_master(archive,data):
    rows=archive.q('SELECT * FROM Barcelona_Season_Master')
    assert len(rows)==len(data['seasons'])==12
    for r in rows:
        actual=data['seasons'][r['Season_ID']]
        for k,col in {'points':'LaLiga_Points','w':'LaLiga_W','d':'LaLiga_D','l':'LaLiga_L','gf':'LaLiga_GF','ga':'LaLiga_GA','trophies':'Total_Trophies'}.items():
            assert actual[k]==metric(r[col])
        assert actual['source']['row']==r['_row']
    assert data['seasons']['PER-S-2034-35']['gf'] is None

def test_career_totals_not_recomputed_from_seasons(archive,data):
    rows=archive.q('SELECT * FROM Barcelona_Player_Career')
    assert len(rows)==len(data['players'])==30
    for r in rows:
        p=data['players'][r['Player_ID']]
        for k,col in {'apps':'Apps','goals':'Goals','assists':'Assists','motm':'MOTM','rating':'Avg_Rating','cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}.items():
            assert p[k]==metric(r[col])
        assert p['source']['row']==r['_row']

def test_only_adopted_barcelona_rows_and_all_cells_preserved(archive,data):
    rows=archive.q("SELECT * FROM Player_Club_Season_Totals WHERE Club_ID='C-0030' AND Statistical_Adoption_Status='ADOPTED'")
    expected=[r for r in rows if r['Player_ID'] in data['players']]
    assert sum(len(p['seasons']) for p in data['players'].values())==len(expected)
    for r in expected:
        actual=next(x for x in data['players'][r['Player_ID']]['seasons'] if x['source']['row']==r['_row'])
        for k,col in {'apps':'Apps','goals':'Goals','assists':'Assists','motm':'POTM','rating':'Rating'}.items():
            assert actual[k]==metric(r[col])
        assert actual['source']['source']==r['Source_ID']

def test_unknown_match_count_is_not_zero(archive,monkeypatch):
    original=archive.q
    def query(sql,*args):
        rows=original(sql,*args)
        if 'FROM Barcelona_Season_Master' in sql:
            rows=[dict(r) for r in rows]
            rows[0]['LaLiga_W']=None
        return rows
    monkeypatch.setattr(archive,'q',query)
    values=integrate_experience(archive,{})['experience']['seasons']
    assert next(iter(values.values()))['played'] is None

def test_metrics_json_is_finite(data):
    json.dumps(data,allow_nan=False)

def test_clasico_suffix_deciders_preserved(archive):
    matches=archive.clasico()
    extra=next(m for m in matches if m['result']=='2-6 加')
    assert extra['score']=='2-6' and extra['decider']=='aet'
    penalty=next(m for m in matches if m['result']=='0-0 点')
    assert penalty['score']=='0-0' and penalty['decider']=='pens' and penalty['verdict']=='D'
    assert all(m['source']['row'] for m in matches)
