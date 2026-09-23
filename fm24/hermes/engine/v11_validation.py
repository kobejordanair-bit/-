"""Validator-owned Full Player Import V1.1 contract and populated-candidate gate."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import re
import zipfile
from openpyxl import load_workbook
from generic_importer import headers, validate as generic_validate
from derived_rebuild import formula_errors
from full_player_import_v11_attributes import HEADER, OUTFIELD, GOALKEEPER
from import_policy import LEDGER, LEDGER_HEADER, dump, period_fields
from semantic_guard import DERIVED_FIELDS, observations, derived_cell_guard, recompute_guard

NEW_SHEETS = {
    "Player_Attr_Snap_O": tuple(HEADER) + tuple(OUTFIELD),
    "Player_Attr_Snap_G": tuple(HEADER) + tuple(GOALKEEPER),
    "Player_Attribute_Changes": ("Player_ID", "From_Snapshot", "To_Snapshot", "Attribute_Name", "Old_Value", "New_Value", "Delta"),
}
CONTROLLED_ALIAS=('N-0027','英格兰','英格蘭')
# Only these pre-existing sheets may receive V1.1 import rows.  Existing cells may
# never be rewritten; appended rows are validated semantically below.
MUTABLE_SHEETS = {
    "Player_Dim", "Player_Profile_Snapshots", "Player_League_Career",
    "Player_Career_Summaries", "Player_Club_Competition_Stats",
    "Player_Club_Season_Totals", "Player_National_Team_Stats", "Source_Index",
    "Record_Identity_Map", "Barcelona_Player_Season_Stats", "Barcelona_Player_Career",
    "Barcelona_Player_Season_Honours", "Nation_Dim", "Player_Attr_Snap_O",
    "Player_Attr_Snap_G", "Player_Attribute_Changes", "Period_Dim", "Data_Issues",
}

DERIVED_MUTABLE_SHEETS = set(DERIVED_FIELDS)


def _rows(ws):
    h=headers(ws)
    return [{name: row[col-1] for name,col in h.items()} for row in ws.iter_rows(min_row=2, values_only=True) if any(v not in (None, '') for v in row)]

def _package_structure(path: Path):
    wb=load_workbook(path, data_only=False)
    out={"sheetnames": tuple(wb.sheetnames), "defined_names": tuple(sorted((x.name, str(x.attr_text)) for x in wb.defined_names.values()))}
    for ws in wb.worksheets:
        out[ws.title]={
            "tables": tuple(sorted((table.name, table.ref) for table in ws.tables.values())),
            "merged": tuple(sorted(str(x) for x in ws.merged_cells.ranges)),
            "validations": tuple(sorted(str(x.sqref)+":"+str(x.type)+":"+str(x.formula1)+":"+str(x.formula2) for x in ws.data_validations.dataValidation)),
            "sheet_state": ws.sheet_state,
            "freeze": str(ws.freeze_panes),
            "headers": tuple(c.value for c in ws[1]),
            "header_styles": tuple(c.style_id for c in ws[1]),
        }
    wb.close(); return out

def _date(x):
    if isinstance(x,date): return x
    return date.fromisoformat(str(x))

def _attr_validation(wb):
    errors=[]; pids={str(x[0]) for x in wb['Player_Dim'].iter_rows(min_row=2,values_only=True) if x[0]}
    histories=defaultdict(dict)
    for schema,sheet,names in (("OUTFIELD","Player_Attr_Snap_O",OUTFIELD),("GOALKEEPER","Player_Attr_Snap_G",GOALKEEPER)):
        if sheet not in wb.sheetnames or tuple(c.value for c in wb[sheet][1]) != NEW_SHEETS[sheet]: errors.append(f"ATTRIBUTE_SHEET_SCHEMA_INVALID:{sheet}"); continue
        keys=set()
        for r in _rows(wb[sheet]):
            key=(str(r.get('Player_ID')),str(r.get('Snapshot_Date')),str(r.get('Attribute_Schema')))
            if key in keys: errors.append('ATTRIBUTE_NATURAL_KEY_DUPLICATE')
            keys.add(key)
            if key[0] not in pids: errors.append('ATTRIBUTE_PLAYER_ID_INVALID')
            if r.get('Attribute_Schema') != schema: errors.append('ATTRIBUTE_SCHEMA_INVALID')
            if r.get('Source_ID') in (None,''): errors.append('ATTRIBUTE_SOURCE_ID_MISSING')
            if not r.get('Verification_Status'): errors.append('ATTRIBUTE_VERIFICATION_STATUS_MISSING')
            try: _date(r.get('Snapshot_Date'))
            except (ValueError,TypeError): errors.append('ATTRIBUTE_SNAPSHOT_DATE_INVALID')
            if any(type(r.get(n)) is not int or not 1 <= r.get(n) <= 20 for n in names): errors.append('ATTRIBUTE_SCHEMA_36_38_OR_VALUE_INVALID')
            histories[(key[0],schema)][key[1]]=r
    changes=wb['Player_Attribute_Changes'] if 'Player_Attribute_Changes' in wb.sheetnames else None
    if changes is None or tuple(c.value for c in changes[1]) != NEW_SHEETS['Player_Attribute_Changes']: errors.append('ATTRIBUTE_SHEET_SCHEMA_INVALID:Player_Attribute_Changes')
    else:
        keys=set()
        for r in _rows(changes):
            key=(r.get('Player_ID'),r.get('From_Snapshot'),r.get('To_Snapshot'),r.get('Attribute_Name'))
            if key in keys: errors.append('ATTRIBUTE_CHANGE_NATURAL_KEY_DUPLICATE')
            keys.add(key)
            choices=[schema for schema in ('OUTFIELD','GOALKEEPER') if str(r.get('From_Snapshot')) in histories[(str(r.get('Player_ID')),schema)] and str(r.get('To_Snapshot')) in histories[(str(r.get('Player_ID')),schema)]]
            schema=choices[0] if len(choices)==1 else None
            try:
                old,new=str(r.get('From_Snapshot')),str(r.get('To_Snapshot'))
                if not schema or _date(old)>=_date(new) or int(r.get('Delta')) != int(r.get('New_Value'))-int(r.get('Old_Value')): raise ValueError
                hist=sorted(histories[(str(r.get('Player_ID')),schema)])
                if old not in hist or new not in hist or hist.index(new)!=hist.index(old)+1: raise ValueError
                if histories[(str(r.get('Player_ID')),schema)][old][r['Attribute_Name']] != r.get('Old_Value') or histories[(str(r.get('Player_ID')),schema)][new][r['Attribute_Name']] != r.get('New_Value'): raise ValueError
            except (ValueError,TypeError): errors.append('ATTRIBUTE_CHANGES_DERIVATION_INVALID')
    return sorted(set(errors))

def _contract(baseline, candidate, mode):
    b=load_workbook(baseline,data_only=False); c=load_workbook(candidate,data_only=False)
    errors=[]; bs,cs=_package_structure(baseline),_package_structure(candidate)
    ledger_errors, transitions = observations(b,c); errors.extend(ledger_errors)
    schema_already_present=all(s in b.sheetnames for s in NEW_SHEETS)
    expected_order=tuple(b.sheetnames) if schema_already_present else tuple(b.sheetnames)+tuple(NEW_SHEETS)
    if LEDGER in c.sheetnames and LEDGER not in b.sheetnames: expected_order += (LEDGER,)
    if tuple(c.sheetnames)!=expected_order: errors.append('SHEET_NAMES_OR_ORDER_CHANGED')
    if bs['defined_names'] != cs['defined_names']: errors.append('NAMED_RANGES_CHANGED')
    for sheet in b.sheetnames:
        bp,cp=bs[sheet],cs.get(sheet)
        if cp is None: errors.append(f'REMOVED_SHEET:{sheet}'); continue
        for k in ('merged','validations','sheet_state','freeze','headers','header_styles'):
            if bp[k]!=cp[k]: errors.append(f'STRUCTURAL_METADATA_CHANGED:{sheet}:{k}')
        if bp['tables'] != cp['tables']:
            bnames={n for n,_ in bp['tables']}; cnames={n for n,_ in cp['tables']}
            if bnames != cnames or sheet not in MUTABLE_SHEETS:
                errors.append(f'STRUCTURAL_METADATA_CHANGED:{sheet}:tables')
            else:
                # Table names and start coordinates are frozen; only the end row may
                # extend, and never beyond appended worksheet data.
                from openpyxl.utils.cell import range_boundaries
                for (_,old),(_,new) in zip(sorted(bp['tables']),sorted(cp['tables'])):
                    oc1,or1,oc2,or2=range_boundaries(old); nc1,nr1,nc2,nr2=range_boundaries(new)
                    if (oc1,or1,oc2)!=(nc1,nr1,nc2) or nr2<or2 or nr2>c[sheet].max_row:
                        errors.append(f'STRUCTURAL_METADATA_CHANGED:{sheet}:tables')
                        break
        br=list(b[sheet].values); cr=list(c[sheet].values)
        if sheet=='Nation_Dim':
            if cr[:len(br)]!=br: errors.append('NATION_DIM_BASELINE_CHANGED')
            extra=cr[len(br):]
            h=headers(c[sheet]); valid=[r for r in extra if (str(r[h['National_Team_ID']-1]),str(r[h['Alias_Name']-1]),str(r[h['Canonical_Display_Name']-1]))==CONTROLLED_ALIAS]
            if (schema_already_present and extra) or (not schema_already_present and (len(extra) != 1 or len(valid) != 1)):
                errors.append('CONTROLLED_ALIAS_CONTRACT_FAILED')
        elif sheet in DERIVED_MUTABLE_SHEETS:
            errors.extend(derived_cell_guard(b,c,sheet))
        elif sheet == 'Data_Issues':
            if len(cr)<len(br): errors.append('ISSUE_REMOVED')
            h=headers(c[sheet])
            for old,new in zip(br,cr):
                if old==new: continue
                allowed=list(old)
                issue=str(old[h['Issue']-1] or '')
                if 'both source authorities retained without overwrite' in issue and 'coverage' in issue.lower():
                    allowed[h['Status']-1]='已確認（涵蓋期間／範圍不同；原始來源均保留，無需調和）'
                if tuple(allowed)!=new: errors.append('UNAUTHORIZED_ISSUE_CHANGE')
            if len(cr)>len(br): errors.append('UNPLANNED_ISSUE_APPEND')
        elif sheet == 'Period_Dim':
            if cr[:len(br)]!=br: errors.append('PERIOD_BASELINE_CHANGED')
            h=headers(c[sheet]); ch=headers(c['Player_League_Career'])
            observed={r.get('Season_Display') for sn in ('Player_League_Career','Player_Club_Competition_Stats','Player_Club_Season_Totals','Player_National_Team_Stats') for r in _rows(c[sn])}
            for row in cr[len(br):]:
                item={k:row[v-1] for k,v in h.items()}
                try:
                    expected=period_fields(item['Source_Period_Display'])
                    old_equiv={r.get('Period_ID') for r in _rows(b[sheet]) if r.get('Canonical_Period_Display')==expected['Canonical_Period_Display'] and r.get('Period_Type')==expected['Period_Type']}
                    if old_equiv and len(old_equiv)==1: expected['Period_ID']=next(iter(old_equiv))
                    if item!=expected or item['Source_Period_Display'] not in observed: raise ValueError()
                except (ValueError,KeyError): errors.append('UNSUPPORTED_PERIOD_APPEND')
        elif sheet == LEDGER:
            pass # append-only policy replay above
        elif sheet == 'Player_Attribute_Changes':
            pass # exact adjacent-snapshot recomputation below
        elif sheet in MUTABLE_SHEETS:
            h=headers(b[sheet])
            if len(cr)<len(br): errors.append(f'BASELINE_ROWS_REMOVED:{sheet}')
            for old,new in zip(br,cr):
                if old==new: continue
                d={k:old[v-1] for k,v in h.items()}
                expected=transitions.get((sheet,dump(d)))
                if sheet=='Record_Identity_Map' and expected is None:
                    try:
                        allowed=list(old); sh=d['Origin_Sheet']; rh=headers(c[sh]); rr=int(d['Origin_Row'])
                        if sh not in ('Player_League_Career','Player_Club_Competition_Stats','Player_Club_Season_Totals'): raise ValueError()
                        allowed[h['Verification_Status']-1]=c[sh].cell(rr,rh['Verification_Status']).value
                        if tuple(allowed)==new: continue
                    except (ValueError,KeyError,TypeError): pass
                if expected is None or tuple(expected.get(k) for k in h)!=new:
                    errors.append(f'EXISTING_CELLS_REWRITTEN:{sheet}')
        elif cr!=br: errors.append(f'UNEXPECTED_DATA_CHANGE:{sheet}')
    for sheet,header in NEW_SHEETS.items():
        if sheet not in c.sheetnames or tuple(x.value for x in c[sheet][1])!=header: errors.append(f'NEW_SHEET_CONTRACT_FAILED:{sheet}')
        elif mode=='schema' and c[sheet].max_row != 1: errors.append(f'POPULATED_SCHEMA_CANDIDATE:{sheet}')
    b.close(); c.close(); return sorted(set(errors))

def _national(wb, baseline_wb=None):
    errors=[]; report=[]; pids={str(r[0]) for r in wb['Player_Dim'].iter_rows(min_row=2,values_only=True)}; nations={str(r[0]) for r in wb['Nation_Dim'].iter_rows(min_row=2,values_only=True)}
    baseline_rows=set()
    if baseline_wb is not None:
        baseline_rows={tuple(r) for r in baseline_wb['Player_National_Team_Stats'].iter_rows(min_row=2,values_only=True)}
    rows=_rows(wb['Player_National_Team_Stats']); keys=set(); agg=defaultdict(lambda:{'Apps':0,'Goals':0})
    for r in rows:
        if tuple(r.get(name) for name in headers(wb['Player_National_Team_Stats'])) in baseline_rows: continue
        level=r.get('Team_Level')
        if level not in {'Senior','U21'}: continue # legacy V1 evidence remains valid but is not V1.1 authority
        key=(r.get('Player_ID'),r.get('Nation_ID'),level,r.get('Season_ID'),r.get('Country_Raw'),r.get('Context_Club'))
        if key in keys: errors.append('NATIONAL_TEAM_NATURAL_KEY_DUPLICATE')
        keys.add(key)
        if str(r.get('Player_ID')) not in pids or str(r.get('Nation_ID')) not in nations or r.get('Source_ID') in (None,''): errors.append('NATIONAL_FK_OR_SOURCE_INVALID')
        try: agg[(str(r['Player_ID']),level)]['Apps']+=int(r.get('Apps') or r.get('Apps_Raw') or 0); agg[(str(r['Player_ID']),level)]['Goals']+=int(r.get('Goals') or 0)
        except (ValueError,TypeError): errors.append('NATIONAL_NUMERIC_INVALID')
    profiles={}
    for r in _rows(wb['Player_Profile_Snapshots']):
        pid=str(r.get('Player_ID')); snap=str(r.get('Snapshot_Date'))
        if pid not in profiles or snap>str(profiles[pid].get('Snapshot_Date')): profiles[pid]=r
    for (pid,level), totals in sorted(agg.items()):
        p=profiles.get(pid,{})
        caps,goals=('Senior_NT_Caps','Senior_NT_Goals') if level=='Senior' else ('U21_Caps','U21_Goals')
        declared={'Apps':int(p.get(caps) or 0),'Goals':int(p.get(goals) or 0)}
        report.append({'Player_ID':pid,'Team_Level':level,'seasonal':totals,'source_declared':declared,'classification':'RECONCILED' if totals==declared else 'RECONCILIATION_ISSUE'})
    return sorted(set(errors)),report

def validate_v11(baseline:Path,candidate:Path,*,mode='populated'):
    if mode not in {'schema','populated'}: raise ValueError('V11_VALIDATION_MODE_INVALID')
    baseline,candidate=Path(baseline),Path(candidate); zip_reload=False
    try:
        with zipfile.ZipFile(candidate) as z: zip_reload=z.testzip() is None
        load_workbook(candidate,read_only=True).close()
    except Exception: zip_reload=False
    wb=load_workbook(candidate,data_only=False)
    contract=_contract(baseline,candidate,mode); attrs=_attr_validation(wb); baseline_wb=load_workbook(baseline,data_only=False); national,national_report=_national(wb, baseline_wb); baseline_wb.close()
    pids={str(r[0]) for r in wb['Player_Dim'].iter_rows(min_row=2,values_only=True)}; source={str(r[0]) for r in wb['Source_Index'].iter_rows(min_row=2,values_only=True)}
    identity=[]
    for r in _rows(wb['Player_Profile_Snapshots']):
        if str(r.get('Player_ID')) not in pids: identity.append('PROFILE_PLAYER_ID_INVALID')
        if r.get('Source_ID') not in source: identity.append('PROFILE_SOURCE_ID_INVALID')
    formula=formula_errors(candidate); generic=generic_validate(candidate); wb.close()
    derived_errors=recompute_guard(candidate)
    errors=contract+attrs+national+identity+formula+derived_errors + ([] if all(generic.values()) else ['GENERIC_VALIDATION_FAILED'])
    return {'pass':zip_reload and not errors,'mode':mode,'zip_reload':zip_reload,'expected_changes':['validator-owned V1.1 sheets + controlled 英格兰 alias + append-only V1.1 import rows'],'unexpected_changes':contract+derived_errors,'unexpected_changes_count':len(contract+derived_errors), 'baseline_sha256':__import__('hashlib').sha256(baseline.read_bytes()).hexdigest(), 'candidate_sha256':__import__('hashlib').sha256(candidate.read_bytes()).hexdigest(),'attribute_validation':{'pass':not attrs,'errors':attrs},'identity_errors':identity,'national_team_errors':national,'national_career_reconciliation':national_report,'formula_errors':formula,'foreign_key_errors':[],'generic_validation':generic}
