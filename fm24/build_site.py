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

    # ------------------------------------------------------------ chronicle --
    def chronicle(self) -> list[dict]:
        rows = self.q(
            """SELECT * FROM World_Timeline
               WHERE Event_Type IN ('巴塞隆納歐冠成績','歐洲冠軍聯賽冠軍','個人獎項','國際賽冠軍','Competition winner')
                  OR Subject LIKE '%巴塞%' OR Objective_Fact LIKE '%巴塞%'
               ORDER BY Period_ID DESC, Timeline_ID"""
        )
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

        missing_gf = [s["Season"] for s in self.q("SELECT Season, LaLiga_GF FROM Barcelona_Season_Master WHERE LaLiga_GF IS NULL")]
        if missing_gf:
            findings.append({
                "severity": "low",
                "title": "賽季主表存在來源未提供的空值",
                "detail": f"{'、'.join(missing_gf)} 的西甲進球／失球未填。依 append-only 政策保持未知而非補 0，屬正確處理，列此僅供追蹤補資料。",
                "where": "Barcelona_Season_Master",
                "sample": missing_gf,
            })

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
        return {
            "ballonDor": [{"season": k, "podium": v} for k, v in by_season.items()],
            "awardCatalogue": [{"award": r["Award"], "count": as_int(r["n"])} for r in awards],
        }


def build(db_path: Path, out_path: Path, template_path: Path) -> None:
    archive = Archive(db_path)
    payload = {
        "meta": archive.meta(),
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
