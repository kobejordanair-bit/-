#!/usr/bin/env python3
"""Generate an audit brief: every checkable claim, with how to check it.

Handing a reviewer the output is not enough — the output is what this pipeline
concluded. A reviewer with the source workbook needs the CLAIMS and the
ASSUMPTIONS, each paired with the query that settles it, plus the judgement
calls that could reasonably have gone the other way.

Numbers are computed live so the brief cannot drift from the code.

    python3 audit_brief.py -o dist/audit-brief.md
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from build_site import Archive
from resolver import (COMPETITION_REFERENCE_COLUMNS, SCRIPT_CONVERSION_AVAILABLE, SURNAME_GATE, ClubResolver,
                      CompetitionResolver, IdentityResolver, discover_club_columns,
                      discover_competition_columns, require_script_conversion)


def generate(db_path: Path, *, allow_degraded: bool = False) -> str:
    archive = Archive(db_path, allow_degraded=allow_degraded)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    def scalar(sql: str, *args):
        return con.execute(sql, args).fetchone()[0]

    meta = archive.meta()
    integrity = archive.integrity()
    resolution = archive.resolution()
    clubs = archive.clubs()
    comps = archive.competitions()
    people = archive.people()

    null_string_rows = scalar(
        "SELECT COUNT(*) FROM Domestic_League_Standings WHERE Qualification_Raw = ?", "NULL")
    bang_rows = scalar(
        "SELECT COUNT(*) FROM Domestic_League_Standings WHERE Qualification_Raw = ?", "!")

    ident = IdentityResolver(con)
    club_res = ClubResolver(con)
    comp_res = CompetitionResolver(con)

    out: list[str] = []
    w = out.append

    w("# 稽核清單：FM24 World Master 資料管線")
    w("")
    w("這份清單給**手上有原始 .xlsx 的審查者**。每一條都是本管線做出的具體主張或假設，")
    w("附上可直接在 Excel 或 SQLite 驗證的方法。目的不是說服你，是讓你能反駁。")
    w("")
    w(f"- 工作簿：`FM24_World_Master_v6.4.0`，{meta['sheet_count']} 張表、{meta['row_count']:,} 列")
    w(f"- 結構版本：`{meta['schema_version']}`")
    w(f"- 本清單產生於：{meta['generated']}")
    w("")
    if not archive.script_conversion:
        w("> ⚠ **本清單在簡繁轉換不可用的環境產生，所有身分相關數字都不完整，"
          "且無法與完整環境的結果比較。**")
        w("")

    w("## 0. 最想被挑戰的三件事")
    w("")
    w("如果時間有限，看這三條就好——它們是最可能錯、而且錯了影響最大的。")
    w("")
    w("1. **欄位白名單是否漏了或多了。** 本管線靠人工列舉「哪些欄位裝的是俱樂部／賽事」，")
    w("   列錯就會漏算或灌水。第 4 節有完整清單，請對照工作簿確認。")
    w("2. **比對門檻是否合理。** 姓氏否決線、聯賽扣分、分群門檻都是看資料調出來的經驗值，")
    w("   沒有理論依據。第 5 節列出每個數字與它擋掉／放行的實例。")
    w("3. **被判定為「缺陷」的，是否真的是缺陷。** 有些可能是來源刻意為之。第 3 節逐條列出。")
    w("")

    # ---------------------------------------------------------------- counts
    w("## 1. 可直接核對的數字")
    w("")
    w("每一列都能在 Excel 用篩選或樞紐分析驗證。對不上就是本管線錯了。")
    w("")
    w("| 主張 | 數值 | 怎麼驗 |")
    w("|---|---:|---|")
    checks = [
        ("工作表數", meta["sheet_count"], "Excel 底部分頁數量"),
        ("總資料列（不含標題、不含全空列）", f"{meta['row_count']:,}",
         "各表列數相加；本管線會跳過整列皆空的列"),
        ("受控球員身分", meta["player_count"],
         "`Player_Dim` 的 **Player_ID 相異值**個數（不是列數，該表一列是一個別名）"),
        ("Player_Dim 總列數（別名）", meta["alias_count"], "`Player_Dim` 列數"),
        ("受控俱樂部", meta["club_count"], "`Club_Dim` 的 Club_ID 相異值個數"),
        ("受控賽事", comps["controlled"], "`Competition_Dim` 列數"),
        ("身分對照連結", f"{meta['identity_links']:,}", "`Record_Identity_Map` 列數"),
        ("獎項事實列", f"{integrity['totalAwards']:,}", "`Canonical_Award_Facts` 列數"),
        ("其中未綁定 Player_ID", integrity["unresolvedAwards"],
         "`Canonical_Award_Facts` 篩 Player_ID 為空"),
        ("Award_Resolution_Status 未解析列", resolution["totalRows"],
         "篩 `Resolution_Status = UNRESOLVED_IDENTITY`"),
        ("未解析的相異姓名", resolution["totalNames"], "同上，取 Player_Raw 相異值"),
        ("Data_Issues 列", integrity["issueTotal"], "`Data_Issues` 列數"),
        ("俱樂部字串（相異）", clubs["totalRefs"], "第 4 節欄位清單的聯集，取相異值"),
        ("其中對不到 Club_ID", len(clubs["unresolved"]), f"涵蓋 {clubs['unresolvedRows']} 列"),
        ("俱樂部重複身分", len(clubs["duplicates"]),
         "去掉「足球俱樂部」等綴詞後，同名卻有兩個以上 Club_ID"),
        ("賽事名稱（相異，不含分類）", comps["totalRefs"], "第 4 節欄位清單"),
        ("其中未受控", len(comps["unresolved"]), f"涵蓋 {comps['unresolvedRows']} 列"),
        ("同賽事異寫組", len(comps["clusters"]), "例如 LaLiga / LaLiga EA Sports / 西甲 LaLiga"),
        ("出賽分類列（非賽事名稱）", f"{comps['categoryRows']:,}",
         "`Player_Club_Competition_Stats.Competition_Raw` 中值為聯賽/杯赛/League/Cup… 的列"),
    ]
    for claim, value, how in checks:
        w(f"| {claim} | {value} | {how} |")
    w("")

    # ------------------------------------------------------------- findings
    w("## 2. 本管線宣稱的資料缺陷")
    w("")
    w("這些是程式從資料本身推出來的，不是人工清單。**請特別檢查有沒有誤判**——")
    w("有些可能是來源刻意保留的原貌，不該被當成錯誤。")
    w("")
    for i, f in enumerate(integrity["findings"], 1):
        w(f"### {i}. [{f['severity'].upper()}] {f['title']}")
        w("")
        w(f"- **位置**：`{f['where']}`")
        w(f"- **主張**：{f['detail']}")
        if f.get("sample"):
            w(f"- **樣本**：{'、'.join(str(x) for x in f['sample'])}")
        w("")

    # --------------------------------------------------------------- scope
    w("## 3. 範圍判斷（最容易出錯的地方）")
    w("")
    w("參照欄位改由**量測**決定：一個欄位算不算俱樂部參照，看它的值實際能不能對應到")
    w("`Club_Dim`。這個測試正好能區分真正的俱樂部欄與 `Intl_Tournament_Results.Winner`")
    w("——後者裝的是國家，對應不到任何俱樂部。")
    w("")
    w("**上一版用人工清單，經量測後發現漏了 54 個欄位**（幾乎所有聯賽獎項表都在內），")
    w("所以改成自動偵測。維度表本身與已知的自由文字欄另以排除清單處理。")
    w("")
    w("**請對照工作簿確認下面兩張清單有沒有誤判。**")
    w("")
    club_columns = discover_club_columns(con)
    w(f"### 視為俱樂部參照的欄位（{len(club_columns)} 個，自動偵測）")
    w("")
    for table, column in club_columns:
        present = "" if archive.has(table, column) else "  ⚠ 此欄位在目前工作簿中不存在"
        w(f"- `{table}.{column}`{present}")
    w("")
    comp_columns = discover_competition_columns(con)
    w(f"### 視為賽事參照的欄位（{len(comp_columns)} 個）")
    w("")
    for table, column in comp_columns:
        present = "" if archive.has(table, column) else "  ⚠ 此欄位在目前工作簿中不存在"
        w(f"- `{table}.{column}`{present}")
    w("")
    w("**刻意排除**：`Award` 欄（獎項不是賽事）、`Intl_Tournament_Results` 的 "
      "`Winner`/`Runner_Up`/`Third_Place`（那是國家）、`Historical_Records.Club_or_Context`"
      "（混合自由文字）。這些排除對嗎？")
    w("")

    # ------------------------------------------------------------ thresholds
    w("## 4. 比對規則與門檻")
    w("")
    w("全部是看真實資料調出來的經驗值，**沒有理論依據**，歡迎挑戰。")
    w("")
    w("### 球員：姓氏否決制")
    w("")
    w(f"- 分數 = 姓氏相似度 × 0.7 ＋ 名相似度 × 0.3")
    w(f"- 姓氏相似度 < **{SURNAME_GATE}** 直接否決整個配對")
    w("- 理由：中文譯名的「名」重複率極高（路易斯、多米尼克、亞歷山德羅），撐不起配對")
    w("")
    w("**已知限制**：`路易斯·迪亞斯` vs `路易斯·蘇亞雷斯` 的姓氏相似度恰為 0.50，")
    w("剛好通過閘門，會以約 71% 出現在待審清單（不會被判為確定配對）。")
    w("同一門檻同時放行了 `馬泰斯·德·萊特` → `馬泰斯·德里赫特` 這個真配對。")
    w("**這個取捨對嗎？調高門檻會同時失去 de Ligt。**")
    w("")
    w("### 字串相似度 = 三種量度取最大值")
    w("")
    w("bigram Dice、字元集重疊 × 0.85、編輯距離比。前兩者對「只差一個字的長名字」嚴重低估，")
    w("編輯距離把這類救回來。**取最大值是否過於寬鬆？**")
    w("")
    w("### 聯賽與賽季加權")
    w("")
    w("- 聯賽相符 **+0.10**；賽季在檔 **+0.06**")
    w("- 聯賽不符：姓名相似度 ≥ 0.90 時**只標註不扣分**（視為未記錄的轉會），否則 **−0.14**")
    w("- 俱樂部吻合 **+0.18**，但上限 0.98（1.0 保留給完全相同）")
    w("")
    w("### 俱樂部：綴詞剝除")
    w("")
    w("剝除後綴 `足球俱樂部`／`竞赛俱乐部` 等，與前綴 `FC`／`VfB`／`RC`／`RB` 等。")
    w("**這份綴詞清單完整嗎？有沒有剝過頭，把兩間不同俱樂部併成一間？**")
    w("")
    w("### 賽事：層級否決")
    w("")
    w("層級標記（數字、羅馬數字、`1ª`/`2ª`）不同就否決——`LaLiga` 與 `LaLiga 2` 是兩回事。")
    w("比對前先剝掉淘汰賽輪次（`決賽`、`半決賽第1回合`）。")
    w("**有沒有賽事的正式名稱本來就帶數字，因而被誤判？**")
    w("")

    # ---------------------------------------------------------- assumptions
    w("## 5. 未經驗證的假設")
    w("")
    w("這些是我做了但沒有向來源求證的判斷。**請優先檢查。**")
    w("")
    assumptions = [
        ("把字串 `'NULL'` 視為空值",
         f"`Domestic_League_Standings` 有 {null_string_rows} 列的資格欄是四字元字串 `NULL`。"
         "**請確認來源真的沒有用它表達任何意思。**"
         "（本管線原本也把 `'!'` 當成空值，後來查證發現那是降級標記，已修正——見下一條。）"),
        ("`'!'` 是降級標記",
         f"{bang_rows} 列的資格欄是單一驚嘆號。本管線判定它是降級標記，依據是：這些列**無一例外**"
         "落在該賽季墊底三名內，且與明寫「降级」者位於同一名次區間。"
         "**這個推論成立嗎？會不會是別的意思（例如附加賽、扣分）？**"),
        ("聯賽積分榜採 FINAL 快照",
         "同賽季有 PROVISIONAL 與 FINAL 兩份時，一律採 FINAL。"
         "**PROVISIONAL 會不會在某些情況下才是對的？**"),
        ("巴薩團隊冠軍採 A1 歸屬政策",
         "該賽季有巴薩出場紀錄即計入該季球隊冠軍。此政策取自工作簿本身的 "
         "`Attribution_Policy` 欄，未另行驗證其定義。"),
        ("能力值六維雷達的分組方式",
         "把 36 項 FM 屬性聚合成終結／創造／防守／心理／速度／體能六軸，"
         "分組是我自訂的，**不是 FM 官方分類**。"),
        ("簡繁轉換迭代到不動點",
         "OpenCC 的 s2t 不冪等（`里爾`→`裏爾`、`托`→`託`），本管線反覆轉換直到穩定。"
         "**這會把 里/裏/裡 視為同一字——在音譯名以外的情境可能不安全。**"),
        ("Season 起始年以字串中第一個 20xx 為準",
         "`2033-2034`、`2033/34`、`2033-34` 都解析為 2033。**有沒有跨年格式會被誤判？**"),
    ]
    for title, detail in assumptions:
        w(f"- **{title}** — {detail}")
    w("")

    # -------------------------------------------------------------- not done
    w("## 6. 明確沒有做的事")
    w("")
    w("- **從不改寫來源。** 所有身分決定寫入 `Ingest_*` 系列表，`.xlsx` 本身未被修改。")
    w("- **不補值。** 來源未提供即為 null，不以 0 代替。")
    w("- **不自動套用配對。** 所有候選都需人工確認。")
    w(f"- 球員積欠中 {sum(1 for i in resolution['items'] if i['verdict'] == 'no_candidate')} 個姓名**查無候選**，")
    w("  代表這些球員從未被工作簿收錄，需要建立新身分而非配對。")
    w(f"- 俱樂部積欠中 {sum(1 for u in clubs['unresolved'] if not u['candidates'])} 個字串同上。")
    w("")

    # --------------------------------------------------------------- probes
    w("## 7. 具體查核點（可直接複製到 Excel 篩選）")
    w("")
    w("| 檢查 | 預期結果 |")
    w("|---|---|")
    probes = [
        ("`Player_Club_Season_Totals` 篩 Season_ID = `PER-S-2034-35`，看 Season_Display",
         "應同時出現 `2034/35` 與 `2034-35` 兩種寫法"),
        ("同上，看 Club_Raw", "應同時出現「巴塞隆納」與「巴塞罗那」"),
        ("`Barcelona_Transfers` 的 Direction 欄相異值",
         "應有四種：轉入／轉出／IN／OUT"),
        ("`Domestic_League_Standings` 篩 LaLiga EA Sports + 2034/35，看 Snapshot",
         "應有兩個日期（賽季中與季末），共 40 列而非 20 列"),
        ("`Club_Dim` 搜尋「南安普頓」與「南安普顿」", "應得到兩個不同的 Club_ID"),
        ("`Nation_Dim` 搜尋「聯辦」或「聯合主辦」",
         "應得到兩筆，且兩者都不是國家"),
        ("`Intl_Tournament_Results` 的 Host 欄搜尋全形分號「；」",
         "應有 5 列把球場寫進了國家欄"),
        ("`Player_Club_Competition_Stats` 的 Competition_Raw 相異值",
         "應同時出現中文分類（联赛/杯赛/洲际级别）與英文分類（League/Cup/Continental）"),
        ("`UCL_Knockout_Results` 的欄位名稱", "**不應**存在 `Competition_Raw` 欄"),
    ]
    for probe, expected in probes:
        w(f"| {probe} | {expected} |")
    w("")
    w("最後一條是本管線曾經自己犯過的錯：SQLite 在雙引號識別字找不到欄位時會退化成")
    w("字串常值而不報錯，導致掃描結果憑空生出 268 列假資料。若你的工具也是 SQL，請注意。")
    w("")

    w("## 8. 資料覆蓋率")
    w("")
    w("**用途是宣告的，不是掃出來的。** 「執行過一次 SELECT」不等於完整接入——"
      "一張表可能只被讀取球會欄做身分比對，它的進球、助攻、評分從未出現在任何讀者頁。"
      "所以每張表的用途記在 `table_roles.py`，再由 `coverage.py` 與實際建置查詢交叉比對，"
      "檢查宣告為已使用的表是否真的被讀取；實際結果見 coverage.py 輸出。")
    w("")
    try:
        from table_roles import (ADOPTED, IDENTITY, PENDING_INTEGRATION, PRESERVED, PROVENANCE,
                                 ROLE_LABELS, ROLE_MEANINGS, SURFACED, use_of)
        from coverage import sheet_tables
        tables = sheet_tables(con)
        counts = {r: [0, 0] for r in (ADOPTED, SURFACED, IDENTITY, PROVENANCE, PRESERVED)}
        for sheet, table in tables.items():
            u = use_of(table)
            rows = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for role in u.roles:
                counts[role][0] += 1
                counts[role][1] += rows
        w("**用途標籤可以重疊**，一張表可以同時是身分索引與讀者頁內容——"
          "強迫單選會讓宣告本身變成錯的。列數是「這些表共含多少列」，"
          "**不代表全部已採用**：季中、季末與被取代的觀測本來就不該全進正式統計。")
        w("")
        w("| 用途 | 張數 | 表內列數 | 意義 |")
        w("|---|---:|---:|---|")
        for role in (ADOPTED, SURFACED, IDENTITY, PROVENANCE, PRESERVED):
            n, rows = counts[role]
            if n:
                w(f"| {ROLE_LABELS[role]} | {n} | {rows:,} | {ROLE_MEANINGS[role]} |")
        w("")
        w("**此檢查的邊界**：交叉比對只驗「有沒有讀到這張表」。把一張表從正式統計"
          "誤標成身分解析，兩者都算已使用，檢查不會抓到。因此每筆宣告另記"
          "**取用哪些欄位、輸出到哪個資料欄位或頁面**，供人工核對——"
          "那才是判斷標籤對錯的依據。")
        w("")
        if PENDING_INTEGRATION:
            by_p: dict[str, list] = {}
            for sheet, (priority, note) in sorted(PENDING_INTEGRATION.items()):
                by_p.setdefault(priority, []).append((sheet, note))
            w("### 待接入清單（依審查決策表）")
            w("")
            for priority in sorted(by_p):
                w(f"**{priority}**")
                w("")
                for sheet, note in by_p[priority]:
                    rows = con.execute(f'SELECT COUNT(*) FROM "{tables[sheet]}"').fetchone()[0] \
                        if sheet in tables else 0
                    w(f"- `{sheet}`　{rows:,} 列　—— {note}")
                w("")
        else:
            w("原定 P0／P1／P2 待接入清單：0 張、0 列。這不表示所有工作表的所有欄位均已採用。")
            w("")
    except Exception as exc:                      # pragma: no cover - diagnostics only
        w(f"（用途盤點未能產生：{exc}）")

    w("### 參照欄位偵測")
    w("")
    try:
        from coverage import scan
        result = scan(db_path, allow_degraded=allow_degraded)
        club_cols = len(discover_club_columns(con))
        comp_cols = len(discover_competition_columns(con))
        w(f"- **俱樂部參照欄 {club_cols} 個、賽事參照欄 {comp_cols} 個**，由值是否真能對應到維度表"
          "自動判定，非人工列舉。（前一版用人工清單，漏了 54 個欄位。）")
        leftover = [r for r in result["clubs"]
                    if r["table"] not in ("Club_Dim", "Competition_Dim", "Player_Dim", "Nation_Dim")]
        w(f"- 自動偵測之外仍疑似漏列者：{len(leftover)} 個"
          + ("（" + "、".join(f"{r['table']}.{r['column']}" for r in leftover[:4]) + "）" if leftover else "（無）"))
        w("- 偵測門檻為至少 3 個相異值、60% 可對應比例。少量資料或多數名稱尚未受控的欄位"
          "仍可能被漏掉，且本偵測與 `coverage.py` 的稽核共用同一組解析器，"
          "**不構成完全獨立的完整性證明**。")
    except Exception as exc:                      # pragma: no cover - diagnostics only
        w(f"（參照欄位量測未能執行：{exc}）")
    w("")

    w("## 9. 想請你回答的問題")
    w("")
    w("1. 第 3 節的欄位清單，有沒有**漏掉**任何裝俱樂部或賽事名稱的欄位？")
    w("2. 第 2 節的缺陷，有沒有哪一條其實是**來源刻意為之**、不該被當成錯誤？")
    w("3. 第 5 節的假設，哪一條最可能是錯的？")
    w("4. 有沒有**完全沒被碰到**的資料面向？（例如某張表從頭到尾沒進入任何視圖）")
    w("5. 以你看工作簿的角度，有沒有比「身分收斂」更該優先處理的問題？")
    w("")
    return "\n".join(out)


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--database", type=Path, default=here / "data" / "fm24.sqlite")
    ap.add_argument("-o", "--output", type=Path, default=here / "dist" / "audit-brief.md")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="承認簡繁轉換不可用，仍以不完整的結果執行")
    args = ap.parse_args()
    require_script_conversion(args.allow_degraded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = generate(args.database, allow_degraded=args.allow_degraded)
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output} ({len(text) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
