from pathlib import Path
import pytest
from build_site import Archive, collect
from honour_review import integrate_honour_review

@pytest.fixture(scope='module')
def data():
    a=Archive(Path(__file__).parent/'data/fm24.sqlite')
    d=collect(a)
    yield a,d
    a.con.close()

def test_all_unbound_player_facts_accounted_once(data):
    _,d=data
    expected={f['key'] for fs in d['honours']['catalogueFacts'].values() for f in fs if not f['resolved'] and f['actorKind']!='coach'}
    actual=[f['key'] for r in d['honourReview']['items'] if r['kind']=='player' for f in r['facts']]
    assert len(actual)==len(set(actual))==471
    assert set(actual)==expected

def test_proposals_have_actual_unique_dimension_evidence(data):
    a,d=data
    from resolver import normalise
    rows=a.q('SELECT * FROM Player_Dim')
    proposals=[r for r in d['honourReview']['items'] if r.get('proposal')]
    assert proposals
    for r in proposals:
        ids={x['Player_ID'] for x in rows if normalise(r['title']) in {normalise(x['Canonical_Display_Name']),normalise(x['Alias_Name'])}}
        assert ids=={r['proposal']['playerId']}
        assert r['proposal']['mode']=='REVIEW_ONLY_NOT_ADOPTED'
        assert all(not f['resolved'] for f in r['facts'])
        assert r['candidates'][0]['evidence']

def test_ambiguous_same_name_never_yields_unique_proposal(data):
    a,d=data
    from copy import deepcopy
    class Ambiguous:
        def q(self,sql):
            rows=a.q(sql)
            if 'FROM Player_Dim' in sql:
                rows.append(dict(rows[0],Player_ID='P-0060',Alias_Name='Kim Min-Jae',Canonical_Display_Name='Different',_row=9999))
            return rows
    result=integrate_honour_review(Ambiguous(),deepcopy(d))
    case=next(r for r in result['honourReview']['items'] if r['title']=='Kim Min-Jae')
    assert case['proposal'] is None and len(case['candidates'])==2

def test_priorities_and_source_conflicts_are_evidence_backed(data):
    _,d=data
    rows=d['honourReview']['items']
    assert [r['priority'] for r in rows]==sorted(r['priority'] for r in rows)
    assert sum(d['honourReview']['priorities'].values())==len(rows)
    for r in rows:
        if r['priority']=='P0':
            assert r['kind'] in ('club','tournament') and r['evidence']
        if r['kind']=='player' and r['counts']['winner']:
            assert r['priority']=='P1'
    assert len([r for r in rows if r['kind']=='tournament'])==2

def test_no_accepted_statistics_changed_by_review(data):
    a,d=data
    from copy import deepcopy
    before=deepcopy(d)
    integrate_honour_review(a,d)
    for k in ['people','players','honours','integrity','world']:
        assert d[k]==before[k]
    assert d['people']['awardCoverage']['records']==1151
    assert d['honours']['catalogueCount']==1636

def test_mapping_cases_preserve_current_and_old_rows(data):
    a,d=data
    raw=a.q('SELECT * FROM Record_Identity_Map')
    byrow={str(r['_row']):r for r in raw}
    cases=[r for r in d['honourReview']['items'] if r['kind']=='mapping']
    assert cases
    for r in cases:
        assert len(r['details'])==r['count']
        for detail in r['details']:
            for old in detail['old']:
                assert byrow[str(old['evidence']['row'])]['Entity_ID']==old['id']

def test_notes_fingerprint_changes_with_affected_evidence(data):
    a,d=data
    from copy import deepcopy
    assert all(len(r['fingerprint'])==16 for r in d['honourReview']['items'])
    assert len({r['id'] for r in d['honourReview']['items']})==len(d['honourReview']['items'])
    assert all(r['count']>=0 for r in d['honourReview']['items'])
    changed=deepcopy(d)
    changed['clubs']['duplicates'][0]['members'][0]['rows']+=1
    integrate_honour_review(a,changed)
    before={r['id']:r['fingerprint'] for r in d['honourReview']['items']}
    after={r['id']:r['fingerprint'] for r in changed['honourReview']['items']}
    assert sum(before[k]!=after[k] for k in before)==1
