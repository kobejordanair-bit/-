"""Provenance for newly adopted screenshot records; legacy IDs stay stable."""
import hashlib
import json

FIELDS = {'Source_Instance_ID', 'Source_Row_Ordinal', 'Source_Row_ID',
          'Observation_ID', 'Fact_ID', 'Statistical_Adoption_Status', 'Adoption_Note'}
TABLES = {'Player_League_Career', 'Player_Club_Competition_Stats', 'Player_Club_Season_Totals'}


def stamp(payload, sheet, key, text_sha, ordinal, columns):
    if sheet not in TABLES:
        return
    if not FIELDS <= set(columns):
        raise ValueError('SCREENSHOT_REQUIRES_OBSERVATION_FACT_SCHEMA:' + sheet)
    def identity(prefix, value):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:24]
    observation = identity('OBS-', [text_sha, sheet, ordinal, key])
    payload.update(Source_Instance_ID='TXT-' + text_sha, Source_Row_Ordinal=ordinal,
                   Source_Row_ID=observation, Observation_ID=observation,
                   Fact_ID=identity('FACT-', [sheet, key]), Statistical_Adoption_Status='ADOPTED',
                   Adoption_Note='FM_SCREENSHOT_V1: ordinal is the record order in the retained transcription, '
                                 'not an original screenshot row. Updates retain the previous fact ID; '
                                 'Import_Observations and the previous workbook retain earlier values.')


def selected_metadata(old, incoming, selected):
    if selected.get('Source_ID') != old.get('Source_ID') and incoming.get('Source_Instance_ID'):
        for key in FIELDS:
            selected[key] = incoming[key]
        if old.get('Fact_ID'):
            selected['Fact_ID'] = old['Fact_ID']


def adopted(row, columns):
    return ('Statistical_Adoption_Status' not in columns or
            row[columns['Statistical_Adoption_Status'] - 1] == 'ADOPTED')
