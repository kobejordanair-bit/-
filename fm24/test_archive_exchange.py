"""Failure isolation and exact-byte interchange, not statistical reimplementations."""
import base64
import io
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile
from contextlib import closing

import pytest
import etl
from archive_exchange import digest, dumps, extract, make_exchange, render_html, runtime, validate_workbook, verify_mirror

ROOT = Path(__file__).parent
MASTER = next((ROOT.parents[1] / 'sources').glob('*.xlsx'), None)


@pytest.fixture(scope='module')
def packet():
    if MASTER is None:
        pytest.skip('read-only Master not present')
    payload = json.loads((ROOT / 'dist/fm24-data.json').read_text(encoding='utf-8'))
    payload.pop('_readme', None)
    return make_exchange(MASTER, ROOT / 'data/fm24.sqlite', payload, runtime()['engine'])


def test_html_exchange_roundtrip_keeps_entire_workbook(packet):
    page = render_html(packet, runtime())
    parsed, raw = extract(page)
    assert raw == MASTER.read_bytes()
    assert parsed['payloadJSON'] == packet['payloadJSON']
    assert parsed['manifest']['rows'] == 27124
    assert len(parsed['manifest']['sheets']) == 122
    assert 'html=html.replace(\'"__ARCHIVE_DATA__"\'' in page


@pytest.mark.parametrize('field', ['workbookSha256', 'payloadSha256'])
def test_corrupt_exchange_rejected(packet, field):
    bad = dict(packet, **{field: '0' * 64})
    with pytest.raises(ValueError, match='雜湊'):
        extract(dumps(bad))


def test_html_never_executes_script(packet, tmp_path):
    sentinel = tmp_path / 'should-not-exist'
    html = render_html(packet, runtime()) + f'<script>writeFile({str(sentinel)!r},"bad")</script>'
    extract(html)
    assert not sentinel.exists()


def test_wrong_json_format_rejected():
    with pytest.raises(ValueError, match='交換包'):
        extract('{"schema":"FM24_IMPORT_BATCH_V1","batches":[]}')


def test_legacy_html_cannot_invent_original_workbook():
    with pytest.raises(ValueError, match='未保存原始 Excel'):
        extract('<script>const DATA = {"meta":{}};</script>')


def test_database_survives_mid_import_failure(tmp_path, monkeypatch):
    if MASTER is None: pytest.skip('Master not present')
    db = tmp_path / 'archive.sqlite'
    shutil.copyfile(ROOT / 'data/fm24.sqlite', db)
    before = db.read_bytes()
    calls = 0
    normalise = etl.normalise
    def fail_after_rows(value):
        nonlocal calls
        calls += 1
        if calls > 80: raise ValueError('simulated truncated workbook')
        return normalise(value)
    monkeypatch.setattr(etl, 'normalise', fail_after_rows)
    with pytest.raises(ValueError, match='simulated'):
        etl.load(MASTER, db)
    assert db.read_bytes() == before
    assert not list(tmp_path.glob('.fm24-*'))


def test_pending_observations_survive_successful_rebuild(tmp_path):
    if MASTER is None: pytest.skip('Master not present')
    db = tmp_path / 'archive.sqlite'
    with closing(sqlite3.connect(db)) as con:
        con.execute('CREATE TABLE Ingest_TEST (Observation_ID TEXT, Payload_JSON TEXT)')
        con.execute('INSERT INTO Ingest_TEST VALUES (?,?)', ('pending-1', '{"Goals":null}'))
        con.commit()
    etl.load(MASTER, db)
    with closing(sqlite3.connect(db)) as con:
        assert con.execute('SELECT * FROM Ingest_TEST').fetchall() == [('pending-1', '{"Goals":null}')]
        assert con.execute('SELECT SUM(row_count) FROM _sheets').fetchone()[0] == 27124


def test_corrupt_existing_database_not_silently_discarded(tmp_path):
    if MASTER is None: pytest.skip('Master not present')
    db = tmp_path / 'archive.sqlite'
    db.write_bytes(b'corrupt but possibly recoverable')
    with pytest.raises(sqlite3.Error):
        etl.load(MASTER, db)
    assert db.read_bytes() == b'corrupt but possibly recoverable'


@pytest.mark.parametrize('xml', [
    '<c r="A1"><f>SUM(A2:A3)</f></c>',
    '<c r="A1"><f>SUM(A2:A3)</f><v/></c>',
    '<c r="A1" t="e"><v>#REF!</v></c>',
])
def test_formula_without_cached_value_or_error_refused(xml):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook/>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>'+xml+'</row></sheetData></worksheet>')
    with pytest.raises(ValueError, match='公式或錯誤'):
        validate_workbook(stream.getvalue())


def test_original_workbook_validates(packet):
    validate_workbook(base64.b64decode(packet['workbook']))


def test_manifest_retains_duplicate_rows_and_all_headers(packet):
    sheets = packet['manifest']['sheets']
    assert sum(len(s['rowHashes']) for s in sheets) == 27124
    assert all(s['columns'] and s['sha256'] for s in sheets)


def test_cannot_attach_different_workbook_to_database(tmp_path):
    if MASTER is None: pytest.skip('Master not present')
    db = tmp_path / 'archive.sqlite'
    shutil.copyfile(ROOT / 'data/fm24.sqlite', db)
    with closing(sqlite3.connect(db)) as con:
        con.execute('DELETE FROM Ballon_dOr WHERE _row = (SELECT MIN(_row) FROM Ballon_dOr)')
        con.commit()
        with pytest.raises(ValueError, match='不是同一版'):
            verify_mirror(MASTER, con)
