"""Regression checks against Master authorities, including stale row locators."""
from collections import Counter
from pathlib import Path
import re
import pytest
from build_site import Archive, collect
from player_awards import AWARD_SHEETS, ALIASES, signature


@pytest.fixture(scope='module')
def archive():
    a = Archive(Path(__file__).parent / 'data/fm24.sqlite')
    yield a
    a.con.close()


@pytest.fixture(scope='module')
def payload(archive):
    return collect(archive)


def test_yamal_all_37_honours_plus_17_placings(payload):
    p = next(p for p in payload['people']['players'] if p['id'] == 'P-0060')
    assert p['awardCounts'] == dict(winner=21, selection=16, placing=17)
    assert len(p['awards']) == 54
    assert {f['season'] for f in p['awards'] if f['award'] == 'Fan Player of Season'} == {'2026/27','2027/28','2031/32'}
    assert sum(f['award'] == 'Kopa Trophy' and f['kind'] == 'winner' for f in p['awards']) == 4
    assert sum(f['award'] == 'FIFPro World XI' for f in p['awards']) == 5


def test_every_career_summary_honour_has_a_structured_source(payload):
    # Narratives are an independent oracle here, never production fact input.
    def award_name(s):
        return ALIASES.get(s, s).replace('’', "'")
    for p in payload['people']['players']:
        if not p['awardSummary']:
            continue
        for text in p['awardSummary']['text'].split('；'):
            match = re.fullmatch(r'(\S+) (.+)（(冠軍|獲獎|入選)）', text)
            if not match:
                assert text == '無已確認重大個人獎項（限已確認 Award／Leader sheets）'
                continue
            season, award, result = match.groups()
            kind = 'selection' if result == '入選' else 'winner'
            assert any(f['periodDisplay'] == season and award_name(f['award']) == award_name(award)
                       and f['kind'] == kind for f in p['awards']), (p['name'], text)


def test_canonical_statistics_are_unchanged(archive, payload):
    facts = [f for fs in payload['honours']['facts'].values() for f in fs]
    assert len(facts) == len(archive.q('SELECT * FROM Canonical_Award_Facts')) == 1132
    assert len({f['key'] for f in facts}) == 1132
    assert sum(not f['id'] for f in facts) == 472


def test_all_ledger_entries_unique_and_explained(payload):
    facts = [f for p in payload['people']['players'] for f in p['awards']]
    assert len(facts) == len({signature(f) for f in facts}) == payload['people']['awardCoverage']['records']
    assert all(f['primary']['sheet'] and f['primary']['row'] for f in facts)
    assert all(f['primary']['sheet'] != 'Barcelona_Player_Career' for f in facts)
    assert not any('Mánager' in f['award'] for f in facts)
    for f in facts:
        if f['primary']['sheet'] == 'Barcelona_Season_Leaders':
            assert f['award'] == 'Fan Player of Season'


def test_sources_are_preserved_and_every_row_accounted_for(archive, payload):
    for sheet in AWARD_SHEETS:
        rows = archive.q(f'SELECT * FROM "{sheet}"')
        report = payload['people']['awardCoverage']['sheets'][sheet]
        assert report['rows'] == len(rows) == sum(v for k,v in report.items() if k != 'rows')
        assert len(payload['reference']['tables'][sheet]['rows']) == len(rows)


def test_stale_map_never_assigns_wrong_fan_award(archive, payload):
    expected = {(r['Season'], r['Player']) for r in archive.q("SELECT * FROM Barcelona_Season_Leaders WHERE Metric='年度球迷票選最佳球員'")}
    actual = {(f['season'], p['name']) for p in payload['people']['players'] for f in p['awards'] if f['award'] == 'Fan Player of Season'}
    assert actual == expected
    assert payload['people']['awardCoverage']['identityIssues']


def test_duplicate_selection_sources_do_not_become_multiple_honours(payload):
    p = next(p for p in payload['people']['players'] if p['id'] == 'P-0060')
    records = [f for f in p['awards'] if f['award'] == 'LaLiga EA Sports Equipo de la temporada']
    assert len(records) == 11
    f = next(f for f in records if f['season'] == '2024/25')
    assert f['kind'] == 'selection'
    assert 'Barcelona_LaLiga_Best_XI' in {r['sheet'] for r in [f['primary'], *f['evidence']]}


def test_calendar_year_is_not_merged_into_season():
    f = dict(id='P', award='award', kind='winner', rank='1', season='2034', periodId='PER-Y-2034')
    assert signature(f) != signature(dict(f, season='2034/35', periodId='PER-S-2034-35'))


def test_registry_counts_recomputed(payload):
    assert payload['people']['withAwards'] == sum(bool(p['awards']) for p in payload['people']['players'])
    for p in payload['people']['players']:
        assert sum(p['awardCounts'].values()) == len(p['awards'])
