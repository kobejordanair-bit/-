"""Preservation-safe derived rebuild on workbook copies; never use against canonical."""
from __future__ import annotations
from collections import defaultdict
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
import zipfile
from openpyxl import load_workbook
from generic_importer import headers, dictrow, refresh
from governance_migration import validate_duplicate_table_consistency

BARCELONA_ID='C-0030'
# destination -> authority source column.  These two names differ deliberately.
SEASON_SOURCE={'Apps':'Apps','Starts':'Starts','Goals':'Goals','Assists':'Assists','Avg_Rating':'Rating','MOTM':'POTM','Yellow':'Yellow','Red':'Red','Goals_Conceded':'Goals_Conceded','Clean_Sheets':'Clean_Sheets','Source_ID':'Source_ID'}
SEASON_SAFE=tuple(SEASON_SOURCE)+('Verification_Status',)
CAREER_SAFE=('Barcelona_Seasons','Apps','Goals','Assists','MOTM','Avg_Rating','Goals_Conceded','Clean_Sheets')

# Machine-readable audit: omitted columns are intentionally not automatic rebuild targets.
DEPENDENCY_MATRIX={
 'Barcelona_Player_Season_Stats': {
  'Season_ID':['Player_Club_Season_Totals','Season_ID','Player_ID+Season_ID+Club_ID','PURE_DERIVED','YES'],
  'Player_ID':['Player_Club_Season_Totals','Player_ID','Player_ID+Season_ID+Club_ID','PURE_DERIVED','YES'],
  **{c:['Player_Club_Season_Totals',SEASON_SOURCE[c],'Player_ID+Season_ID+Club_ID','PURE_DERIVED','YES'] for c in SEASON_SAFE if c not in ('Verification_Status',)},
  'Verification_Status':['Player_Club_Season_Totals','Verification_Status','Player_ID+Season_ID+Club_ID','CONTROLLED_DERIVED','YES'],
  'Minutes':['None',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'Major_Awards':['award / trophy authority sheets + Record_Identity_Map',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'Squad_Role':['Barcelona_Squad_History',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
 },
 'Barcelona_Player_Career': {
  'Player_ID':['Player_Club_Season_Totals','Player_ID','Player_ID','PURE_DERIVED','YES'],
  'Player_Name':['Player_Dim','Canonical_Display_Name','Player_ID','CONTROLLED_DERIVED','YES'],
  'Barcelona_Seasons':['Barcelona_Player_Season_Stats','Season_ID','Player_ID','PURE_DERIVED','YES'],
  **{c:['Barcelona_Player_Season_Stats',c,'Player_ID','PURE_DERIVED','YES'] for c in CAREER_SAFE if c not in ('Barcelona_Seasons','Avg_Rating')},
  'Avg_Rating':['Barcelona_Player_Season_Stats','Apps+Avg_Rating','Player_ID','PURE_DERIVED (apps-weighted)','YES'],
  'LaLiga_Team_Championships_While_At_Barcelona':['Barcelona_History / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'UCL_Team_Championships_While_At_Barcelona':['Barcelona_UCL_Journey / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'Copa_Team_Championships_While_At_Barcelona':['National_Tournaments / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'Supercopa_Team_Championships_While_At_Barcelona':['National_Tournaments / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'UEFA_SuperCup_Team_Championships_While_At_Barcelona':['UEFA_Super_Cup / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'Club_World_Cup_Team_Championships_While_At_Barcelona':['Barcelona_Club_World_Cup / trophy authority sheets',None,'Player_ID+Season_ID','MANUAL_OR_SEMANTIC','NO'],
  'FIFPro_Count':['FIFA_FIFPro_World_XI',None,'Player_ID','MANUAL_OR_SEMANTIC','NO'],
  'Ballon_dOr_Top3_Count':['Ballon_dOr',None,'Player_ID','MANUAL_OR_SEMANTIC','NO'],
  'Major_Awards':['award / trophy authority sheets + Record_Identity_Map',None,'Player_ID','MANUAL_OR_SEMANTIC','NO'],
  'Derivation_Status':['Multiple authority sheets',None,'Player_ID','MANUAL_OR_SEMANTIC','NO'],
  'Derivation_Sources':['Multiple authority sheets',None,'Player_ID','MANUAL_OR_SEMANTIC','NO'],
 },
}

def _numeric(v):
 return None if v in (None,'') else float(v)

def _decimal(v):
 """Convert displayed numeric values without binary-float boundary drift."""
 if v in (None,''):
  return None
 try:
  return Decimal(str(v))
 except (InvalidOperation, ValueError):
  return None

def reconcile_league_career_rating(source_rating, seasonal_ratings, *, apps, goals, assists, potm,
                                   source_apps, source_goals, source_assists, source_potm):
 """Classify source-vs-displayed-rating variance without mutating source totals.

 The exact non-rating aggregates are a prerequisite.  Rating is assessed using
 Decimal and the unrounded apps-weighted displayed seasonal values.
 """
 exact = (apps, goals, assists, potm) == (source_apps, source_goals, source_assists, source_potm)
 total_apps = sum((_decimal(a) or Decimal('0')) for _, a in seasonal_ratings)
 weighted = (sum((_decimal(r) or Decimal('0')) * (_decimal(a) or Decimal('0')) for r, a in seasonal_ratings) / total_apps
             if total_apps else None)
 source = _decimal(source_rating)
 difference = abs(source-weighted) if source is not None and weighted is not None else None
 return {
  'classification': 'ROUNDING_VARIANCE_ACCEPTED' if exact and difference is not None and difference <= Decimal('0.01') else 'RECONCILIATION_ISSUE',
  'source_rating': source_rating, 'displayed_weighted_rating': str(weighted) if weighted is not None else None,
  'difference': str(difference) if difference is not None else None,
  'source_rating_preserved': True,
 }
def _same(a,b):
 return a==b or (isinstance(a,(int,float)) and isinstance(b,(int,float)) and float(a)==float(b))
def _set(ws,row,col,value,changes):
 old=ws.cell(row,col).value
 if not _same(old,value): ws.cell(row,col).value=value; changes.append(f'{ws.title}!{row}:{ws.cell(1,col).value}')
def _rows(ws):
 h=headers(ws)
 for i,r in enumerate(ws.iter_rows(min_row=2,values_only=True),2): yield i,{k:r[v-1] for k,v in h.items()}

def rebuild_derived(path:Path, *, affected_players=None):
 """Rebuild only approved deterministic fields and preserve all semantic/manual values."""
 wb=load_workbook(path); totals=wb['Player_Club_Season_Totals']; season=wb['Barcelona_Player_Season_Stats']; career=wb['Barcelona_Player_Career']; changes=[]
 source={(r['Player_ID'],r['Season_ID']):r for _,r in _rows(totals)
         if r.get('Statistical_Adoption_Status', 'ADOPTED')=='ADOPTED' and r['Club_ID']==BARCELONA_ID and r['Player_ID'] not in (None,'') and (re.fullmatch(r'PER-S-(\d{4})-\d{2}',str(r.get('Season_ID') or '')) and int(str(r['Season_ID'])[6:10])>=2023)}
 sh=headers(season); existing={ (r['Player_ID'],r['Season_ID']):rn for rn,r in _rows(season) }
 for key,r in source.items():
  rn=existing.get(key)
  if rn is None:
   payload={c:None for c in sh}; payload.update({'Season_ID':r['Season_ID'],'Player_ID':r['Player_ID']})
   for c in SEASON_SAFE: payload[c]=(('已確認（由 Club Season Totals 衍生）' if r.get('Verification_Status') else 'DERIVED_SOURCE_VERIFICATION_UNSPECIFIED') if c=='Verification_Status' else r.get(SEASON_SOURCE[c]))
   season.append(dictrow(season,payload)); rn=season.max_row; existing[key]=rn; changes.append(f'{season.title}!{rn}:ROW_ADDED')
  for c in SEASON_SAFE:
   v=('已確認（由 Club Season Totals 衍生）' if r.get('Verification_Status') else 'DERIVED_SOURCE_VERIFICATION_UNSPECIFIED') if c=='Verification_Status' else r.get(SEASON_SOURCE[c])
   _set(season,rn,sh[c],v,changes)
 refresh(season)
 # Aggregate from the freshly rebuilt safe seasonal fields; current historical/manual columns stay untouched.
 # Career Barcelona_Seasons is based only on first-team Barcelona totals with
 # actual appearances.  Do not infer it from existing season-row presence.
 ss=defaultdict(list)
 for r in source.values():
  if (_numeric(r.get('Apps')) or 0) > 0:
   ss[r['Player_ID']].append({
    'Season_ID':r['Season_ID'], 'Apps':r.get('Apps'), 'Goals':r.get('Goals'),
    'Assists':r.get('Assists'), 'MOTM':r.get('POTM'), 'Avg_Rating':r.get('Rating'),
    'Goals_Conceded':r.get('Goals_Conceded'), 'Clean_Sheets':r.get('Clean_Sheets'),
   })
 ch=headers(career); careers={r['Player_ID']:rn for rn,r in _rows(career)}
 # A career aggregate without an entity key is never a valid record.  Remove
 # the existing ghost row before calculating aggregates; reverse order avoids
 # index shifts and preserves every keyed/manual career record.
 ghost_rows=[rn for rn,r in _rows(career) if r['Player_ID'] in (None,'')]
 for rn in reversed(ghost_rows):
  career.delete_rows(rn,1); changes.append(f'{career.title}!{rn}:GHOST_ROW_REMOVED')
 careers={r['Player_ID']:rn for rn,r in _rows(career) if r['Player_ID'] not in (None,'')}
 names={r['Player_ID']:r['Canonical_Display_Name'] for _,r in _rows(wb['Player_Dim'])}
 for pid,rs in ss.items():
  rn=careers.get(pid)
  if rn is None:
   payload={c:None for c in ch}; payload.update({'Player_ID':pid,'Player_Name':names.get(pid),'Derivation_Status':'PARTIAL: deterministic club totals only'})
   career.append(dictrow(career,payload)); rn=career.max_row; careers[pid]=rn; changes.append(f'{career.title}!{rn}:ROW_ADDED')
  vals={'Barcelona_Seasons':len({r['Season_ID'] for r in rs})}
  for c in ('Apps','Goals','Assists','MOTM'):
   raw=[r.get(c) for r in rs]
   if all(v not in (None,'') for v in raw): vals[c]=sum(raw)
   elif affected_players and pid in affected_players: vals[c]=None
  for c in ('Goals_Conceded','Clean_Sheets'):
   raw=[r.get(c) for r in rs]
   if all(v not in (None,'') for v in raw): vals[c]=sum(raw)
   elif affected_players and pid in affected_players: vals[c]=None
  rated=[r for r in rs if r.get('Avg_Rating') not in (None,'') and r.get('Apps') not in (None,'')]
  if rated and sum(r['Apps'] for r in rated)>0: vals['Avg_Rating']=round(sum(float(r['Avg_Rating'])*r['Apps'] for r in rated)/sum(r['Apps'] for r in rated),2)
  for c,v in vals.items(): _set(career,rn,ch[c],v,changes)
 refresh(career); wb.save(path)
 return {'pass':True,'semantic_changes':len(changes),'changes':changes,'season_source_rows':len(source),'career_players':len(ss),'unresolved_manual_columns':{'Barcelona_Player_Season_Stats':['Minutes','Major_Awards','Squad_Role'],'Barcelona_Player_Career':[c for c in ch if c not in CAREER_SAFE and c not in ('Player_ID','Player_Name')]}}

def repair_barcelona_squad_history_table(path:Path):
 """Fix only the verified table reference; worksheet cell content must remain unchanged."""
 wb=load_workbook(path); ws=wb['Barcelona_Squad_History']; before=[[c.value for c in r] for r in ws.iter_rows()]
 table=ws.tables['BarcelonaSquadHistoryTable']; old=table.ref; table.ref=f'A1:N{ws.max_row}'; wb.save(path)
 # Reload proves OOXML serialization and catches broken refs/zip structures.
 with zipfile.ZipFile(path) as z: bad=z.testzip()
 check=load_workbook(path); after=[[c.value for c in r] for r in check['Barcelona_Squad_History'].iter_rows()]
 gate=validate_duplicate_table_consistency(path)
 return {'pass':old=='A1:N13' and table.ref=='A1:N15' and before==after and bad is None and gate['pass'],'old_ref':old,'new_ref':'A1:N15','semantic_cell_changes':sum(a!=b for x,y in zip(before,after) for a,b in zip(x,y)),'zip_error':bad,'table_gate':gate}

def formula_errors(path:Path):
 wb=load_workbook(path,data_only=False); bad=[]
 for ws in wb.worksheets:
  for row in ws.iter_rows():
   for c in row:
    if isinstance(c.value,str) and c.value in ('#REF!','#DIV/0!','#VALUE!','#NAME?','#N/A'): bad.append(f'{ws.title}!{c.coordinate}:{c.value}')
 return bad
