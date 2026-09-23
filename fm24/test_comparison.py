from pathlib import Path
import pytest
from build_site import Archive, collect
from comparison import integrate_comparison
from experience import metric

@pytest.fixture(scope='module')
def data():
    a=Archive(Path(__file__).parent/'data/fm24.sqlite')
    yield a,collect(a)
    a.con.close()

def test_all_world_identities_are_selectable(data):
    _,d=data
    assert set(d['comparison']['players'])=={p['id'] for p in d['people']['players']}

def test_league_rows_are_only_adopted_and_preserve_every_source_value(data):
    a,d=data
    raw=a.q("SELECT * FROM Player_League_Career WHERE Statistical_Adoption_Status='ADOPTED'")
    actual={r['source']['row']:r for p in d['comparison']['players'].values() for r in p['league']}
    assert len(actual)==len(raw)==532
    for r in raw:
        out=actual[r['_row']]
        for k,col in {'apps':'Apps','goals':'Goals','assists':'Assists','motm':'POTM','rating':'Rating','cleanSheets':'Clean_Sheets','goalsConceded':'Goals_Conceded'}.items():
            assert out[k]==metric(r.get(col))
        assert out['fact']==r['Fact_ID'] and out['clubId']==r['Club_ID']

def test_missing_values_do_not_become_zero(data):
    a,d=data
    class Missing:
        def q(self,sql):
            rows=a.q(sql)
            if 'FROM Player_League_Career' in sql:rows=[dict(r,Assists=None,Goals='0') for r in rows]
            return rows
    from copy import deepcopy
    out=integrate_comparison(Missing(),deepcopy(d))
    rows=[r for p in out['comparison']['players'].values() for r in p['league']]
    assert rows and all(r['assists'] is None and r['goals']==0 for r in rows)

def test_attribute_snapshots_have_real_cells_and_source_rows(data):
    a,d=data
    raw={sheet:{r['_row']:r for r in a.q(f'SELECT * FROM {sheet}')} for sheet in ['Player_Attr_Snap_O','Player_Attr_Snap_G']}
    snapshots=[s for p in d['comparison']['players'].values() for s in p['snapshots']]
    assert len(snapshots)==sum(len(rows) for rows in raw.values())
    for s in snapshots:
        r=raw[s['evidence']['sheet']][s['evidence']['row']]
        cells={k.replace('_',' '):metric(v) for k,v in r.items()}
        for pairs in s['groups'].values():
            for k,v in pairs:assert v==cells[k] and 1<=v<=20
        assert s['date']==r['Snapshot_Date']

def test_new_comparison_does_not_change_accepted_honours(data):
    a,d=data
    from copy import deepcopy
    before=deepcopy(d)
    integrate_comparison(a,d)
    for key in ['people','players','honours','experience','honourReview']:
        assert d[key]==before[key]

def test_profile_rows_preserve_dates_and_identity(data):
    a,d=data
    raw={r['_row']:r for r in a.q('SELECT * FROM Player_Profile_Snapshots')}
    for pid,p in d['comparison']['players'].items():
        for profile in p['profiles']:
            r=raw[profile['source']['row']]
            assert pid==r['Player_ID'] and profile['date']==r['Snapshot_Date']
