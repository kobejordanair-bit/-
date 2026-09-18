#!/usr/bin/env python3
"""What each sheet is actually used for, declared and then cross-checked.

A reviewer pointed out that "a query touched this table" is not the same as
"this table is properly integrated": a sheet can be read only for identity
matching while none of its goals, assists or fixtures ever reach a reader. One
bit of measurement cannot carry four different meanings.

So the role is DECLARED here — it is a design fact, not something a scan can
infer — and coverage.py cross-checks the declaration against what a build
actually reads, so a claim and the code cannot drift apart unnoticed.
"""

from __future__ import annotations

# 正式統計採用 — rows become figures the site presents as fact
ADOPTED = "adopted"
# 讀者頁呈現 — rows are displayed to a reader, as a list or table
SURFACED = "surfaced"
# 來源追溯使用 — read to resolve identities or trace provenance, not displayed
TRACING = "tracing"
# 原始證據保留 — kept in the database, reachable by query, not used by any view
PRESERVED = "preserved"

ROLE_LABELS = {
    ADOPTED: "正式統計採用",
    SURFACED: "讀者頁呈現",
    TRACING: "來源追溯使用",
    PRESERVED: "原始證據保留",
}

# Anything absent defaults to PRESERVED, which is the honest assumption: a sheet
# is not integrated until someone says what it is for.
# Sheets awaiting a decision on integration, with the reviewer's priority.
PENDING_INTEGRATION: dict[str, tuple[str, str]] = {
    "Award_Fact_Source_Links": ("P0", "獎項詳情的來源證據，依 Fact_Key 關聯，多來源不得變多次得獎"),
    "Award_Index": ("P0", "獎項目錄與涵蓋狀態，需區分得主／前三／最佳陣容粒度"),
    "Period_Dim": ("P0", "統一賽季識別，不同寫法不得造成重複賽季"),
    "Season_Master_Field_Provenance": ("P0", "逐欄位來源日期與採用狀態，不得以單一季末日期套用整頁"),
    "Source_Index": ("P0", "查看來源的編號、檔名與說明；不公開本機路徑"),
    "Barcelona_Player_Season_Honours": ("P0", "冠軍數逐季依據，遵守 Attribution_Policy，無世俱盃欄位不得補零"),
    "Barcelona_Player_Season_Stats": ("P0", "巴薩逐季核對來源，不與 Club Season Totals 疊加"),
    "Barcelona_Transfer_Totals": ("P0", "季度官方轉會總額，與淨支出分開交代"),
    "Barcelona_Club_Records": ("P1", "隊史紀錄，需顯示 As_Of 並區分存檔十二季與完整隊史"),
    "Barcelona_LaLiga_Best_XI": ("P1", "逐季西甲最佳陣容，不得假設全為巴薩球員"),
    "National_Tournament_Context": ("P1", "須與分組、賽程一併接入；明確更正優先於原始標題"),
    "National_Tournament_Groups": ("P1", "國際賽分組積分榜"),
    "National_Tournament_Matches": ("P1", "國際賽逐場賽程，保留加時與點球，不推定晉級"),
    "Real_Madrid_LaLiga_History": ("P1", "逐季對照，與正式積分榜去重"),
    "Retirement_Profiles": ("P1", "退役球員身分快照，非現役"),
    "Retirement_Career_Totals": ("P1", "退役生涯總計，不覆蓋口徑可能不同的 Profile 總計"),
    "Retirement_Milestones": ("P1", "里程碑照原意呈現，First／Second 非獎項排名"),
    "Retirement_Narratives": ("P1", "退役回顧原文，與正式統計分開"),
    "Bundesliga_VDV_Player": ("P1", "補前三名與表現欄位，以正式獎項事實為識別"),
    "Bundesliga_VDV_Player_History": ("P2", "歷屆得主核對，不重複計算得獎"),
    "Serie_A_Capocannoniere_History": ("P2", "金靴得主核對"),
    "Serie_A_MVP_Player_History": ("P2", "年度最佳得主核對"),
    "Serie_A_MVP_Young_History": ("P2", "最佳年輕球員得主核對"),
    "Barcelona_History": ("P2", "賽季主表追溯來源，已有正式衍生表則不另建頁"),
    "Barcelona_RealMadrid_H2H": ("P2", "該 As_Of 的交手摘要，舊 44 場不得覆蓋最新 46 場"),
    "Barcelona_Club_Records_RAW": ("P2", "隊史紀錄原始證據，不另累計"),
    "Continental_Awards_RAW": ("P2", "歐洲獎項原始證據，不疊加獎項次數"),
    "League_Award_Raw_2034_35": ("P2", "2034/35 獎項原始行，不將每行視為獎項事實"),
    "Import_Observations": ("P2", "匯入決策歷史，非新增比賽數據"),
    "Club_Cup_History_Issues": ("P2", "盃賽問題清單，Issue 文字非賽果"),
    "Retirement_Extraction_Issues": ("P2", "退役資料缺口與歧義"),
    "Retirement_Honours_Claims": ("P2", "未逐季採用的來源敘述，不自動展開年份"),
}

TABLE_ROLES: dict[str, tuple[str, str]] = {
    # --- figures the site presents as fact --------------------------------
    "Barcelona_Season_Master": (ADOPTED, "巴薩逐季主表：名次、積分、六項賽事結果"),
    "Player_Club_Season_Totals": (ADOPTED, "球員逐季數據，僅採用 ADOPTED 列"),
    "Barcelona_Player_Career": (ADOPTED, "球員生涯總計與團隊冠軍歸屬"),
    "Domestic_League_Standings": (ADOPTED, "五大聯賽積分榜，依 Season_Status 選快照"),
    "Canonical_Award_Facts": (ADOPTED, "獎項事實列，榮譽殿堂與球員獎項來源"),
    "UCL": (ADOPTED, "歐冠決賽結果，冠軍次數依 Club_ID 合併"),
    "El_Clasico_Match_History": (ADOPTED, "國家德比逐場結果與勝負判定"),
    "Barcelona_Transfers": (ADOPTED, "逐季轉入轉出名單"),
    "Player_Attr_Snap_O": (ADOPTED, "非門將能力值快照與六維概覽"),
    "Player_Attr_Snap_G": (ADOPTED, "門將能力值快照"),
    "Ballon_dOr": (ADOPTED, "金球獎前三名與當季數據"),

    # --- displayed to a reader --------------------------------------------
    "World_Timeline": (SURFACED, "編年史事件清單"),
    "Intl_Tournament_Results": (SURFACED, "國際賽冠亞季軍與主辦"),
    "Competition_History": (SURFACED, "歐洲其他錦標歷屆結果"),
    "National_Tournaments": (SURFACED, "各國盃賽名次"),
    "Player_League_Career": (SURFACED, "球員名錄的聯賽生涯累計"),
    "Player_Profile_Snapshots": (SURFACED, "球員國籍、位置、生日"),
    "Player_Career_Summaries": (SURFACED, "國家隊生涯總計"),
    "Player_Attribute_Changes": (SURFACED, "認知史的能力值變動"),
    "Barcelona_Season_Leaders": (SURFACED, "賽季個人領先"),
    "Barcelona_Squad_History": (SURFACED, "陣容快照，供認知史計算"),
    "Club_Cup_History": (SURFACED, "盃賽進程，供認知史計算"),
    "Award_Resolution_Status": (SURFACED, "身分解析控制台的積欠清單"),
    "Data_Issues": (SURFACED, "完整性報告的問題分佈"),
    "Workbook_Schema_Metadata": (SURFACED, "結構版本與遷移識別"),

    # --- read for identity or provenance, not displayed --------------------
    "Player_Dim": (TRACING, "球員受控身分與別名索引"),
    "Club_Dim": (TRACING, "俱樂部受控身分與別名索引"),
    "Nation_Dim": (TRACING, "國家隊受控身分"),
    "Competition_Dim": (TRACING, "賽事受控身分"),
    "Record_Identity_Map": (TRACING, "已接受的原始名→ID 關聯，比對索引的主要來源"),
    "Player_Club_Competition_Stats": (TRACING, "俱樂部與聯賽對照，供比對加權"),
    # Declared as the A1 policy's basis on a first pass; the cross-check showed
    # the build never reads it — that policy comes from Barcelona_Player_Career.


    # Read only so identity matching can see their club and player columns. The
    # reviewer's point exactly: a sheet being read is not the same as its
    # figures reaching anyone. Their performance columns are NOT surfaced.
    "Barcelona_Club_World_Cup": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Barcelona_UCL_Journey": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Bundesliga_Elf_des_Jahres": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals 等欄位未呈現"),
    "Bundesliga_Torjagerkanone": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Bundesliga_Torjagerkanone_History": (TRACING, "僅讀取球會／球員欄供身分比對；Goals 等欄位未呈現"),
    "Bundesliga_VDV_Newcomer": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals／Rating 等欄位未呈現"),
    "Bundesliga_VDV_Newcomer_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Canonical_Competition_Results": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Club_Season_Player_History": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Goals 等欄位未呈現"),
    "Domestic_Leagues": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "FIFA_Club_World_Cup_Results": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "FIFA_FIFPro_World_XI": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals 等欄位未呈現"),
    "Goal_50": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Golden_Shoe": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals／Points 等欄位未呈現"),
    "Historical_Records": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Kopa_Trophy": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "LaLiga_2034_35_Table_RAW": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "LaLiga_Awards_RAW": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "LaLiga_Coach_of_Year": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "LaLiga_Player_of_Year": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "LaLiga_Team_Season_Raw": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Rating 等欄位未呈現"),
    "Legacy_Historical_Evidence": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Ligue1_Golden_Boot": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Ligue1_Golden_Boot_History": (TRACING, "僅讀取球會／球員欄供身分比對；Goals 等欄位未呈現"),
    "Ligue1_UNFP_Best_XI": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals 等欄位未呈現"),
    "Ligue1_UNFP_MVP": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Ligue1_UNFP_MVP_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "PL_2034_35_Table_RAW": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "PL_Awards_RAW": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "PL_Golden_Boot_History": (TRACING, "僅讀取球會／球員欄供身分比對；Goals 等欄位未呈現"),
    "PL_PFA_POTY_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "PL_PFA_Team_of_Year": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals 等欄位未呈現"),
    "PL_PFA_Young_POTY": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Assists／Goals 等欄位未呈現"),
    "PL_PFA_Young_POTY_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "PL_Season_Records": (TRACING, "僅讀取球會／球員欄供身分比對；Apps 等欄位未呈現"),
    "Pichichi_Award": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Player_National_Team_Stats": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Assists／Goals／Rating 等欄位未呈現"),
    "Premier_League_Golden_Boot": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Premier_League_PFA_POTY": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Real_Madrid_Copa_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Real_Madrid_UCL_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Retirement_Career_History": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "Serie_A_Capocannoniere": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Serie_A_MVP_Player": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Assists／Goals 等欄位未呈現"),
    "Serie_A_MVP_Young": (TRACING, "僅讀取球會／球員欄供身分比對；Apps／Assists／Goals 等欄位未呈現"),
    "Serie_A_Team_of_Year": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Goals 等欄位未呈現"),
    "The_Best_FIFA_Mens_Player": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_2034_35_KO_RAW": (TRACING, "僅讀取球會／球員欄供身分比對；Score_Raw 等欄位未呈現"),
    "UCL_Awards_RAW": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "UCL_Golden_Boot": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Knockout_Results": (TRACING, "僅讀取球會／球員欄供身分比對；Score_Raw 等欄位未呈現"),
    "UCL_Season_Best_Player": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Season_Best_Young_Player": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Season_Leaders": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "UEFA_Super_Cup": (TRACING, "僅讀取球會／球員欄供身分比對"),
    "World_Player_of_the_Year": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
    "Worlds_Best_Goalkeeper": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances 等欄位未呈現"),
    "Yashin_Trophy": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances 等欄位未呈現"),
    "Youth_Awards": (TRACING, "僅讀取球會／球員欄供身分比對；Appearances／Assists／Goals 等欄位未呈現"),
}


def role_of(table: str) -> tuple[str, str]:
    return TABLE_ROLES.get(table, (PRESERVED, ""))
