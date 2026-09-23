"""Deterministic Record_Identity_Map refresh on a workbook copy."""
from __future__ import annotations
from pathlib import Path
from openpyxl import load_workbook
from generic_importer import headers, dictrow, refresh, ImportFailure

AUTHORITY=('Player_League_Career','Player_Club_Competition_Stats','Player_Club_Season_Totals')

def _names(wb, sheet, ident):
    ws=wb[sheet]; h=headers(ws)
    idcol='Player_ID' if sheet=='Player_Dim' else 'Club_ID'
    for r in ws.iter_rows(min_row=2,values_only=True):
        if str(r[h[idcol]-1])==ident: return str(r[h['Canonical_Display_Name']-1])
    raise ImportFailure(f'IDENTITY_DIM_MISSING:{ident}')

def refresh_identity_map(path: Path, *, reconcile_row_provenance: bool=False) -> dict:
    wb=load_workbook(path,data_only=False); m=wb['Record_Identity_Map']; mh=headers(m)
    names = {sheet: {str(r[headers(wb[sheet])[field]-1]): str(r[headers(wb[sheet])['Canonical_Display_Name']-1]) for r in wb[sheet].iter_rows(min_row=2, values_only=True)} for sheet,field in [('Player_Dim','Player_ID'),('Club_Dim','Club_ID')]}
    existing={}
    for r in m.iter_rows(min_row=2,values_only=True):
        key=(str(r[mh['Origin_Sheet']-1]),r[mh['Origin_Row']-1],str(r[mh['Entity_Role']-1]))
        existing[key]=r
    added=conflicts=noops=0; missing_before={}; missing_after={}; expected_rows=[]
    for sn in AUTHORITY:
        ws=wb[sn]; h=headers(ws); miss=0
        for n,r in enumerate(ws.iter_rows(min_row=2,values_only=True),2):
            for role,idfield,rawfield in [('Player','Player_ID',None),('Club','Club_ID','Club_Raw')]:
                key=(sn,n,role); ident=str(r[h[idfield]-1]); raw=(str(r[h[rawfield]-1]) if rawfield else names['Player_Dim'][ident])
                canonical=names['Player_Dim' if role=='Player' else 'Club_Dim'][ident]
                expected={'Origin_Sheet':sn,'Origin_Row':n,'Origin_Record_Key':f'{sn}|{n}|{role}',
                  'Period_ID':r[h['Season_ID']-1],'Entity_Role':role,'Raw_Display_Name':raw,'Entity_ID':ident,
                  'Canonical_Display_Name':canonical,'Verification_Status':r[h['Verification_Status']-1]}
                expected_rows.append(expected)
                old=existing.get(key)
                if old is None:
                    miss+=1; m.append(dictrow(m,expected)); added+=1
                else:
                    # Raw display variants are historical evidence, not an identity conflict.
                    # Existing rows are correct when their stable identity and provenance key agree.
                    stable=('Origin_Sheet','Origin_Row','Origin_Record_Key','Period_ID','Entity_Role','Entity_ID')
                    if all(old[mh[k]-1] == expected[k] for k in stable):
                        noops+=1
                        if old[mh['Verification_Status']-1] != expected['Verification_Status']:
                            for rn in range(2,m.max_row+1):
                                if (str(m.cell(rn,mh['Origin_Sheet']).value),m.cell(rn,mh['Origin_Row']).value,str(m.cell(rn,mh['Entity_Role']).value))==key:
                                    m.cell(rn,mh['Verification_Status']).value=expected['Verification_Status'];break
                    else: conflicts+=1
        missing_before[sn]=miss
    if conflicts and reconcile_row_provenance:
        # Canonical re-sorting after a valid import changes Origin_Row.  The map is
        # derived from authority rows, so rebuild only its authority-derived rows.
        retained=[r for r in m.iter_rows(min_row=2,values_only=True)
                  if str(r[mh['Origin_Sheet']-1]) not in AUTHORITY]
        if m.max_row>1: m.delete_rows(2,m.max_row-1)
        for row in retained: m.append(row)
        for expected in expected_rows: m.append(dictrow(m,expected))
        added=len(expected_rows); noops=0
        conflicts=0
    if conflicts: raise ImportFailure(f'IDENTITY_MAP_CONFLICT:{conflicts}')
    refresh(m); wb.save(path)
    # By construction every original missing (two roles / authority row) has been appended.
    missing_after={sn:0 for sn in AUTHORITY}
    return {'before_missing_rows':missing_before,'added_map_entries':added,'after_missing_rows':missing_after,
            'conflict_count':conflicts,'no_op_entries':noops,'row_provenance_reconciled':reconcile_row_provenance}
