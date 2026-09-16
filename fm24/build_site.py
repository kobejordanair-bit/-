#!/usr/bin/env python3
"""Build the Blaugrana Archive: fm24.sqlite -> a single self-contained HTML page.

The workbook's distinguishing feature is lineage, not statistics: every fact
carries Source_ID / Verification_Status, and 437 award rows are still awaiting
identity resolution. The page is built as an archive viewer, so that backlog is
a first-class view rather than something swept under a rug.

Usage:
    python3 build_site.py [-d data/fm24.sqlite] [-o dist/index.html]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from resolver import IdentityResolver

BARCELONA_CLUB_ID = "C-0030"

# FM attribute groups, in the game's own column order.
TECHNICAL = ["傳球", "傳中", "盯人", "罰點球", "技術", "角球", "界外球", "盤帶", "搶斷", "任意球", "射門", "停球", "頭球", "遠射"]
MENTAL = ["才華", "防守站位", "工作投入", "集中", "決斷", "領導力", "侵略性", "視野", "團隊合作", "無球跑動", "意志力", "勇敢", "預判", "鎮定"]
PHYSICAL = ["爆發力", "彈跳", "靈活", "耐力", "平衡", "強壯", "速度", "體質"]

# Six radar axes aggregated from the 36 raw attributes.
RADAR_AXES = [
    ("終結", ["射門", "遠射", "頭球", "罰點球"]),
    ("創造", ["傳球", "視野", "傳中", "盤帶"]),
    ("防守", ["搶斷", "盯人", "防守站位", "侵略性"]),
    ("心理", ["決斷", "鎮定", "集中", "意志力"]),
    ("速度", ["速度", "爆發力", "靈活", "平衡"]),
    ("體能", ["強壯", "耐力", "彈跳", "體質"]),
]

TROPHY_COLUMNS = [
    ("LaLiga_Position", "西甲", lambda v: v == "1"),
    ("UCL_Result", "歐冠", lambda v: v == "冠軍"),
    ("Copa_Result", "國王盃", lambda v: v == "冠軍"),
    ("Supercopa_Result", "西超盃", lambda v: v == "冠軍"),
    ("UEFA_SuperCup_Result", "歐超盃", lambda v: v == "冠軍"),
    ("Club_World_Cup_Result", "世俱盃", lambda v: v == "冠軍"),
]


def num(value, default=None):
    """Parse the workbook's loose numerics: '0(2)' -> 0, '85%' -> 85, '' -> default."""
    if value is None:
        return default
    match = re.match(r"-?\d+(?:\.\d+)?", str(value).strip())
    return float(match.group()) if match else default


def as_int(value, default=0):
    parsed = num(value)
    return default if parsed is None else int(parsed)


def maybe_int(value):
    """None stays None. The workbook's policy is to keep unknown unknown, never 0."""
    parsed = num(value)
    return None if parsed is None else int(parsed)


def clean(value):
    """The source transcription writes a literal 'NULL' string for absent cells."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in ("", "NULL", "null", "!") else text


def norm_name(value: str | None) -> str:
    """Strip the separators that differ between Discord sources (・ vs ·)."""
    if not value:
        return ""
    return re.sub(r"[·・.\s]", "", str(value))


class Archive:
    def __init__(self, db_path: Path):
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = sqlite3.Row

    def q(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, args)]

    def one(self, sql: str, *args):
        rows = self.q(sql, *args)
        return rows[0] if rows else None

    # ---------------------------------------------------------------- meta --
    def meta(self) -> dict:
        sheets = self.q("SELECT sheet_name, table_name, row_count FROM _sheets ORDER BY row_count DESC")
        schema = self.one("SELECT * FROM Workbook_Schema_Metadata") or {}
        return {
            "generated": dt.date.today().isoformat(),
            "sheet_count": len(sheets),
            "row_count": sum(s["row_count"] for s in sheets),
            "schema_version": schema.get("Workbook_Schema_Version", "—"),
            "migration_id": schema.get("Migration_ID", "—"),
            "biggest_sheets": sheets[:8],
            "player_count": as_int(self.one("SELECT COUNT(DISTINCT Player_ID) n FROM Player_Dim")["n"]),
            "alias_count": as_int(self.one("SELECT COUNT(*) n FROM Player_Dim")["n"]),
            "club_count": as_int(self.one("SELECT COUNT(DISTINCT Club_ID) n FROM Club_Dim")["n"]),
            "nation_count": as_int(self.one("SELECT COUNT(DISTINCT National_Team_ID) n FROM Nation_Dim")["n"]),
            "identity_links": as_int(self.one("SELECT COUNT(*) n FROM Record_Identity_Map")["n"]),
        }

    # ------------------------------------------------------------- seasons --
    def seasons(self) -> list[dict]:
        transfers = defaultdict(lambda: {"in": [], "out": []})
        for row in self.q("SELECT * FROM Barcelona_Transfers"):
            bucket = "in" if row["Direction"] in ("轉入", "IN") else "out"
            transfers[row["Season"]][bucket].append(
                {"player": row["Player"], "club": row["Counterparty_Club"], "fee": row["Fee_Display"], "date": row["Date_Display"]}
            )

        leaders = defaultdict(list)
        for row in self.q("SELECT * FROM Barcelona_Season_Leaders"):
            leaders[row["Season"]].append({"metric": row["Metric"], "player": row["Player"], "value": row["Value"], "status": row["Season_Status"]})

        ballon = {}
        for row in self.q("SELECT * FROM Ballon_dOr WHERE Rank='1'"):
            ballon[row["Season"].replace("-", "/").replace("20", "", 1) if False else row["Season"]] = row

        out = []
        for row in self.q("SELECT * FROM Barcelona_Season_Master ORDER BY Season_ID"):
            season = row["Season"]
            titles = [label for col, label, won in TROPHY_COLUMNS if won(row[col] or "")]
            start_year = as_int(row["Season_ID"].split("-")[2])
            bdo = ballon.get(f"{start_year}-{start_year + 1}")
            out.append({
                "id": row["Season_ID"],
                "season": season,
                "position": row["LaLiga_Position"],
                "points": as_int(row["LaLiga_Points"]),
                "w": as_int(row["LaLiga_W"]), "d": as_int(row["LaLiga_D"]), "l": as_int(row["LaLiga_L"]),
                "gf": num(row["LaLiga_GF"]), "ga": num(row["LaLiga_GA"]),
                "ucl": row["UCL_Result"], "copa": row["Copa_Result"], "supercopa": row["Supercopa_Result"],
                "superCup": row["UEFA_SuperCup_Result"], "cwc": row["Club_World_Cup_Result"],
                "titles": titles,
                "trophies": as_int(row["Total_Trophies"]),
                "topScorer": row["Top_Scorer"], "topScorerGoals": as_int(row["Top_Scorer_Goals"]),
                "topAssist": row["Top_Assist"], "topAssistCount": as_int(row["Top_Assist_Count"]),
                "bestRatingPlayer": row["Best_Avg_Rating_Player"], "bestRating": row["Best_Avg_Rating"],
                "mostMotmPlayer": row["Most_MOTM_Player"], "mostMotm": as_int(row["Most_MOTM"]),
                "fanPlayer": row["Fan_Player_of_Season"],
                "arrival": row["Highest_Fee_Arrival"], "departure": row["Highest_Fee_Departure"],
                "netSpend": row["Net_Spend"],
                "note": row["Historical_Note"],
                "derivation": row["Derivation_Status"],
                "transfersIn": transfers[season]["in"], "transfersOut": transfers[season]["out"],
                "leaders": leaders[season],
                "ballonDor": {"player": bdo["Player"], "club": bdo["Club"]} if bdo else None,
            })
        return out

    # ------------------------------------------------------------- players --
    def players(self) -> list[dict]:
        profiles = {}
        for row in self.q("SELECT * FROM Player_Profile_Snapshots ORDER BY Snapshot_Date"):
            profiles[row["Player_ID"]] = row

        season_stats = defaultdict(list)
        for row in self.q(
            "SELECT * FROM Player_Club_Season_Totals WHERE Club_ID=? ORDER BY Season_ID", BARCELONA_CLUB_ID
        ):
            season_stats[row["Player_ID"]].append({
                "season": row["Season_Display"], "apps": as_int(row["Apps"]), "goals": as_int(row["Goals"]),
                "assists": as_int(row["Assists"]), "motm": as_int(row["POTM"]), "rating": num(row["Rating"]),
                "source": row["Source_ID"], "status": row["Verification_Status"],
            })

        attrs = {}
        for row in self.q("SELECT * FROM Player_Attr_Snap_O ORDER BY Snapshot_Date"):
            groups = {
                "技術": [(k, as_int(row[k])) for k in TECHNICAL if row.get(k)],
                "心理": [(k, as_int(row[k])) for k in MENTAL if row.get(k)],
                "體能": [(k, as_int(row[k])) for k in PHYSICAL if row.get(k)],
            }
            radar = []
            for axis, keys in RADAR_AXES:
                values = [as_int(row[k]) for k in keys if row.get(k)]
                radar.append({"axis": axis, "value": round(sum(values) / len(values), 1) if values else 0})
            attrs[row["Player_ID"]] = {
                "date": row["Snapshot_Date"], "schema": "OUTFIELD", "groups": groups, "radar": radar,
                "source": row["Source_ID"],
            }
        for row in self.q("SELECT * FROM Player_Attr_Snap_G ORDER BY Snapshot_Date"):
            keeper = [k for k in row if k not in ("Player_ID", "Snapshot_Date", "Attribute_Schema", "Source_ID", "Verification_Status", "_row")]
            attrs[row["Player_ID"]] = {
                "date": row["Snapshot_Date"], "schema": "GOALKEEPER",
                "groups": {"門將": [(k.replace("_", " "), as_int(row[k])) for k in keeper if row.get(k) and k not in MENTAL + PHYSICAL],
                           "心理": [(k, as_int(row[k])) for k in MENTAL if row.get(k)],
                           "體能": [(k, as_int(row[k])) for k in PHYSICAL if row.get(k)]},
                "radar": [], "source": row["Source_ID"],
            }

        national = defaultdict(list)
        for row in self.q("SELECT * FROM Player_Career_Summaries WHERE Team_Level!='Club'"):
            national[row["Player_ID"]].append({
                "scope": row["Scope"], "country": row["Country_Raw"], "apps": as_int(row["Apps"]),
                "goals": as_int(row["Goals"]), "assists": as_int(row["Assists"]),
            })

        out = []
        for row in self.q("SELECT * FROM Barcelona_Player_Career"):
            pid = row["Player_ID"]
            profile = profiles.get(pid, {})
            awards = [a.strip() for a in (row["Major_Awards"] or "").split("；") if a.strip()]
            out.append({
                "id": pid,
                "name": row["Player_Name"],
                "seasons": as_int(row["Barcelona_Seasons"]),
                "apps": as_int(row["Apps"]), "goals": as_int(row["Goals"]), "assists": as_int(row["Assists"]),
                "motm": as_int(row["MOTM"]), "rating": num(row["Avg_Rating"]),
                "cleanSheets": as_int(row["Clean_Sheets"]) if row["Clean_Sheets"] else None,
                "goalsConceded": as_int(row["Goals_Conceded"]) if row["Goals_Conceded"] else None,
                "titles": {
                    "西甲": as_int(row["LaLiga_Team_Championships_While_At_Barcelona"]),
                    "歐冠": as_int(row["UCL_Team_Championships_While_At_Barcelona"]),
                    "國王盃": as_int(row["Copa_Team_Championships_While_At_Barcelona"]),
                    "西超盃": as_int(row["Supercopa_Team_Championships_While_At_Barcelona"]),
                    "歐超盃": as_int(row["UEFA_SuperCup_Team_Championships_While_At_Barcelona"]),
                    "世俱盃": as_int(row["Club_World_Cup_Team_Championships_While_At_Barcelona"]),
                },
                "fifpro": as_int(row["FIFPro_Count"]),
                "ballonTop3": as_int(row["Ballon_dOr_Top3_Count"]),
                "awards": awards,
                "nationality": profile.get("Nationality_Raw"),
                "position": profile.get("Position_Raw"),
                "dob": profile.get("DOB"),
                "shirt": profile.get("Shirt_Number"),
                "seasonStats": season_stats.get(pid, []),
                "attrs": attrs.get(pid),
                "national": national.get(pid, []),
            })
        out.sort(key=lambda p: (-p["apps"], p["name"]))
        return out


    # ---------------------------------------------------------------- world --
    def world(self) -> dict:
        """Everything outside Barcelona: five leagues, continental and international."""
        league_rows = self.q(
            """SELECT Competition_Raw, Season, Snapshot, Season_Status, Rank, Club_Raw, Played,
                      Wins, Draws, Losses, Goals_For, Goals_Against, Goal_Difference, Points,
                      Qualification_Raw, Info_Raw
               FROM Domestic_League_Standings
               ORDER BY Competition_Raw, Season, Snapshot, CAST(Rank AS INTEGER)"""
        )

        # A league-season can carry several snapshots: a mid-season PROVISIONAL table and
        # a FINAL one. Mixing them doubles the table, so each snapshot stays its own view
        # and the final one is what the page opens on.
        snaps = defaultdict(list)
        snap_meta = {}
        for r in league_rows:
            key = f"{r['Competition_Raw']}|{r['Season']}|{r['Snapshot']}"
            snaps[key].append([
                as_int(r["Rank"]), r["Club_Raw"], maybe_int(r["Played"]), maybe_int(r["Wins"]),
                maybe_int(r["Draws"]), maybe_int(r["Losses"]), maybe_int(r["Goals_For"]),
                maybe_int(r["Goals_Against"]), maybe_int(r["Goal_Difference"]), maybe_int(r["Points"]),
                clean(r["Qualification_Raw"]) or clean(r["Info_Raw"]) or "",
            ])
            status = r["Season_Status"] or ""
            snap_meta[key] = {
                "snapshot": r["Snapshot"],
                "status": status,
                "final": status.startswith("FINAL") or "FINAL" in status,
            }

        # league|season -> the snapshots available, final first
        snapshot_index = defaultdict(list)
        for key, meta in snap_meta.items():
            league, season, snapshot = key.split("|")
            snapshot_index[f"{league}|{season}"].append({
                "key": key, "snapshot": snapshot, "status": meta["status"], "final": meta["final"],
                "teams": len(snaps[key]),
            })
        for group in snapshot_index.values():
            group.sort(key=lambda x: (not x["final"], x["snapshot"]), reverse=False)

        standings = dict(snaps)
        leagues = sorted({r["Competition_Raw"] for r in league_rows})
        seasons = sorted({r["Season"] for r in league_rows})

        # champions grid reads the adopted snapshot only, never a provisional table
        champions = {}
        for group_key, group in snapshot_index.items():
            chosen = next((g for g in group if g["final"]), group[-1])
            first = next((r for r in snaps[chosen["key"]] if r[0] == 1), None)
            if first and chosen["final"]:
                champions[group_key] = first[1]
            elif first:
                champions[group_key] = first[1] + "（暫）"

        ucl = [{"season": r["Season"], "winner": r["Winner"], "runnerUp": r["Runner_Up"]}
               for r in self.q("SELECT * FROM UCL ORDER BY Season DESC")]
        super_cup = [{"season": r["Season"], "winner": r["Winner"], "runnerUp": r["Runner_Up"]}
                     for r in self.q("SELECT * FROM UEFA_Super_Cup ORDER BY Season DESC")]
        intl = [{"tournament": r["Tournament"], "period": r["Period"], "winner": r["Winner"],
                 "runnerUp": r["Runner_Up"], "third": r["Third_Place"], "host": r["Host"]}
                for r in self.q("SELECT * FROM Intl_Tournament_Results ORDER BY Period DESC")]
        cups = [{"season": r["Season"], "competition": r["Competition"], "rank": as_int(r["Rank"]), "club": r["Club"]}
                for r in self.q("SELECT * FROM National_Tournaments WHERE Rank IN ('1','2') ORDER BY Season DESC")]
        euro_cups = [{"season": r["Season"], "competition": r["Competition_Raw"], "winner": r["Winner_Raw"],
                      "runnerUp": r["Runner_Up_Raw"], "venue": r["Final_Venue_Raw"]}
                     for r in self.q("SELECT * FROM Competition_History ORDER BY Season DESC")]
        cwc = [{"season": r["Season"] if "Season" in r else None, **{k: v for k, v in r.items() if k != "_row"}}
               for r in self.q("SELECT * FROM FIFA_Club_World_Cup_Results")]

        # club honour counts across every source that names a winner
        club_titles = Counter()
        for key, club in champions.items():
            club_titles[club] += 1
        for r in ucl:
            if r["winner"]:
                club_titles[r["winner"]] += 1

        return {
            "leagues": leagues,
            "seasons": seasons,
            "standingsCols": ["名次", "球隊", "賽", "勝", "和", "負", "進", "失", "淨", "分", "備註"],
            "standings": standings,
            "snapshots": {k: v for k, v in snapshot_index.items()},
            "champions": champions,
            "ucl": ucl,
            "superCup": super_cup,
            "intl": intl,
            "cups": cups,
            "euroCups": euro_cups,
            "cwc": cwc,
        }

    # --------------------------------------------------------------- people --
    def people(self) -> dict:
        """Every controlled player identity, and how much the archive actually knows."""
        aliases = defaultdict(set)
        canonical = {}
        for r in self.q("SELECT * FROM Player_Dim"):
            pid = r["Player_ID"]
            if not pid:
                continue
            canonical[pid] = r["Canonical_Display_Name"] or r["Alias_Name"]
            for value in (r["Canonical_Display_Name"], r["Alias_Name"]):
                if value:
                    aliases[pid].add(value)

        award_rows = self.q(
            "SELECT Player_ID, Award, Season, Rank, Club_Raw FROM Canonical_Award_Facts WHERE Player_ID IS NOT NULL"
        )
        awards = defaultdict(list)
        for r in award_rows:
            awards[r["Player_ID"]].append({
                "award": r["Award"], "season": r["Season"], "rank": as_int(r["Rank"]), "club": r["Club_Raw"],
            })

        stats = defaultdict(lambda: {"apps": 0, "goals": 0, "assists": 0, "clubs": set(), "seasons": set()})
        for r in self.q("SELECT * FROM Player_League_Career"):
            pid = r["Player_ID"]
            bucket = stats[pid]
            bucket["apps"] += as_int(r["Apps"])
            bucket["goals"] += as_int(r["Goals"])
            bucket["assists"] += as_int(r["Assists"])
            if r["Club_Raw"]:
                bucket["clubs"].add(r["Club_Raw"])
            if r["Season_Display"]:
                bucket["seasons"].add(r["Season_Display"])

        nations = {}
        for r in self.q("SELECT Player_ID, Nationality_Raw FROM Player_Profile_Snapshots WHERE Nationality_Raw IS NOT NULL"):
            nations[r["Player_ID"]] = r["Nationality_Raw"]

        barca = {p["Player_ID"] for p in self.q("SELECT DISTINCT Player_ID FROM Barcelona_Player_Career")}

        people = []
        for pid, name in sorted(canonical.items()):
            s = stats.get(pid)
            people.append({
                "id": pid,
                "name": name,
                "aliases": sorted(a for a in aliases[pid] if a != name),
                "nationality": nations.get(pid),
                "awards": awards.get(pid, []),
                "apps": s["apps"] if s else 0,
                "goals": s["goals"] if s else 0,
                "assists": s["assists"] if s else 0,
                "clubs": sorted(s["clubs"]) if s else [],
                "seasonCount": len(s["seasons"]) if s else 0,
                "barca": pid in barca,
            })
        people.sort(key=lambda p: (-len(p["awards"]), -p["apps"], p["name"]))

        clubs = [{"id": r["Club_ID"], "name": r["Canonical_Display_Name"]}
                 for r in self.q("SELECT DISTINCT Club_ID, Canonical_Display_Name FROM Club_Dim WHERE Club_ID IS NOT NULL")]

        return {
            "players": people,
            "clubs": sorted(clubs, key=lambda c: c["id"]),
            "withStats": sum(1 for p in people if p["apps"]),
            "withAwards": sum(1 for p in people if p["awards"]),
        }


    # ------------------------------------------------------------ resolution --
    def resolution(self) -> dict:
        """The unresolved-identity backlog, with candidates computed here.

        Matching needs OpenCC and the whole accepted-association index, neither
        of which belongs in a browser, so the page receives ranked candidates
        and evidence and a person makes the call.
        """
        resolver = IdentityResolver(self.con)

        rows = self.q(
            """SELECT Player_Raw, Origin_Sheet, Origin_Row, Source_ID, Reason
               FROM Award_Resolution_Status WHERE Resolution_Status='UNRESOLVED_IDENTITY'"""
        )
        context = defaultdict(lambda: {"rows": 0, "sheets": Counter(), "awards": Counter(),
                                       "seasons": set(), "clubs": Counter(), "clubIds": Counter()})
        for r in rows:
            bucket = context[r["Player_Raw"]]
            bucket["rows"] += 1
            if r["Origin_Sheet"]:
                bucket["sheets"][r["Origin_Sheet"]] += 1

        # the award facts carry the season and club that make a name decidable
        for r in self.q("SELECT Player_Raw, Award, Season, Club_Raw, Club_ID FROM Canonical_Award_Facts WHERE Player_ID IS NULL"):
            name = r["Player_Raw"]
            if name not in context:
                continue
            bucket = context[name]
            if r["Award"]:
                bucket["awards"][r["Award"]] += 1
            if r["Season"]:
                bucket["seasons"].add(r["Season"])
            if r["Club_Raw"]:
                bucket["clubs"][r["Club_Raw"]] += 1
            if r["Club_ID"]:
                bucket["clubIds"][r["Club_ID"]] += 1

        names = sorted(context)
        clusters = resolver.cluster_backlog(names)
        sibling = {}
        for group in clusters:
            if len(group) > 1:
                for name in group:
                    sibling[name] = [n for n in group if n != name]

        items = []
        for name in names:
            bucket = context[name]
            club_id = bucket["clubIds"].most_common(1)[0][0] if bucket["clubIds"] else None
            candidates = resolver.candidates(name, club_id=club_id)
            items.append({
                "raw": name,
                "rows": bucket["rows"],
                "sheets": [{"sheet": k, "n": v} for k, v in bucket["sheets"].most_common()],
                "awards": [{"award": k, "n": v} for k, v in bucket["awards"].most_common()],
                "seasons": sorted(bucket["seasons"], reverse=True),
                "clubs": [k for k, _ in bucket["clubs"].most_common(3)],
                "clubId": club_id,
                "candidates": candidates,
                "verdict": IdentityResolver.verdict(candidates),
                "siblings": sibling.get(name, []),
            })
        # heaviest first: confirming one name can clear a dozen rows
        items.sort(key=lambda x: (-x["rows"], x["raw"]))

        verdicts = Counter(i["verdict"] for i in items)
        return {
            "items": items,
            "totalRows": sum(i["rows"] for i in items),
            "totalNames": len(items),
            "verdicts": [{"verdict": k, "n": v} for k, v in verdicts.most_common()],
            "merges": [g for g in clusters if len(g) > 1],
            "controlledPlayers": len(resolver.canonical),
            "indexKeys": len(resolver.index),
        }

    # ------------------------------------------------------------ timetravel --
    def timetravel(self) -> dict:
        """The archive's own knowledge history.

        Distinct from the in-world timeline: these are the dates the archive
        LEARNED things. Because the model is append-only, every one of them is
        still reconstructible — which is the whole point of not overwriting.
        """
        date_sources = [
            ("Player_Profile_Snapshots", "Snapshot_Date", "球員檔案"),
            ("Player_Attr_Snap_O", "Snapshot_Date", "能力值快照（非門將）"),
            ("Player_Attr_Snap_G", "Snapshot_Date", "能力值快照（門將）"),
            ("Player_Career_Summaries", "Snapshot_Date", "生涯總計"),
            ("Barcelona_Squad_History", "Snapshot_Date", "巴薩陣容快照"),
            ("Domestic_League_Standings", "Snapshot", "聯賽積分榜"),
            ("Club_Cup_History", "Snapshot", "盃賽進程"),
        ]

        per_date = defaultdict(lambda: defaultdict(int))
        for table, column, label in date_sources:
            try:
                for r in self.q(f'SELECT "{column}" d, COUNT(*) n FROM "{table}" WHERE "{column}" IS NOT NULL GROUP BY 1'):
                    date = str(r["d"])[:10]
                    if re.match(r"^20\d\d-\d\d-\d\d$", date):
                        per_date[date][label] += as_int(r["n"])
            except sqlite3.OperationalError:
                continue

        # attribute movement between two snapshots, per player
        changes = defaultdict(list)
        for r in self.q("SELECT * FROM Player_Attribute_Changes"):
            changes[f'{r["From_Snapshot"]}→{r["To_Snapshot"]}'].append({
                "player": r["Player_ID"], "attr": r["Attribute_Name"],
                "old": as_int(r["Old_Value"]), "new": as_int(r["New_Value"]), "delta": as_int(r["Delta"]),
            })

        names = {p["Player_ID"]: p["Canonical_Display_Name"]
                 for p in self.q("SELECT DISTINCT Player_ID, Canonical_Display_Name FROM Player_Dim WHERE Player_ID IS NOT NULL")}

        # which players the archive knew a profile for, as of each date
        profile_dates = defaultdict(set)
        for r in self.q("SELECT Snapshot_Date, Player_ID FROM Player_Profile_Snapshots WHERE Snapshot_Date IS NOT NULL"):
            profile_dates[str(r["Snapshot_Date"])[:10]].add(r["Player_ID"])

        dates = sorted(per_date)
        known, timeline = set(), []
        for date in dates:
            new_players = profile_dates.get(date, set()) - known
            known |= profile_dates.get(date, set())
            timeline.append({
                "date": date,
                "learned": [{"label": k, "n": v} for k, v in sorted(per_date[date].items(), key=lambda x: -x[1])],
                "total": sum(per_date[date].values()),
                "newPlayers": sorted(names.get(p, p) for p in new_players),
                "knownPlayers": len(known),
            })

        return {
            "timeline": timeline,
            "changes": [{"span": k, "moves": v} for k, v in sorted(changes.items())],
            "playerNames": names,
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
        }

    # ------------------------------------------------------------ chronicle --
    def chronicle(self) -> list[dict]:
        rows = self.q("SELECT * FROM World_Timeline ORDER BY Period_ID DESC, Timeline_ID")
        return [{
            "id": r["Timeline_ID"], "period": r["Period_ID"], "season": r["Season_or_Year"],
            "type": r["Event_Type"], "fact": r["Objective_Fact"], "subject": r["Subject"],
            "sheet": r["Source_Sheet"], "status": r["Verification_Status"],
        } for r in rows]

    # -------------------------------------------------------------- clasico --
    def clasico(self) -> list[dict]:
        out = []
        for r in self.q("SELECT * FROM El_Clasico_Match_History ORDER BY Date"):
            home_is_barca = "巴塞" in (r["Home_Club_Raw"] or "")
            goals = re.match(r"(\d+)\s*[-:]\s*(\d+)", (r["Result_Raw"] or "").strip())
            verdict = None
            if goals:
                hg, ag = int(goals.group(1)), int(goals.group(2))
                barca, rival = (hg, ag) if home_is_barca else (ag, hg)
                verdict = "W" if barca > rival else "L" if barca < rival else "D"
            out.append({
                "date": r["Date"], "competition": r["Competition_Raw"], "home": r["Home_Club_Raw"],
                "away": r["Away_Club_Raw"], "result": r["Result_Raw"], "verdict": verdict,
                "homeIsBarca": home_is_barca,
            })
        return out

    # -------------------------------------------------------------- quality --
    def integrity(self) -> dict:
        domains = Counter(r["Domain"] for r in self.q("SELECT Domain FROM Data_Issues") if r["Domain"])
        resolution = Counter(r["Resolution_Status"] for r in self.q("SELECT Resolution_Status FROM Award_Resolution_Status"))

        unresolved_awards = as_int(self.one("SELECT COUNT(*) n FROM Canonical_Award_Facts WHERE Player_ID IS NULL")["n"])
        total_awards = as_int(self.one("SELECT COUNT(*) n FROM Canonical_Award_Facts")["n"])

        top_unresolved = self.q(
            """SELECT Player_Raw, COUNT(*) n, GROUP_CONCAT(DISTINCT Origin_Sheet) sheets
               FROM Award_Resolution_Status WHERE Resolution_Status='UNRESOLVED_IDENTITY'
               GROUP BY Player_Raw ORDER BY n DESC LIMIT 25"""
        )

        # Findings the ETL can prove from the data itself, rather than a hand-kept list.
        findings = []

        dupes = self.q(
            """SELECT Player_ID, COUNT(DISTINCT Season_Display) variants, GROUP_CONCAT(DISTINCT Season_Display) labels
               FROM Player_Club_Season_Totals
               WHERE Season_ID='PER-S-2034-35' GROUP BY Player_ID HAVING variants > 1"""
        )
        if dupes:
            findings.append({
                "severity": "high",
                "title": "2034/35 同一球員存在兩筆賽季總計",
                "detail": f"{len(dupes)} 名球員在 PER-S-2034-35 下同時有 '2034/35' 與 '2034-35' 兩種 Season_Display，"
                          "且 Club_Raw 分別寫成「巴塞隆納」與「巴塞罗那」。任何 SUM 都會重複計算。",
                "where": "Player_Club_Season_Totals",
                "sample": [d["Player_ID"] for d in dupes[:8]],
            })

        directions = Counter(r["Direction"] for r in self.q("SELECT Direction FROM Barcelona_Transfers"))
        if len({d for d in directions if d in ("IN", "轉入")}) > 1 or len({d for d in directions if d in ("OUT", "轉出")}) > 1:
            findings.append({
                "severity": "medium",
                "title": "轉會方向欄位混用中英文編碼",
                "detail": "Direction 同時出現 " + "、".join(f"{k}（{v}）" for k, v in directions.most_common())
                          + "。以字串比對過濾轉入／轉出的查詢會漏掉一半資料。",
                "where": "Barcelona_Transfers",
                "sample": list(directions),
            })

        clubs = Counter()
        for r in self.q("SELECT Club_Raw FROM Player_Club_Season_Totals WHERE Club_ID=?", BARCELONA_CLUB_ID):
            if r["Club_Raw"]:
                clubs[r["Club_Raw"]] += 1
        if len(clubs) > 1:
            findings.append({
                "severity": "low",
                "title": "同一 Club_ID 對應多種原始寫法",
                "detail": f"C-0030 的 Club_Raw 有 {len(clubs)} 種寫法："
                          + "、".join(f"{k}（{v}）" for k, v in clubs.most_common()) + "。Club_ID 已正確收斂，原始字串保留無誤，僅提醒不要直接以 Club_Raw 分組。",
                "where": "Player_Club_Season_Totals",
                "sample": list(clubs),
            })

        multi_snap = self.q(
            """SELECT Competition_Raw, Season, COUNT(DISTINCT Snapshot) n
               FROM Domestic_League_Standings GROUP BY 1,2 HAVING n > 1"""
        )
        if multi_snap:
            findings.append({
                "severity": "high",
                "title": "聯賽積分榜同賽季存在多份快照",
                "detail": f"{len(multi_snap)} 個聯賽賽季同時有 PROVISIONAL（賽季中）與 FINAL（賽季末）兩份積分榜。"
                          "不看 Season_Status 直接查詢會得到兩倍的隊伍數與錯誤的冠軍。本站已只採 FINAL 快照。",
                "where": "Domestic_League_Standings",
                "sample": [f"{r['Competition_Raw']} {r['Season']}" for r in multi_snap[:6]],
            })

        null_strings = as_int(self.one(
            "SELECT COUNT(*) n FROM Domestic_League_Standings WHERE Qualification_Raw='NULL' OR Info_Raw='NULL'")["n"])
        if null_strings:
            findings.append({
                "severity": "medium",
                "title": "資格欄位以字串 'NULL' 表示空值",
                "detail": f"{null_strings} 列的 Qualification_Raw／Info_Raw 內容是四個字元的字串 'NULL'，不是真正的空值。"
                          "任何 IS NULL 判斷都會漏掉這些列。本站顯示時視為空白，來源值未更動。",
                "where": "Domestic_League_Standings",
                "sample": ["NULL", "!"],
            })

        missing_gf = [s["Season"] for s in self.q("SELECT Season, LaLiga_GF FROM Barcelona_Season_Master WHERE LaLiga_GF IS NULL")]
        if missing_gf:
            findings.append({
                "severity": "low",
                "title": "賽季主表存在來源未提供的空值",
                "detail": f"{'、'.join(missing_gf)} 的西甲進球／失球未填。依 append-only 政策保持未知而非補 0，屬正確處理，列此僅供追蹤補資料。",
                "where": "Barcelona_Season_Master",
                "sample": missing_gf,
            })

        order = {"high": 0, "medium": 1, "low": 2}
        findings.sort(key=lambda f: order.get(f["severity"], 3))

        return {
            "issueTotal": sum(domains.values()),
            "domains": [{"domain": k, "count": v} for k, v in domains.most_common()],
            "resolution": [{"status": k, "count": v} for k, v in resolution.most_common()],
            "unresolvedAwards": unresolved_awards,
            "totalAwards": total_awards,
            "topUnresolved": [{"name": r["Player_Raw"], "count": as_int(r["n"]), "sheets": r["sheets"]} for r in top_unresolved],
            "findings": findings,
        }

    # -------------------------------------------------------------- honours --
    def honours(self) -> dict:
        ballon = self.q("SELECT * FROM Ballon_dOr ORDER BY Season DESC, CAST(Rank AS INTEGER)")
        by_season = defaultdict(list)
        for r in ballon:
            by_season[r["Season"]].append({
                "rank": as_int(r["Rank"]), "player": r["Player"], "club": r["Club"], "position": r["Position"],
                "apps": as_int(r["Appearances"]), "goals": as_int(r["Goals"]), "assists": as_int(r["Assists"]),
                "rating": num(r["Average_Rating"]),
            })
        awards = self.q("SELECT Award, COUNT(*) n FROM Canonical_Award_Facts GROUP BY 1 ORDER BY n DESC")

        winners = defaultdict(list)
        for r in self.q(
            """SELECT Award, Season, Player_Raw, Player_ID, Club_Raw, Identity_Status
               FROM Canonical_Award_Facts WHERE Rank='1' ORDER BY Award, Season DESC"""
        ):
            winners[r["Award"]].append({
                "season": r["Season"], "player": r["Player_Raw"], "id": r["Player_ID"],
                "club": r["Club_Raw"], "resolved": bool(r["Player_ID"]),
            })

        records = [{"type": r["Record_Type"], "season": r["Season"], "who": r["Player_or_Entity"],
                    "context": r["Club_or_Context"], "sheet": r["Origin_Sheet"]}
                   for r in self.q("SELECT * FROM Historical_Records ORDER BY Season DESC")]

        return {
            "ballonDor": [{"season": k, "podium": v} for k, v in by_season.items()],
            "awardCatalogue": [{"award": r["Award"], "count": as_int(r["n"])} for r in awards],
            "winners": winners,
            "records": records,
        }


def build(db_path: Path, out_path: Path, template_path: Path) -> None:
    archive = Archive(db_path)
    payload = {
        "meta": archive.meta(),
        "world": archive.world(),
        "resolution": archive.resolution(),
        "timetravel": archive.timetravel(),
        "people": archive.people(),
        "seasons": archive.seasons(),
        "players": archive.players(),
        "chronicle": archive.chronicle(),
        "clasico": archive.clasico(),
        "integrity": archive.integrity(),
        "honours": archive.honours(),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = template_path.read_text(encoding="utf-8").replace('"__ARCHIVE_DATA__"', data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html) / 1024:.0f} KB, payload {len(data) / 1024:.0f} KB)")
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"  {key:<12} {len(value)}")


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--database", type=Path, default=here / "data" / "fm24.sqlite")
    ap.add_argument("-o", "--output", type=Path, default=here / "dist" / "index.html")
    ap.add_argument("-t", "--template", type=Path, default=here / "template.html")
    args = ap.parse_args()
    build(args.database, args.output, args.template)


if __name__ == "__main__":
    main()
