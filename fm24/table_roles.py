#!/usr/bin/env python3
"""What each sheet is used for — overlapping tags, with the evidence.

A first version used four mutually exclusive boxes. A reviewer pointed out that
they are not exclusive: Player_Dim supplies the identity index AND the names a
reader sees in the roster. Forcing one label made the declaration wrong, and the
cross-check could not catch it because it only compared "read" against "not
read" — a sheet filed under the wrong tag still counted as read.

So a sheet carries a SET of tags, and each declaration records what is actually
taken from it: which columns, which payload field or page, and whether the
pipeline reads the sheet directly or reaches its content through one of the
workbook's own derived tables.

Tracing is split, because they are different guarantees: knowing two names are
one person (IDENTITY) says nothing about being able to show where a fact came
from (PROVENANCE).
"""

from __future__ import annotations

from dataclasses import dataclass, field

ADOPTED = "adopted"        # values become figures the site states as fact
SURFACED = "surfaced"      # content is displayed to a reader
IDENTITY = "identity"      # read so entities can be matched, content not shown
PROVENANCE = "provenance"  # read so a fact's source can be cited
PRESERVED = "preserved"    # in the database, reached by no view

ROLE_LABELS = {
    ADOPTED: "正式統計採用",
    SURFACED: "讀者頁呈現",
    IDENTITY: "身分解析",
    PROVENANCE: "事實來源查證",
    PRESERVED: "尚未使用",
}

ROLE_MEANINGS = {
    ADOPTED: "欄位數值成為站上以事實呈現的數字",
    SURFACED: "內容直接顯示給讀者",
    IDENTITY: "供比對同一實體；是否另有呈現，見讀者頁標籤",
    PROVENANCE: "供查證事實或來源聲明的出處；不代表採用為正式統計",
    PRESERVED: "保存於資料庫，尚未被任何視圖使用",
}


@dataclass(frozen=True)
class Use:
    """One sheet's declared use. `roles` may hold several tags."""

    roles: frozenset
    columns: str = ""       # which columns are taken
    output: str = ""        # where they end up: payload field, page, or metric
    direct: bool = True     # False when reached through a derived table instead
    note: str = ""

    @property
    def sorted_roles(self) -> list:
        order = [ADOPTED, SURFACED, IDENTITY, PROVENANCE, PRESERVED]
        return [r for r in order if r in self.roles]


def use(*roles, columns="", output="", direct=True, note="") -> Use:
    return Use(frozenset(roles), columns, output, direct, note)


TABLE_USES: dict[str, Use] = {
    "Award_Fact_Source_Links": use(SURFACED, PROVENANCE,
        columns="Fact_Key/Origin_Sheet/Origin_Row/Source_ID/Link_Role/Verification_Status",
        output="honours.facts[].evidence → 獎項與人物頁來源面板；sources.unlinkedAwardEvidence → 未唯一關聯證據"),
    "Award_Index": use(SURFACED, columns="Category/Award/Worksheet/Data_Status/Record_Grain/Notes",
        output="honours.index → 榮譽殿堂獎項目錄，不擴增獎項事實"),
    "Season_Master_Field_Provenance": use(SURFACED, PROVENANCE,
        columns="Season/Field_Group/Source_Sheet/Source_ID/Source_Date/Coverage/Final_Result_Status",
        output="seasons[].provenance → 賽季欄位來源與採用狀態"),
    "Barcelona_Player_Season_Stats": use(SURFACED, PROVENANCE,
        columns="Player_ID/Season_ID/表現欄位/Source_ID/Verification_Status；無 Player_ID 的说明列另存",
        output="players[].seasonVerification → 逐欄核對（不再加總）；sources.seasonStatsNotes → 說明列"),
    "Barcelona_Player_Season_Honours": use(SURFACED, PROVENANCE,
        columns="Player_ID/Season_ID/Apps/Attribution_Policy/五項冠軍/Authority_Lineage/Source_Reference",
        output="players[].seasonHonours → 逐季冠軍歸屬；無世俱盃欄位，不補零"),
    "Barcelona_Transfer_Totals": use(SURFACED, PROVENANCE,
        columns="Season/Direction/Displayed_Total/Source_ID/Verification_Status/Notes",
        output="seasons[].transferTotals → 原始顯示總額，與 netSpend 分列，不重算"),
    # --- figures presented as fact ----------------------------------------
    "Barcelona_Season_Master": use(
        ADOPTED, SURFACED, columns="名次、積分、勝和負、六項賽事結果、轉會摘要",
        output="seasons[] → 巴薩王朝／巴薩賽季；experience.seasons → 王朝實驗室及戰績海報"),
    "Player_Club_Season_Totals": use(
        ADOPTED, SURFACED, columns="Apps/Goals/Assists/POTM/Rating，僅 ADOPTED 列",
        output="players[].seasonStats → 球員逐季圖與表；experience.players[].seasons → 球員對決（缺值保留）",
        note="非 ADOPTED 列另存 supersededStats，不計入任何統計"),
    "Barcelona_Player_Career": use(
        ADOPTED, SURFACED, columns="生涯總計與六項團隊冠軍",
        output="players[] → 巴薩陣容名冊與球員頁；experience.players → 生涯比較／戰績海報；夢幻 XI 選人名冊"),
    "Domestic_League_Standings": use(
        ADOPTED, SURFACED, columns="名次、積分、勝和負、進失球、資格說明",
        output="world.standings → 聯賽積分榜；world.champions → 冠軍版圖"),
    "Canonical_Award_Facts": use(
        ADOPTED, SURFACED, IDENTITY,
        columns="Award/Season/Rank/Player_Raw/Club_Raw/Player_ID",
        output="honours.winners → 榮譽殿堂；people[].awards → 球員獎項；身分積欠統計"),
    "UCL": use(ADOPTED, SURFACED, columns="Winner/Runner_Up",
               output="world.ucl 與 world.uclTitles → 歐冠決賽與奪冠次數（依 Club_ID 合併）"),
    "El_Clasico_Match_History": use(
        ADOPTED, SURFACED, columns="Date/Competition/Home/Away/Result_Raw",
        output="clasico[] → 國家德比戰績條／德比劇場／比分海報；保留原始比分與來源列"),
    "Barcelona_Transfers": use(
        ADOPTED, SURFACED, columns="Direction/Player/Counterparty_Club/Fee_Display",
        output="seasons[].transfersIn/Out → 巴薩賽季轉會名單"),
    "Player_Attr_Snap_O": use(
        ADOPTED, SURFACED, columns="36 項非門將屬性",
        output="players[].attrs → 能力值表與六維概覽"),
    "Player_Attr_Snap_G": use(ADOPTED, SURFACED, columns="門將屬性組",
                              output="players[].attrs → 能力值表"),
    "Ballon_dOr": use(ADOPTED, SURFACED, columns="Rank/Player/Club/Goals/Assists/Rating",
                      output="honours.ballonDor → 金球獎前三名"),
    "Player_League_Career": use(
        ADOPTED, SURFACED, IDENTITY,
        columns="Apps/Goals/Assists 加總；League_Raw 供聯賽加權；Club_Raw 供比對",
        output="people[] 的聯賽生涯累計 → 球員名錄欄位",
        note="審查指出：此表的數值有被加總，不只是呈現"),
    "Domestic_Leagues": use(
        ADOPTED, IDENTITY, columns="Competition/Season/Club/Rank=1",
        output="world.champions[].confirmedElsewhere → 決定冠軍是否標為暫定",
        note="審查指出：不只身分比對，會影響正式統計的呈現"),

    # --- displayed, not aggregated ----------------------------------------
    "World_Timeline": use(SURFACED, columns="事件敘述、類型、賽季、來源表",
                          output="chronicle[] → 編年史"),
    "Intl_Tournament_Results": use(SURFACED, columns="Tournament/Period/Winner/Runner_Up/Third/Host",
                                   output="world.intl → 國際賽事表"),
    "Competition_History": use(SURFACED, columns="Season/Competition/Winner/Runner_Up/Venue",
                               output="world.euroCups → 歐洲其他錦標"),
    "National_Tournaments": use(SURFACED, columns="Season/Competition/Rank/Club",
                                output="world.cups → 各國盃賽冠亞軍"),
    "UEFA_Super_Cup": use(SURFACED, IDENTITY, columns="Season/Winner/Runner_Up",
                          output="world.superCup → 歐洲超級盃歷屆",
                          note="審查指出：已輸出賽事結果，不只讀身分欄"),
    "FIFA_Club_World_Cup_Results": use(SURFACED, IDENTITY, columns="Period/Rank/Club",
                                       output="world.cwc → 世俱盃歷屆",
                                       note="審查指出：已輸出賽事結果，不只讀身分欄"),
    "Historical_Records": use(SURFACED, columns="Record_Type/Season/Player_or_Entity/Club_or_Context",
                              output="honours.records → 歷史紀錄查詢"),
    "Player_Profile_Snapshots": use(SURFACED, columns="國籍、位置、生日、背號",
                                    output="players[]／people[] 的個人欄位"),
    "Player_Career_Summaries": use(SURFACED, columns="國家隊出場、進球、助攻",
                                   output="players[].national → 球員頁國家隊區塊"),
    "Player_Attribute_Changes": use(SURFACED, columns="屬性、新舊值、快照區間",
                                    output="timetravel.changes → 認知史能力值變動"),
    "Barcelona_Season_Leaders": use(SURFACED, columns="Metric/Player/Value",
                                    output="seasons[].leaders → 球季個人領先"),
    "Barcelona_Squad_History": use(SURFACED, columns="Snapshot_Date 計數",
                                   output="timetravel.timeline → 認知史觀測量"),
    "Club_Cup_History": use(SURFACED, IDENTITY, columns="Snapshot 計數；Club_Raw 供比對",
                            output="timetravel.timeline → 認知史觀測量"),
    "Award_Resolution_Status": use(SURFACED, columns="Player_Raw/Origin_Sheet/Resolution_Status",
                                   output="resolution.items → 球員身分控制台"),
    "Data_Issues": use(SURFACED, columns="全部來源欄位、原始狀態與分類統計、Excel 列號",
                       output="integrity.domains → 完整性報告分佈"),
    "Workbook_Schema_Metadata": use(SURFACED, columns="結構版本、遷移識別",
                                    output="meta → 頁尾與完整性報告"),
    "Player_Dim": use(
        IDENTITY, SURFACED, PROVENANCE,
        columns="Player_ID/Canonical_Display_Name/Alias_Name",
        output="比對索引；people[].name 與 timetravel.playerNames → 球員名錄；honourReview → 受控別名的原名／欄位／列號證據",
        note="審查指出：正名直接出現在讀者頁，不只是比對索引"),
    "Club_Dim": use(IDENTITY, SURFACED, PROVENANCE, columns="Club_ID/正名/別名/_row",
                    output="俱樂部比對索引與重複身分偵測；honourReview → 重複 ID、名稱、引用列數與主檔列號"),
    "Nation_Dim": use(IDENTITY, columns="National_Team_ID/正名/別名",
                      output="國家名稱比對；完整性報告的非國家身分檢查"),
    "Competition_Dim": use(IDENTITY, columns="Competition_ID/Competition_Name",
                           output="賽事比對索引"),
    "Record_Identity_Map": use(IDENTITY, SURFACED, PROVENANCE,
                               columns="Raw_Display_Name/Entity_ID/Period_ID/Origin_Sheet/Origin_Row/Entity_Role/_row",
                               output="比對索引（10,558 列關聯）；honourReview → 失效對照的舊姓名、期間、ID、證據列，與現有來源並列"),
    # --- P0 接入：共用的來源與期間對照 -------------------------------------
    "Source_Index": use(
        SURFACED, PROVENANCE,
        columns="Source_ID/File_Name/Domain/Season_Context/Source_Note（Local_Path 刻意不取）",
        output="sources.sources → 來源與期間頁的來源名冊；引用次數由各事實表的 Source_ID 統計",
        note="Local_Path 記的是組建機器上的檔案路徑，不入 payload 也不顯示"),
    "Period_Dim": use(
        SURFACED, IDENTITY,
        columns="Period_ID/Source_Period_Display/Canonical_Period_Display/Period_Type/起迄年",
        output="sources.periods 與 sources.mergedPeriods → 期間對照表",
        note="同一賽季的多種寫法收斂到一個 Period_ID，共 12 個期間有多種寫法"),

    "Player_Club_Competition_Stats": use(IDENTITY, columns="Club_ID/League_Raw",
                                         output="球員聯賽歸屬，供比對加權",
                                         note="出場、進球、評分欄位未呈現"),

    # Read only so identity matching can see their club columns. Declared
    # separately because the distinction matters: these sheets are read, but
    # their performance figures reach no reader.
    "Barcelona_Club_World_Cup": use(IDENTITY, columns="Opponent",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Barcelona_UCL_Journey": use(IDENTITY, columns="Opponent",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Bundesliga_Elf_des_Jahres": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Goals 等欄位未呈現"),
    "Bundesliga_Torjagerkanone": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Bundesliga_Torjagerkanone_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Goals 等欄位未呈現"),
    "Bundesliga_VDV_Newcomer": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals／Rating 等欄位未呈現"),
    "Bundesliga_VDV_Newcomer_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Canonical_Competition_Results": use(IDENTITY, columns="Club_Raw／Opponent_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Club_Season_Player_History": use(IDENTITY, columns="Current_Club_Raw",
                  output="俱樂部比對索引", note="Apps／Goals 等欄位未呈現"),
    "FIFA_FIFPro_World_XI": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Goals 等欄位未呈現"),
    "Goal_50": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Golden_Shoe": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Goals／Points 等欄位未呈現"),
    "Kopa_Trophy": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "LaLiga_2034_35_Table_RAW": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "LaLiga_Awards_RAW": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "LaLiga_Coach_of_Year": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "LaLiga_Player_of_Year": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "LaLiga_Team_Season_Raw": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Apps／Rating 等欄位未呈現"),
    "Legacy_Historical_Evidence": use(IDENTITY, columns="Club_or_Context",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Ligue1_Golden_Boot": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Ligue1_Golden_Boot_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Goals 等欄位未呈現"),
    "Ligue1_UNFP_Best_XI": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Goals 等欄位未呈現"),
    "Ligue1_UNFP_MVP": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Ligue1_UNFP_MVP_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "PL_2034_35_Table_RAW": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "PL_Awards_RAW": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "PL_Golden_Boot_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Goals 等欄位未呈現"),
    "PL_PFA_POTY_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "PL_PFA_Team_of_Year": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Goals 等欄位未呈現"),
    "PL_PFA_Young_POTY": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Apps／Assists／Goals 等欄位未呈現"),
    "PL_PFA_Young_POTY_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "PL_Season_Records": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Apps 等欄位未呈現"),
    "Pichichi_Award": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Player_National_Team_Stats": use(IDENTITY, columns="Context_Club",
                  output="俱樂部比對索引", note="Apps／Assists／Goals／Rating 等欄位未呈現"),
    "Premier_League_Golden_Boot": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Premier_League_PFA_POTY": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Real_Madrid_Copa_History": use(IDENTITY, columns="Opponent",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Real_Madrid_UCL_History": use(IDENTITY, columns="Opponent",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Retirement_Career_History": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "Serie_A_Capocannoniere": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Serie_A_MVP_Player": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Apps／Assists／Goals 等欄位未呈現"),
    "Serie_A_MVP_Young": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Apps／Assists／Goals 等欄位未呈現"),
    "Serie_A_Team_of_Year": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="Appearances／Goals 等欄位未呈現"),
    "The_Best_FIFA_Mens_Player": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_2034_35_KO_RAW": use(IDENTITY, columns="Team1_Raw／Team2_Raw",
                  output="俱樂部比對索引", note="Score_Raw 等欄位未呈現"),
    "UCL_Awards_RAW": use(IDENTITY, columns="Club_Raw",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "UCL_Golden_Boot": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Knockout_Results": use(IDENTITY, columns="Left_Club_Raw／Right_Club_Raw",
                  output="俱樂部比對索引", note="Score_Raw 等欄位未呈現"),
    "UCL_Season_Best_Player": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Season_Best_Young_Player": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "UCL_Season_Leaders": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="僅比對，無表現欄位"),
    "World_Player_of_the_Year": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
    "Worlds_Best_Goalkeeper": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances 等欄位未呈現"),
    "Yashin_Trophy": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances 等欄位未呈現"),
    "Youth_Awards": use(IDENTITY, columns="Club",
                  output="俱樂部比對索引", note="Appearances／Assists／Goals 等欄位未呈現"),
}


# Completed review plan, retaining the original priorities and constraints.
COMPLETED_P1_P2: dict[str, tuple[str, str]] = {
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

# Each is rendered in its reader view and in the searchable evidence register.
# Whole-row preservation does not imply statistical adoption.
for _table, (_priority, _constraint) in COMPLETED_P1_P2.items():
    TABLE_USES[_table] = use(SURFACED, PROVENANCE,
        columns="全部來源欄位（含原始列號）；不以原始證據新增正式統計",
        output="reference.tables → 史料與查證；國際賽程／俱樂部史料／退役檔案及獎項來源面板",
        note=_constraint)

PENDING_INTEGRATION: dict[str, tuple[str, str]] = {}
TABLE_USES['Retirement_Career_History'] = use(SURFACED, PROVENANCE, IDENTITY,
    columns='Years_Raw/Club_Raw/Nation_Raw/Apps_Raw/Goals_Raw/Source_ID/Source_Block_Index',
    output='history.retirements[].sections → 退役生涯逐段履歷；reference.tables → 來源原文',
    note='以球員、來源、區塊三者共同定位；不把履歷再加進生涯摘要。')

# Independent structured award authorities now reach each player's ledger.
from player_awards import AWARD_SHEETS
for _table in AWARD_SHEETS:
    _previous = TABLE_USES.get(_table, use())
    TABLE_USES[_table] = use(*(_previous.roles | {SURFACED, PROVENANCE}),
        columns=_previous.columns + '；獎項／期間／名次／球員／表現欄位／來源列',
        output=_previous.output + '；people.players[].awards → 球員獎項及逐筆來源；reference.tables → 原始列',
        note='依受控身分及期間去重；生涯摘要與統計領先者不新增獎項。')


def use_of(table: str) -> Use:
    return TABLE_USES.get(table, use(PRESERVED))
