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
import sys
from collections import Counter, defaultdict
from pathlib import Path
from data_rules import collective_host, host_parts, snapshot_order, snapshot_state, transfer_direction

from resolver import (CATEGORY_LABELS, COMPETITION_REFERENCE_COLUMNS, SCRIPT_CONVERSION_AVAILABLE,
                      LEAGUE_LABELS, ClubResolver, CompetitionResolver, IdentityResolver,
                      club_key, competition_category, is_truncated, league_key, normalise,
                      discover_club_columns, discover_competition_columns, require_script_conversion,
                      sheet_league, start_year, strip_stage, tier_signature)

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
    """The source transcription writes a literal 'NULL' string for absent cells.

    '!' is NOT one of them. All 117 rows carrying it sit in the bottom three
    places of their table and nowhere else, in the same band the source
    elsewhere spells out as 降级 — it is the relegation marker, and discarding
    it as noise silently deleted that fact from every one of those rows.
    """
    if value is None:
        return None
    text = str(value).strip()
    return None if text in ("", "NULL", "null") else text


def norm_name(value: str | None) -> str:
    """Strip the separators that differ between Discord sources (・ vs ·)."""
    if not value:
        return ""
    return re.sub(r"[·・.\s]", "", str(value))


class Archive:
    def __init__(self, db_path: Path, *, allow_degraded: bool = False):
        self.script_conversion = require_script_conversion(allow_degraded)
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = sqlite3.Row
        self._column_cache: dict[str, set[str]] = {}

    def q(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, args)]

    def one(self, sql: str, *args):
        rows = self.q(sql, *args)
        return rows[0] if rows else None

    def columns(self, table: str) -> set[str]:
        """Column names of a table, or an empty set if the table is absent."""
        if table not in self._column_cache:
            try:
                self._column_cache[table] = {r[1] for r in self.con.execute(f'PRAGMA table_info("{table}")')}
            except sqlite3.OperationalError:
                self._column_cache[table] = set()
        return self._column_cache[table]

    def has(self, table: str, *columns: str) -> bool:
        """Guard every dynamically-built column reference with this.

        SQLite resolves a double-quoted identifier that matches no column as a
        STRING LITERAL rather than raising, so `SELECT "Competition_Raw" FROM t`
        on a table without that column silently returns the text
        "Competition_Raw" once per row. A survey built on that pattern invents
        data that looks entirely real.
        """
        available = self.columns(table)
        return bool(available) and all(c in available for c in columns)

    # ---------------------------------------------------------------- meta --
    def meta(self) -> dict:
        sheets = self.q("SELECT sheet_name, table_name, row_count FROM _sheets ORDER BY row_count DESC")
        schema = self.one("SELECT * FROM Workbook_Schema_Metadata") or {}
        return {
            "generated": dt.date.today().isoformat(),
            "scriptConversion": self.script_conversion,
            "degraded": not self.script_conversion,
            "buildWarnings": [] if self.script_conversion else ["簡繁轉換不可用，身分與覆蓋率不可和完整建置比較。"],
            "sheet_count": len(sheets),
            "row_count": sum(s["row_count"] for s in sheets),
            "schema_version": schema.get("Workbook_Schema_Version", "—"),
            "migration_id": schema.get("Migration_ID", "—"),
            "biggest_sheets": sheets[:8],
            "player_count": as_int(self.one("SELECT COUNT(DISTINCT Player_ID) n FROM Player_Dim")["n"]),
            "alias_count": as_int(self.one("SELECT COUNT(*) n FROM Player_Dim")["n"]),
            "club_count": as_int(self.one("SELECT COUNT(DISTINCT Club_ID) n FROM Club_Dim")["n"]),
            "nation_count": len({r['National_Team_ID'] for r in self.q('SELECT * FROM Nation_Dim')
                                 if not collective_host(r['Canonical_Display_Name'])}),
            "nation_dimension_count": as_int(self.one("SELECT COUNT(DISTINCT National_Team_ID) n FROM Nation_Dim")["n"]),
            "identity_links": as_int(self.one("SELECT COUNT(*) n FROM Record_Identity_Map")["n"]),
        }

    # ------------------------------------------------------------- seasons --
    def seasons(self) -> list[dict]:
        transfers = defaultdict(lambda: {"in": [], "out": [], "unknown": []})
        for row in self.q("SELECT * FROM Barcelona_Transfers"):
            bucket = transfer_direction(row['Direction']) or 'unknown'
            transfers[row["Season"]][bucket].append(
                {"player": row["Player"], "club": row["Counterparty_Club"], "fee": row["Fee_Display"], "date": row["Date_Display"],
                 "directionRaw": row['Direction'], "row": row['_row']}
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
                "transfersUnknown": transfers[season]['unknown'],
                "leaders": leaders[season],
                "ballonDor": {"player": bdo["Player"], "club": bdo["Club"]} if bdo else None,
            })
        return out

    # ------------------------------------------------------------- players --
    def players(self) -> list[dict]:
        profiles = {}
        for row in self.q("SELECT * FROM Player_Profile_Snapshots ORDER BY Snapshot_Date"):
            profiles[row["Player_ID"]] = row

        # The workbook states which observation is authoritative for a season in
        # Statistical_Adoption_Status. Plotting the superseded row alongside the
        # adopted one puts two different seasons on the chart and contradicts the
        # career total printed on the same page, which counts only the adopted.
        season_stats = defaultdict(list)
        superseded = defaultdict(list)
        for row in self.q(
            "SELECT * FROM Player_Club_Season_Totals WHERE Club_ID=? ORDER BY Season_ID", BARCELONA_CLUB_ID
        ):
            adoption = row["Statistical_Adoption_Status"] or "UNKNOWN_NOT_ADOPTED"
            record = {
                "season": row["Season_Display"], "apps": maybe_int(row["Apps"]), "goals": maybe_int(row["Goals"]),
                "assists": maybe_int(row["Assists"]), "motm": maybe_int(row["POTM"]), "rating": num(row["Rating"]),
                "source": row["Source_ID"], "status": row["Verification_Status"],
                "adoption": adoption, "adoptionNote": row["Adoption_Note"],
                "instance": row["Source_Instance_ID"],
            }
            (season_stats if adoption == "ADOPTED" else superseded)[row["Player_ID"]].append(record)

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
                "scope": row["Scope"], "level": row['Team_Level'], "country": row["Country_Raw"], "apps": maybe_int(row["Apps"]),
                "goals": maybe_int(row["Goals"]), "assists": maybe_int(row["Assists"]),
                "date": row['Snapshot_Date'],
                "evidence": dict(sheet='Player_Career_Summaries', row=row['_row'], source=row.get('Source_ID'), status=row.get('Verification_Status')),
            })

        out = []
        for row in self.q("SELECT * FROM Barcelona_Player_Career"):
            pid = row["Player_ID"]
            profile = profiles.get(pid, {})
            awards = [a.strip() for a in (row["Major_Awards"] or "").split("；") if a.strip() and not a.strip().startswith('無已確認')]
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
                "supersededStats": superseded.get(pid, []),
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
        snap_statuses = defaultdict(set)
        for r in league_rows:
            key = f"{r['Competition_Raw']}|{r['Season']}|{r['Snapshot']}"
            snaps[key].append([
                as_int(r["Rank"]), r["Club_Raw"], maybe_int(r["Played"]), maybe_int(r["Wins"]),
                maybe_int(r["Draws"]), maybe_int(r["Losses"]), maybe_int(r["Goals_For"]),
                maybe_int(r["Goals_Against"]), maybe_int(r["Goal_Difference"]), maybe_int(r["Points"]),
                clean(r["Qualification_Raw"]) or clean(r["Info_Raw"]) or "",
            ])
            status = r["Season_Status"] or ""
            snap_statuses[key].add(status)
            state = snapshot_state(snap_statuses[key])
            snap_meta[key] = {
                "snapshot": r["Snapshot"],
                "status": ' / '.join(sorted(snap_statuses[key])) or None,
                "state": state,
                "final": state == 'final',
            }

        # league|season -> the snapshots available, final first
        snapshot_index = defaultdict(list)
        for key, meta in snap_meta.items():
            league, season, snapshot = key.split("|")
            snapshot_index[f"{league}|{season}"].append({
                "key": key, "snapshot": snapshot, "status": meta["status"], "final": meta["final"],
                "state": meta['state'],
                "teams": len(snaps[key]),
            })
        for group in snapshot_index.values():
            group.sort(key=snapshot_order, reverse=True)

        standings = dict(snaps)
        leagues = sorted({r["Competition_Raw"] for r in league_rows})
        seasons = sorted({r["Season"] for r in league_rows})

        # Champions confirmed by another table in the workbook. A standings
        # snapshot without a FINAL marker does not make an already-recorded title
        # provisional — those are two different questions.
        confirmed = set()
        club_res = ClubResolver(self.con)
        from evidence import Periods
        periods = Periods(self.q('SELECT * FROM Period_Dim'))
        def champion_key(competition, season, club):
            # Exact controlled aliases first. Corporate suffixes are comparison
            # keys only: this never merges or rewrites Club_IDs.
            cid = club_res.resolve(club)
            name = club_res.canonical.get(cid, club)
            return league_key(competition), periods.resolve(season) or season, club_key(name)
        for table, competition_col, season_col, club_col, rank_col in (
            ("Domestic_Leagues", "Competition", "Season", "Club", "Rank"),
        ):
            if not self.has(table, competition_col, season_col, club_col, rank_col):
                continue
            for r in self.q(f'SELECT "{competition_col}" c, "{season_col}" s, "{club_col}" k '
                            f'FROM "{table}" WHERE "{rank_col}"=?', "1"):
                key = league_key(r["c"])
                if key and r["s"]:
                    confirmed.add(champion_key(r['c'], r['s'], r['k']))

        champions = {}
        for group_key, group in snapshot_index.items():
            league_name, season = group_key.split("|")
            chosen = group[0]
            first = next((r for r in snaps[chosen["key"]] if r[0] == 1), None)
            if not first:
                continue
            elsewhere = champion_key(league_name, season, first[1]) in confirmed
            champions[group_key] = {
                "club": first[1],
                "final": chosen["final"],
                "confirmedElsewhere": elsewhere,
                "snapshot": chosen["snapshot"],
                "state": chosen['state'],
            }

        club_res = ClubResolver(self.con)

        def club_identity(raw):
            """Resolve to a Club_ID so two spellings of one club count once."""
            if not raw:
                return None, None
            cid = club_res.resolve(raw)
            if not cid:
                hits = club_res.stripped.get(club_key(raw), set())
                cid = next(iter(hits)) if len(hits) == 1 else None
            return cid, (club_res.canonical.get(cid) if cid else None)

        ucl = []
        ucl_titles = Counter()
        ucl_names = {}
        for r in self.q("SELECT * FROM UCL ORDER BY Season DESC"):
            cid, canonical = club_identity(r["Winner"])
            ucl.append({"season": r["Season"], "winner": r["Winner"], "runnerUp": r["Runner_Up"],
                        "winnerId": cid, "winnerCanonical": canonical})
            if r["Winner"]:
                key = cid or ("raw:" + str(r["Winner"]))
                ucl_titles[key] += 1
                ucl_names.setdefault(key, canonical or r["Winner"])
        super_cup = [{"season": r["Season"], "winner": r["Winner"], "runnerUp": r["Runner_Up"]}
                     for r in self.q("SELECT * FROM UEFA_Super_Cup ORDER BY Season DESC")]
        intl = [{"tournament": r["Tournament"], "period": r["Period"], "winner": r["Winner"],
                 "runnerUp": r["Runner_Up"], "third": r["Third_Place"], "host": host_parts(r['Host'])[0],
                 "venue": host_parts(r['Host'])[1], "hostRaw": r['Host']}
                for r in self.q("SELECT * FROM Intl_Tournament_Results ORDER BY Period DESC")]
        cups = [{"season": r["Season"], "competition": r["Competition"], "rank": as_int(r["Rank"]), "club": r["Club"]}
                for r in self.q("SELECT * FROM National_Tournaments WHERE Rank IN ('1','2') ORDER BY Season DESC")]
        euro_cups = [{"season": r["Season"], "competition": r["Competition_Raw"], "winner": r["Winner_Raw"],
                      "runnerUp": r["Runner_Up_Raw"], "venue": r["Final_Venue_Raw"]}
                     for r in self.q("SELECT * FROM Competition_History ORDER BY Season DESC")]
        cwc = [{"season": r["Season"] if "Season" in r else None, **{k: v for k, v in r.items() if k != "_row"}}
               for r in self.q("SELECT * FROM FIFA_Club_World_Cup_Results")]

        return {
            "uclTitles": [{"id": None if k.startswith("raw:") else k,
                           "name": ucl_names[k], "titles": v,
                           "resolved": not k.startswith("raw:")}
                          for k, v in ucl_titles.most_common()],
            "leagues": leagues,
            "seasons": seasons,
            "standingsCols": ["名次", "球隊", "賽", "勝", "和", "負", "進", "失", "淨", "分", "備註"],
            "standings": standings,
            "standingRows": len(league_rows),
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
                                       "seasons": set(), "clubs": Counter(), "clubIds": Counter(),
                                       "leagues": Counter(), "years": []})
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
                for key in resolver.club_leagues.get(r["Club_ID"], ()):
                    bucket["leagues"][key] += 1
            year = start_year(r["Season"])
            if year:
                bucket["years"].append(year)

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
            # the club the award names is a better league signal than the sheet,
            # because cross-league awards live on sheets that name no league
            league = (bucket["leagues"].most_common(1)[0][0] if bucket["leagues"]
                      else next((k for k in (sheet_league(s["sheet"]) for s in
                                             [{"sheet": x} for x, _ in bucket["sheets"].most_common()]) if k), None))
            season_year = max(bucket["years"]) if bucket["years"] else None
            candidates = resolver.candidates(name, club_id=club_id, league=league, season_year=season_year)
            items.append({
                "raw": name,
                "rows": bucket["rows"],
                "league": LEAGUE_LABELS.get(league) if league else None,
                "seasonYear": season_year,
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


    # ----------------------------------------------------------------- clubs --
    def clubs(self) -> dict:
        """Club references that carry no Club_ID, and identities recorded twice."""
        resolver = ClubResolver(self.con)

        # Discovered rather than hand-listed: a curated allowlist missed 54 of the
        # columns actually holding club names, every league award sheet included.
        reference_columns = discover_club_columns(self.con)
        refs = defaultdict(lambda: {"rows": 0, "tables": Counter(), "leagues": Counter(),
                                    "seasons": set()})
        for table, column in reference_columns:
            if not self.has(table, column):
                continue
            has_season = self.has(table, "Season")
            season_col = ", Season" if has_season else ""
            rows = self.q(f'SELECT "{column}" v{season_col} FROM "{table}" WHERE "{column}" IS NOT NULL')
            for r in rows:
                name = clean(r['v'])
                if not name:
                    continue
                bucket = refs[name]
                bucket["rows"] += 1
                bucket["tables"][table] += 1
                if has_season and r.get("Season"):
                    bucket["seasons"].add(str(r["Season"]))

        # the standings are the one place a reference states its own league
        for r in self.q("SELECT Club_Raw, Competition_Raw FROM Domestic_League_Standings WHERE Club_Raw IS NOT NULL"):
            key = league_key(r["Competition_Raw"])
            name = str(r["Club_Raw"]).strip()
            if key and name in refs:
                refs[name]["leagues"][key] += 1

        unresolved, resolved_rows = [], 0
        for name, bucket in refs.items():
            if resolver.resolve(name):
                resolved_rows += bucket["rows"]
                continue
            league = bucket["leagues"].most_common(1)[0][0] if bucket["leagues"] else None
            candidates = resolver.candidates(name, league=league)
            unresolved.append({
                "raw": name,
                "rows": bucket["rows"],
                "tables": [{"table": k, "n": v} for k, v in bucket["tables"].most_common()],
                "league": LEAGUE_LABELS.get(league) if league else None,
                "seasons": sorted(bucket["seasons"], reverse=True)[:4],
                "truncated": is_truncated(name),
                "candidates": candidates,
                "verdict": IdentityResolver.verdict(candidates),
            })
        unresolved.sort(key=lambda x: (-x["rows"], x["raw"]))

        # duplicate identities, with the weight of data sitting on each side
        duplicates = []
        for dupe in resolver.duplicates():
            members = []
            for cid in dupe["ids"]:
                used = Counter()
                for table in sorted({t for t, _ in reference_columns}):
                    if not self.has(table, "Club_ID"):
                        continue
                    n = as_int(self.one(f'SELECT COUNT(*) n FROM "{table}" WHERE Club_ID=?', cid)["n"])
                    if n:
                        used[table] = n
                members.append({
                    "id": cid,
                    "name": resolver.canonical.get(cid, cid),
                    "rows": sum(used.values()),
                    "tables": [{"table": k, "n": v} for k, v in used.most_common()],
                    "leagues": sorted(LEAGUE_LABELS.get(k, k) for k in resolver.club_leagues.get(cid, ())),
                })
            members.sort(key=lambda m: -m["rows"])
            duplicates.append({
                "key": dupe["key"],
                "members": members,
                "bothCarryData": sum(1 for m in members if m["rows"]) > 1,
            })
        duplicates.sort(key=lambda d: (not d["bothCarryData"], -sum(m["rows"] for m in d["members"])))

        verdicts = Counter(u["verdict"] for u in unresolved)
        return {
            "unresolved": unresolved,
            "duplicates": duplicates,
            "totalRefs": len(refs),
            "resolvedRefs": len(refs) - len(unresolved),
            "unresolvedRows": sum(u["rows"] for u in unresolved),
            "resolvedRows": resolved_rows,
            "controlled": len(resolver.canonical),
            "referenceColumns": len(reference_columns),
            "verdicts": [{"verdict": k, "n": v} for k, v in verdicts.most_common()],
        }

    # ---------------------------------------------------------- competitions --
    def competitions(self) -> dict:
        """Competition references, split from the stat categories they share a column with."""
        resolver = CompetitionResolver(self.con)

        refs = defaultdict(lambda: {"rows": 0, "tables": Counter()})
        categories = defaultdict(lambda: {"rows": 0, "tables": Counter()})
        for table, column in discover_competition_columns(self.con):
            if not self.has(table, column):
                continue
            for r in self.q(f'SELECT "{column}" v, COUNT(*) n FROM "{table}" WHERE "{column}" IS NOT NULL GROUP BY 1'):
                name = clean(r['v'])
                if not name or name == "-":
                    continue
                bucket = categories if competition_category(name) else refs
                bucket[name]["rows"] += as_int(r["n"])
                bucket[name]["tables"][table] += as_int(r["n"])

        unresolved = []
        for name, bucket in refs.items():
            if resolver.resolve(name):
                continue
            candidates = resolver.candidates(name)
            unresolved.append({
                "raw": name,
                "rows": bucket["rows"],
                "tables": [{"table": k, "n": v} for k, v in bucket["tables"].most_common()],
                "tier": list(tier_signature(strip_stage(name))),
                "candidates": candidates,
                "verdict": IdentityResolver.verdict(candidates),
            })
        unresolved.sort(key=lambda x: (-x["rows"], x["raw"]))

        by_name = {u["raw"]: u for u in unresolved}
        clusters = []
        for group in resolver.cluster([u["raw"] for u in unresolved]):
            if len(group) < 2:
                continue
            members = sorted((by_name[n] for n in group), key=lambda m: -m["rows"])
            clusters.append({
                "members": [{"raw": m["raw"], "rows": m["rows"]} for m in members],
                "rows": sum(m["rows"] for m in members),
                "suggested": members[0]["raw"],
            })
        clusters.sort(key=lambda c: -c["rows"])

        # the same four categories are recorded in two languages
        grouped = defaultdict(lambda: {"rows": 0, "spellings": []})
        for name, bucket in categories.items():
            key = competition_category(name)
            grouped[key]["rows"] += bucket["rows"]
            grouped[key]["spellings"].append({"raw": name, "rows": bucket["rows"]})
        category_report = [{
            "category": key,
            "label": CATEGORY_LABELS.get(key, key),
            "rows": value["rows"],
            "spellings": sorted(value["spellings"], key=lambda s: -s["rows"]),
        } for key, value in sorted(grouped.items(), key=lambda kv: -kv[1]["rows"])]

        verdicts = Counter(u["verdict"] for u in unresolved)
        return {
            "unresolved": unresolved,
            "clusters": clusters,
            "categories": category_report,
            "categoryRows": sum(c["rows"] for c in category_report),
            "controlled": len(resolver.canonical),
            "totalRefs": len(refs),
            "unresolvedRows": sum(u["rows"] for u in unresolved),
            "verdicts": [{"verdict": k, "n": v} for k, v in verdicts.most_common()],
        }

    # --------------------------------------------------------------- sources --
    def sources(self) -> dict:
        """The source registry, and the period map every sheet's dates fold into.

        Local_Path is deliberately omitted: it names a directory on whoever
        assembled the workbook, which is of no use to a reader and should not be
        published.
        """
        entries = []
        by_domain = Counter()
        for r in self.q("SELECT * FROM Source_Index ORDER BY Source_ID"):
            domain = clean(r["Domain"]) or "未分類"
            by_domain[domain] += 1
            entries.append({
                "id": r["Source_ID"],
                "file": clean(r["File_Name"]),
                "domain": domain,
                "season": clean(r["Season_Context"]),
                "note": clean(r["Source_Note"]),
            })

        # how many facts each source is cited by, so a reader can see its weight
        cited = Counter()
        for table in ("Canonical_Award_Facts", "Player_Club_Season_Totals",
                      "Domestic_League_Standings", "World_Timeline", "El_Clasico_Match_History"):
            if not self.has(table, "Source_ID"):
                continue
            for r in self.q(f'SELECT Source_ID, COUNT(*) n FROM "{table}" '
                            f'WHERE Source_ID IS NOT NULL GROUP BY 1'):
                cited[r["Source_ID"]] += as_int(r["n"])
        for entry in entries:
            entry["citedBy"] = cited.get(entry["id"], 0)

        periods, variants = [], defaultdict(set)
        for r in self.q("SELECT * FROM Period_Dim ORDER BY Period_ID"):
            pid = r["Period_ID"]
            periods.append({
                "id": pid,
                "display": clean(r["Canonical_Period_Display"]) or clean(r["Source_Period_Display"]),
                "sourceDisplay": clean(r["Source_Period_Display"]),
                "type": clean(r["Period_Type"]),
                "start": maybe_int(r["Start_Year"]),
                "end": maybe_int(r["End_Year"]),
                "status": clean(r["Verification_Status"]),
            })
            for value in (r["Source_Period_Display"], r["Canonical_Period_Display"]):
                if clean(value):
                    variants[pid].add(clean(value))

        # one canonical period can be written several ways; that is the whole
        # point of the table, and a reader should be able to see the mapping
        merged = [{"id": pid, "spellings": sorted(v)} for pid, v in variants.items() if len(v) > 1]

        orphan_sources = sum(1 for e in entries if not e["citedBy"])
        return {
            "sources": entries,
            "domains": [{"domain": k, "n": v} for k, v in by_domain.most_common()],
            "periods": periods,
            "mergedPeriods": sorted(merged, key=lambda m: m["id"]),
            "orphanSources": orphan_sources,
            "citedSources": len(entries) - orphan_sources,
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
            if not self.has(table, column):
                continue
            for r in self.q(f'SELECT "{column}" d, COUNT(*) n FROM "{table}" WHERE "{column}" IS NOT NULL GROUP BY 1'):
                date = str(r["d"])[:10]
                if re.match(r"^20\d\d-\d\d-\d\d$", date):
                    per_date[date][label] += as_int(r["n"])

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
        from evidence import Periods
        periods = Periods(self.q('SELECT * FROM Period_Dim'))
        def order(r):
            p = periods.by_id.get(r['Period_ID'], {})
            year = re.search(r'\d{4}', r['Season_or_Year'] or '')
            return (p.get('start') or (int(year[0]) if year else 0), p.get('end') or 0, r['Timeline_ID'] or '')
        rows.sort(key=order, reverse=True)
        return [{
            "id": r["Timeline_ID"], "period": r["Period_ID"], "season": r["Season_or_Year"],
            "type": r["Event_Type"], "fact": r["Objective_Fact"], "subject": r["Subject"],
            "sheet": r["Source_Sheet"], "status": r["Verification_Status"],
        } for r in rows]

    # -------------------------------------------------------------- clasico --
    def clasico(self) -> list[dict]:
        """Every recorded meeting, with the result read as the source wrote it.

        The source prefixes a result decided in extra time with 加 and one
        decided on penalties with 点. A parser that only accepts a leading digit
        silently drops those, which is how a 46-match record summed to 43.

        A penalty shoot-out is recorded as the draw it was: who advanced is not
        stated, and this does not guess.
        """
        DECIDER = {"加": "aet", "延": "aet", "点": "pens", "點": "pens"}

        out, undated = [], []
        for r in self.q("SELECT * FROM El_Clasico_Match_History"):
            raw = (r["Result_Raw"] or "").strip()
            decider = None
            for token, kind in DECIDER.items():
                if raw.startswith(token):
                    decider = kind
                    raw = raw[len(token):].strip()
                    break
                if raw.endswith(token):
                    decider = kind
                    raw = raw[:-len(token)].strip()
                    break

            home_is_barca = "巴塞" in (r["Home_Club_Raw"] or "")
            goals = re.match(r"(\d+)\s*[-:：]\s*(\d+)", raw)
            verdict = None
            if goals:
                hg, ag = int(goals.group(1)), int(goals.group(2))
                barca, rival = (hg, ag) if home_is_barca else (ag, hg)
                verdict = "W" if barca > rival else "L" if barca < rival else "D"

            match = {
                "date": r["Date"], "competition": r["Competition_Raw"],
                "home": r["Home_Club_Raw"], "away": r["Away_Club_Raw"],
                "result": r["Result_Raw"], "score": raw or None, "verdict": verdict,
                "decider": decider, "homeIsBarca": home_is_barca,
                "source": {"source": r.get('Source_ID'), "sheet": 'El_Clasico_Match_History',
                           "row": r['_row'], "status": r.get('Verification_Status')},
            }
            (out if r["Date"] else undated).append(match)

        out.sort(key=lambda m: m["date"])
        return out + undated

    # -------------------------------------------------------------- quality --
    def integrity(self) -> dict:
        from integrity import report
        return report(self)

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


# The Artifact platform wraps the published fragment in its own document
# skeleton. A file opened from file:// gets no such wrapper, and without an
# explicit charset the browser guesses — which turns every Chinese character in
# the page into mojibake — so a standalone build supplies the skeleton itself.
STANDALONE_SKELETON = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
  :root {{ color-scheme: light dark; padding-top: env(safe-area-inset-top, 0px);
           padding-bottom: env(safe-area-inset-bottom, 0px); }}
  html, body {{ margin: 0; }}
  body {{ font: 14px system-ui, sans-serif; }}
  img {{ max-width: 100%; }}
  [hidden] {{ display: none !important; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def export_json(db_path: Path, out_path: Path, *, allow_degraded: bool = False) -> None:
    """Dump the payload on its own, for handing to something that reads data.

    The site embeds this same structure inside a megabyte of page, which is the
    wrong shape for another program (or another model) to read: it has to get
    through the viewer to reach the archive. This writes the archive alone.
    """
    payload = collect(Archive(db_path, allow_degraded=allow_degraded))
    payload["_readme"] = {
        "source": "FM24 World Master workbook, mirrored to SQLite then derived",
        "generated": payload["meta"]["generated"],
        "note": "數值依既有頁面口徑衍生；新增來源核對欄位保留原文與 null。"
                "identity/club/competition 區塊是待解析的積欠，不是已確認事實。",
        "sections": {
            "meta": "工作簿規模與結構版本",
            "world": "五大聯賽積分榜、歐冠與國際賽冠軍",
            "people": "受控球員身分與其正式獎項紀錄（含名次及入選）",
            "seasons": "巴塞隆納 12 季主表",
            "players": "巴塞隆納球員生涯與能力值",
            "chronicle": "工作簿的世界史事件",
            "sources": "來源名冊、期間別名與未能唯一關聯的來源證據",
            "history": "國際賽程、俱樂部歷史對照與退役檔案；保留來源範圍，不另累計",
            "reference": "24 張 P1/P2 工作表全部 707 列與原始欄位、來源列號及採用限制",
            "honours": "金球獎與各獎項歷屆得主",
            "resolution": "球員身分積欠與候選",
            "clubs": "俱樂部身分積欠與重複身分",
            "competitions": "賽事身分積欠與同賽事異寫",
            "timetravel": "檔案認知史：哪一天知道了什麼",
            "integrity": "完整性檢查、處理狀態與完整來源問題歷史",
            "experience": "互動比較專用的來源數值；缺值保留 null，逐季僅明示 ADOPTED",
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path} ({len(text) / 1024 / 1024:.1f} MB)")


def collect(archive: "Archive") -> dict:
    from evidence import integrate
    from history import integrate_history
    from experience import integrate_experience
    from player_awards import integrate_player_awards
    from honour_review import integrate_honour_review
    from comparison import integrate_comparison
    payload = {
        "meta": archive.meta(),
        "world": archive.world(),
        "resolution": archive.resolution(),
        "clubs": archive.clubs(),
        "competitions": archive.competitions(),
        "sources": archive.sources(),
        "timetravel": archive.timetravel(),
        "people": archive.people(),
        "seasons": archive.seasons(),
        "players": archive.players(),
        "chronicle": archive.chronicle(),
        "clasico": archive.clasico(),
        "integrity": archive.integrity(),
        "honours": archive.honours(),
    }
    return integrate_comparison(archive, integrate_honour_review(archive, integrate_experience(archive, integrate_player_awards(archive, integrate_history(archive, integrate(archive, payload))))))


def build(db_path: Path, out_path: Path, template_path: Path, standalone: bool = False, *, allow_degraded: bool = False, workbook_path: Path | None = None) -> None:
    from archive_exchange import runtime, make_exchange, render_html, digest
    archive = Archive(db_path, allow_degraded=allow_degraded)
    try:
        payload = collect(archive)
    finally:
        archive.con.close()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace('<', '\\u003c')
    code = runtime()
    code['files']['template.html'] = template_path.read_text(encoding='utf-8')
    code['engine'] = digest(json.dumps(code['files'], ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c'))
    packet = make_exchange(workbook_path, db_path, payload, code['engine']) if workbook_path else {
        'format':'FM24_SNAPSHOT_V1', 'engine':code['engine'], 'payloadJSON':data,
        'payloadSha256':digest(data), 'filename':'網站快照（未附 Excel）', 'manifest':None}
    html = render_html(packet, code, portable=False, standalone=standalone)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    kind = "standalone" if standalone else "artifact fragment"
    print(f"wrote {out_path} ({len(html) / 1024:.0f} KB, payload {len(data) / 1024:.0f} KB, {kind})")
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"  {key:<12} {len(value)}")


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--database", type=Path, default=here / "data" / "fm24.sqlite")
    ap.add_argument("-o", "--output", type=Path, default=here / "dist" / "index.html")
    ap.add_argument("-t", "--template", type=Path, default=here / "template.html")
    ap.add_argument("-j", "--json", type=Path, metavar="PATH",
                    help="write the payload as a standalone JSON file and exit "
                         "(for feeding to another tool or model, not a browser)")
    ap.add_argument("-s", "--standalone", action="store_true",
                    help="emit a complete HTML document that opens from file:// "
                         "(the default output is a fragment for the Artifact platform)")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="承認簡繁轉換不可用，仍以不完整的結果執行")
    ap.add_argument("--workbook", type=Path, help="附上與 SQLite 同版的原始 Excel，供完整往返；更新建議使用 archive_exchange.py")
    args = ap.parse_args()
    degraded = not require_script_conversion(args.allow_degraded)
    if degraded:
        print("警告：以降級模式建置，簡繁轉換未啟用，身分相關數字不完整。", file=sys.stderr)
    if args.json:
        export_json(args.database, args.json, allow_degraded=args.allow_degraded)
        return
    build(args.database, args.output, args.template, standalone=args.standalone, allow_degraded=args.allow_degraded, workbook_path=args.workbook)


if __name__ == "__main__":
    main()
