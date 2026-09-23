"""Isolated FM World Import V1 prototype; target sheets only."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, re, shutil, zipfile
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import range_boundaries

FORMAT = "FORMAT=FM_WORLD_IMPORT_V1"
PLAYER_FIELDS = {"Name","Raw_Name","Nationality","Date_of_Birth","Current_Club","Shirt_Number","Position","International_Caps","International_Goals","U21_Caps","U21_Goals","Snapshot"}
TARGETS = ("Player_Club_Competition_Stats", "Player_Club_Season_Totals")
NULLS = {"NULL", "-"}

class ImportFailure(ValueError): pass
@dataclass
class RawValue:
    normalized: object
    token: str | None
    present: bool
@dataclass
class Record:
    family: str
    values: dict
    raw: dict
@dataclass
class Document:
    player: dict
    player_raw: dict
    records: list[Record]

def normalize(v, present=True):
    if not present: return RawValue(None, None, False)
    v=v.strip()
    return RawValue(None, v, True) if v in NULLS or v == "" else RawValue(v, v, True)

def parse(text: str) -> Document:
    lines=[x.rstrip("\r") for x in text.splitlines()]
    if not lines or lines[0] != FORMAT: raise ImportFailure("FORMAT_VERSION_REQUIRED_OR_UNSUPPORTED")
    i=1; player={}; player_raw={}; records=[]; seen=set()
    while i < len(lines):
        if not lines[i].strip(): i+=1; continue
        section=lines[i].strip(); i+=1
        block=[]
        while i < len(lines) and lines[i].strip() not in {"PLAYER","CLUB_COMPETITION_STATS","CLUB_TOTALS"}:
            block.append(lines[i]); i+=1
        if section == "PLAYER":
            for line in block:
                if not line.strip(): continue
                if "=" not in line: raise ImportFailure("PLAYER_MALFORMED")
                k,v=line.split("=",1); k=k.strip()
                if k not in PLAYER_FIELDS: raise ImportFailure(f"PLAYER_FIELD_UNSUPPORTED:{k}")
                if k in seen: raise ImportFailure(f"PLAYER_FIELD_DUPLICATE:{k}")
                seen.add(k); player[k]=v.strip(); player_raw[k]=normalize(v)
            continue
        if section not in {"CLUB_COMPETITION_STATS","CLUB_TOTALS"}:
            raise ImportFailure(f"SECTION_UNSUPPORTED:{section}")
        nonblank=[x for x in block if x.strip()]
        if not nonblank: raise ImportFailure(f"SECTION_EMPTY:{section}")
        heads=nonblank[0].split("|")
        required=["Season","Club","Apps_Raw"] + (["Competition"] if section=="CLUB_COMPETITION_STATS" else [])
        if len(set(heads))!=len(heads) or any(x not in heads for x in required): raise ImportFailure(f"HEADER_INVALID:{section}")
        # Conceded90 is a recognised FM source field.  The current target authority
        # schema has no semantic destination, so it is retained in Record.raw for
        # audit but deliberately never materialised into a workbook cell.
        allowed={"Season","Club","Competition","Apps_Raw","Goals","Penalties","Assists","POTM","Yellow","Red","TacklesWon90","PassPct","Dribbles90","ShotsOnTargetPct","Fouls","Fouled","Rating","Conceded","CleanSheets","Conceded90"}
        unknown=set(heads)-allowed
        if unknown: raise ImportFailure(f"HEADER_UNSUPPORTED:{section}:{sorted(unknown)}")
        for line in nonblank[1:]:
            cells=line.split("|")
            if len(cells)!=len(heads): raise ImportFailure(f"COLUMN_COUNT:{section}")
            raw={k:normalize(v) for k,v in zip(heads,cells)}
            vals={k:x.normalized for k,x in raw.items()}
            if not vals["Season"] or not vals["Club"] or (section=="CLUB_COMPETITION_STATS" and not vals["Competition"]): raise ImportFailure("IDENTITY_NULL")
            records.append(Record(section,vals,raw))
    if not player.get("Name"): raise ImportFailure("PLAYER_NAME_REQUIRED")
    if not records: raise ImportFailure("NO_TARGET_RECORDS")
    return Document(player,player_raw,records)

def headers(ws): return {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
def indexes(ws, idfield):
    h=headers(ws); out=defaultdict(set)
    for row in ws.iter_rows(min_row=2,values_only=True):
        ident=str(row[h[idfield]-1] or "")
        for col in ("Canonical_Display_Name","Alias_Name"):
            if col in h and row[h[col]-1] not in (None,""): out[str(row[h[col]-1])].add(ident)
    return out
def resolve_one(index, token, kind, coverage):
    got=index.get(token,set()); coverage.setdefault(kind,{})[token]=sorted(got)
    if len(got)==1: return next(iter(got))
    raise ImportFailure(f"{kind.upper()}_{'NOT_FOUND' if not got else 'AMBIGUOUS'}:{token}")
def resolve(doc, wb):
    coverage=defaultdict(dict)
    p=indexes(wb["Player_Dim"],"Player_ID"); c=indexes(wb["Club_Dim"],"Club_ID")
    ph=headers(wb["Period_Dim"]); pi=defaultdict(set)
    for row in wb["Period_Dim"].iter_rows(min_row=2,values_only=True):
        if str(row[ph["Period_Type"]-1] or "") == "Season": pi[str(row[ph["Source_Period_Display"]-1] or "")].add(str(row[ph["Period_ID"]-1]))
    tokens=[doc.player["Name"]]+([doc.player["Raw_Name"]] if doc.player.get("Raw_Name") else [])
    ids={resolve_one(p,x,"player",coverage) for x in tokens}
    if len(ids)!=1: raise ImportFailure("PLAYER_TOKENS_DIFFER")
    pid=next(iter(ids)); out=[]
    for rec in doc.records:
        club=resolve_one(c,rec.values["Club"],"club",coverage); season=resolve_one(pi,rec.values["Season"],"period",coverage)
        out.append((rec,pid,club,season))
    return out,coverage

def parse_apps(v):
    if v in (None,"-","NULL"): return None,None,None
    m=re.fullmatch(r"(\d+)(?:\((\d+)\))?",str(v))
    if not m: raise ImportFailure(f"APPS_RAW_INVALID:{v}")
    starts=int(m.group(1)); subs=int(m.group(2) or 0); return starts+subs,starts,subs
def num(v):
    if v is None:return None
    try:return float(v) if "." in str(v) else int(v)
    except ValueError: raise ImportFailure(f"NUMBER_INVALID:{v}")
def pct(v):
    if v is None:return None
    if not re.fullmatch(r"\d+%",str(v)): raise ImportFailure(f"PERCENT_INVALID:{v}")
    return str(v)
def source_id(metadata, ws):
    # Exact Source_Index reuse is allowed only for matching actual wrapper metadata.
    h=headers(ws); matches=[]
    for r in ws.iter_rows(min_row=2,values_only=True):
        if str(r[h["File_Name"]-1] or "")==metadata["file_name"] and str(r[h["Local_Path"]-1] or "")==metadata["local_path"]: matches.append(str(r[h["Source_ID"]-1]))
    if len(matches)==1:return matches[0],False
    if len(matches)>1:raise ImportFailure("SOURCE_INDEX_AMBIGUOUS")
    safe=re.sub(r"[^A-Za-z0-9_-]+","-",metadata["file_name"].rsplit(".",1)[0]).strip("-")
    return f"SRC-DISCORD-{metadata['message_id']}-{metadata['attachment_sequence']}-{safe}",True
def dictrow(ws, data): return [data.get(c.value) for c in ws[1]]
def refresh(ws):
    for t in ws.tables.values():
        a,b,c,_=range_boundaries(t.ref); t.ref=f"{get_column_letter(a)}{b}:{get_column_letter(c)}{ws.max_row}"
def import_document(base:Path, output:Path, text:str, metadata:dict):
    doc=parse(text); shutil.copy2(base,output); wb=load_workbook(output,data_only=False)
    resolved,coverage=resolve(doc,wb); sid,newsource=source_id(metadata,wb["Source_Index"])
    non_materialized=[
        {"family":rec.family,"season":rec.values.get("Season"),"club":rec.values.get("Club"),
         "competition":rec.values.get("Competition"),"field":"Conceded90",
         "raw_token":rec.raw["Conceded90"].token,"normalized":rec.values.get("Conceded90")}
        for rec,_,_,_ in resolved if "Conceded90" in rec.raw and rec.values.get("Conceded90") is not None
    ]
    # Audit payload is not authority storage.  Reject non-null data until a formal destination exists.
    if non_materialized:
        raise ImportFailure("UNMATERIALIZED_SOURCE_FIELD: Conceded90 has no approved authority destination")
    # Detect all authority collisions before changing workbook.
    for rec,pid,cid,season in resolved:
        ws=wb[TARGETS[0] if rec.family=="CLUB_COMPETITION_STATS" else TARGETS[1]]; h=headers(ws)
        keys=[pid,season,cid]+([rec.values["Competition"]] if rec.family=="CLUB_COMPETITION_STATS" else [])
        for r in ws.iter_rows(min_row=2,values_only=True):
            old=[r[h[x]-1] for x in (["Player_ID","Season_ID","Club_ID"]+(["Competition_Raw"] if rec.family=="CLUB_COMPETITION_STATS" else []))]
            if old==keys and str(r[h["Source_ID"]-1])!=sid: raise ImportFailure("SOURCE_CONFLICT_UNRESOLVED")
    if newsource:
        wb["Source_Index"].append(dictrow(wb["Source_Index"],{"Source_ID":sid,"File_Name":metadata["file_name"],"Local_Path":metadata["local_path"],"Domain":"FM World Import V1","Season_Context":doc.player.get("Snapshot"),"Source_Note":"execution provenance"}))
    for rec,pid,cid,season in resolved:
        ws=wb[TARGETS[0] if rec.family=="CLUB_COMPETITION_STATS" else TARGETS[1]]; apps,starts,subs=parse_apps(rec.values["Apps_Raw"])
        raw=lambda k: rec.raw[k].token if k in rec.raw else None
        d={"Season_ID":season,"Season_Display":rec.values["Season"],"Player_ID":pid,"Club_ID":cid,"Club_Raw":rec.values["Club"],"Apps_Raw":raw("Apps_Raw"),"Apps":apps,"Starts":starts,"Sub_Appearances":subs,"Goals":num(rec.values.get("Goals")),"Penalties_Raw":raw("Penalties"),"Assists":num(rec.values.get("Assists")),"POTM":num(rec.values.get("POTM")),"Yellow":num(rec.values.get("Yellow")),"Red":num(rec.values.get("Red")),"TacklesWon90":num(rec.values.get("TacklesWon90")),"PassPct_Raw":raw("PassPct"),"Dribbles90":num(rec.values.get("Dribbles90")),"ShotsOnTargetPct_Raw":raw("ShotsOnTargetPct"),"Fouls":num(rec.values.get("Fouls")),"Fouled":num(rec.values.get("Fouled")),"Rating":num(rec.values.get("Rating")),"Goals_Conceded":num(rec.values.get("Conceded")),"Clean_Sheets":num(rec.values.get("CleanSheets")),"Source_ID":sid,"Verification_Status":metadata.get("verification_status")}
        if rec.family=="CLUB_COMPETITION_STATS":d["Competition_Raw"]=rec.values["Competition"]
        ws.append(dictrow(ws,d)); refresh(ws)
    refresh(wb["Source_Index"]); wb.save(output)
    return {"source_id":sid,"new_source":newsource,"coverage":coverage,"records":len(resolved),
            "non_materialized_audit":non_materialized}

def validate(path:Path):
    result={"zip_integrity":False,"reload":False,"foreign_keys":False,"source_index":False,"apps":False,"table_ranges":False,"formulas":True}
    try:
        with zipfile.ZipFile(path) as z: result["zip_integrity"]=z.testzip() is None
        wb=load_workbook(path,data_only=False); result["reload"]=True
        pd={r[0] for r in wb["Player_Dim"].iter_rows(min_row=2,values_only=True)}; cd={r[0] for r in wb["Club_Dim"].iter_rows(min_row=2,values_only=True)}; per={r[0] for r in wb["Period_Dim"].iter_rows(min_row=2,values_only=True)}; si={r[0] for r in wb["Source_Index"].iter_rows(min_row=2,values_only=True)}
        fk=src=apps=tab=True
        for sn in TARGETS:
            ws=wb[sn]; h=headers(ws)
            for r in ws.iter_rows(min_row=2,values_only=True):
                fk &= r[h['Player_ID']-1] in pd and r[h['Club_ID']-1] in cd and r[h['Season_ID']-1] in per; src &= r[h['Source_ID']-1] in si
                a,s,u=parse_apps(r[h['Apps_Raw']-1]); apps &= (a,s,u)==(r[h['Apps']-1],r[h['Starts']-1],r[h['Sub_Appearances']-1])
            for t in ws.tables.values(): tab &= range_boundaries(t.ref)[3]==ws.max_row
        result.update(foreign_keys=fk,source_index=src,apps=apps,table_ranges=tab)
    except Exception as e: result['error']=str(e)
    return result

def app_violations(path:Path):
    """Stable, row-level Apps derived-field violations for baseline/output deltas."""
    wb=load_workbook(path,data_only=False)
    out=[]
    for sn in TARGETS:
        ws=wb[sn]; h=headers(ws)
        for row_no,r in enumerate(ws.iter_rows(min_row=2,values_only=True),2):
            raw=r[h['Apps_Raw']-1]
            try: expected=parse_apps(raw)
            except ImportFailure:
                out.append((sn,row_no,str(r[h['Source_ID']-1]),'APPS_RAW_INVALID',str(raw)))
                continue
            actual=(r[h['Apps']-1],r[h['Starts']-1],r[h['Sub_Appearances']-1])
            if expected != actual:
                # Use business identity rather than row number so removal/reappend is comparable.
                key=(str(r[h['Source_ID']-1]),str(r[h['Player_ID']-1]),str(r[h['Club_ID']-1]),str(r[h['Season_ID']-1]),str(r[h['Competition_Raw']-1]) if 'Competition_Raw' in h else '')
                out.append((sn,*key,'APPS_DERIVATION',str(raw),repr(expected),repr(actual)))
    return sorted(out)
