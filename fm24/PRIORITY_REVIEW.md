# 高影響資料缺口核對報告

建置日期：2026-09-23；依目前 Master v6.4.0 及網站相同明細重新核對。

共 274 項：P0 5 項、P1 84 項、P2 185 項。

P0：直接來源矛盾或多 ID 均有資料。P1：漏掛得獎、至少五列獎項、唯一既有別名線索、失效對照。P2：其餘缺口。相同優先級依得獎列數、影響列數排序。優先級不是身分信心；不同類別的影響數不能相加。

本輪完成來源定位、失效對照核對及優先級整理；以下主檔矛盾尚未擅自修正。不同類別的影響數不可相加，也不是可新增的獎盃數。

## P0：直接矛盾與俱樂部多 ID

### 波爾圖二隊

多個 Club_ID 均承載資料，合併前需核對引用

影響：31 列／引用。證據：Club_Dim:281; Club_Dim:282。
- C-0201 波尔图二队：25 引用列；Player_Club_Competition_Stats 16；Player_League_Career 5；Player_Club_Season_Totals 4
- C-0202 FC波尔图二队：6 引用列；Player_Club_Competition_Stats 4；Player_Club_Season_Totals 1；Player_League_Career 1

核對各 ID 的來源、球隊級別及歷年身份；確認主 ID 與轉向關係後才遷移引用。

### 南安普頓

多個 Club_ID 均承載資料，合併前需核對引用

影響：25 列／引用。證據：Club_Dim:153; Club_Dim:272。
- C-0119 南安普頓：20 引用列；Player_Club_Competition_Stats 12；Player_Club_Season_Totals 4；Player_League_Career 4
- C-0195 南安普顿：5 引用列；Player_Club_Competition_Stats 3；Player_Club_Season_Totals 1；Player_League_Career 1

核對各 ID 的來源、球隊級別及歷年身份；確認主 ID 與轉向關係後才遷移引用。

### 多特蒙德

多個 Club_ID 均承載資料，合併前需核對引用

影響：17 列／引用。證據：Club_Dim:24; Club_Dim:165。
- C-0125 多特蒙德足球俱樂部：12 引用列；Canonical_Award_Facts 9；Player_League_Career 3
- C-0024 多特蒙德：5 引用列；Player_Club_Competition_Stats 3；Player_Club_Season_Totals 1；Player_League_Career 1

核對各 ID 的來源、球隊級別及歷年身份；確認主 ID 與轉向關係後才遷移引用。

### 2026 伊朗

同隊在同屆賽事出現在多個小組

影響：2 列／引用。證據：National_Tournament_Groups:97; National_Tournament_Groups:120。

矛盾分組：2026 二组 / 2026 八组。

回查對應分組截圖或原始文字，確認兩列的球隊名稱；不自行刪除任何一列。

### 2034 新西兰

同隊在同屆賽事出現在多個小組

影響：2 列／引用。證據：National_Tournament_Groups:16; National_Tournament_Groups:29。

矛盾分組：2034 四组 / 2034 七组。

回查對應分組截圖或原始文字，確認兩列的球隊名稱；不自行刪除任何一列。

## 已找到受控別名的十組線索

10 組、涉及 19 筆原始獎項。正規化只處理簡繁、大小寫及分隔符。以下是逐列人工核對的候選，尚未採用或增加個人榮譽。

| 原始姓名 | 候選 ID | 原始列數 | Player_Dim 證據 | 獎項來源 |
|---|---|---:|---|---|
| 埃尔林·哈兰德 | P-0036 | 3 | Player_Dim:36 | Premier_League_Golden_Boot:36; PL_PFA_Team_of_Year:133; UCL_Golden_Boot:15 |
| 马丁纳·戈约吉伊夫 | P-0121 | 1 | Player_Dim:120 | PL_PFA_Young_POTY:13 |
| Kim Min-Jae | P-0002 | 7 | Player_Dim:3 | Bundesliga_Elf_des_Jahres:49; Bundesliga_Elf_des_Jahres:60; Bundesliga_Elf_des_Jahres:71; Bundesliga_Elf_des_Jahres:81; Bundesliga_Elf_des_Jahres:92; Bundesliga_Elf_des_Jahres:103; Bundesliga_Elf_des_Jahres:115 |
| 佩德罗·坎波斯 | P-0168 | 2 | Player_Dim:165 | Barcelona_LaLiga_Best_XI:131; Pichichi_Award:16 |
| 伊利亚·扎巴尔尼 | P-0011 | 1 | Player_Dim:12 | PL_PFA_Team_of_Year:126 |
| 布卡约·萨卡 | P-0049 | 1 | Player_Dim:49 | PL_PFA_Team_of_Year:131 |
| 若奥·卡瓦略·德·苏萨 | P-0308 | 1 | Player_Dim:444 | Bundesliga_VDV_Newcomer:15 |
| 萨米赫·克利奇索伊 | P-0135 | 1 | Player_Dim:134 | Barcelona_LaLiga_Best_XI:130 |
| 谢赫·桑内赫 | P-0130 | 1 | Player_Dim:129 | Barcelona_LaLiga_Best_XI:122 |
| 里科·刘易斯 | P-0117 | 1 | Player_Dim:117 | PL_PFA_Team_of_Year:124 |

## 其他優先核對：得獎影響最大的前十組

| 原始姓名 | 得獎列 | 入選列 | 其他名次列 | 期間 | 證據 |
|---|---:|---:|---:|---|---|
| 贡萨洛·拉莫斯 | 6 | 6 | 2 | 2034/35、2033/34、2032/33、2031/32、2028/29、2027/28、2026/27、2023/24 | Golden_Shoe:4; Ligue1_UNFP_Best_XI:12; Ligue1_UNFP_Best_XI:23; Ligue1_UNFP_Best_XI:34; Ligue1_UNFP_Best_XI:67; Ligue1_UNFP_Best_XI:78; Ligue1_UNFP_Best_XI:122; Ligue1_Golden_Boot:37; Ligue1_Golden_Boot:2; Ligue1_Golden_Boot:5; Ligue1_Golden_Boot:8; Ligue1_Golden_Boot:17; Ligue1_Golden_Boot:23; Ligue1_Golden_Boot:32 |
| 拉斯马斯·温特·霍兰德 | 2 | 3 | 4 | 2033/34、2032/33、2031/32、2029/30、2028/29 | Golden_Shoe:3; Premier_League_Golden_Boot:2; Premier_League_Golden_Boot:6; Premier_League_Golden_Boot:8; Premier_League_Golden_Boot:15; Premier_League_Golden_Boot:18; PL_PFA_Team_of_Year:11; PL_PFA_Team_of_Year:33; PL_PFA_Team_of_Year:56 |
| 凯南·伊尔迪斯 | 2 | 4 | 0 | 2031/32、2029/30、2027/28、2026/27、2025/26 | Serie_A_Team_of_Year:33; Serie_A_Team_of_Year:55; Serie_A_Team_of_Year:77; Serie_A_Team_of_Year:88; Serie_A_MVP_Young:9; Serie_A_MVP_Young:10 |
| 哈里·凯恩 | 2 | 2 | 2 | 2025/26、2024/25、2023/24 | Golden_Shoe:34; Bundesliga_Elf_des_Jahres:100; Bundesliga_Elf_des_Jahres:122; Bundesliga_Torjagerkanone:26; Bundesliga_Torjagerkanone:31; Bundesliga_Torjagerkanone:32 |
| Vitinha | 2 | 1 | 1 | 2030/31、2026/27 | Golden_Shoe:25; Serie_A_Team_of_Year:43; Serie_A_Capocannoniere:11; Serie_A_Capocannoniere:23 |
| 费尔·尼尼奥 | 2 | 0 | 1 | 2029/30、2027/28、2025/26 | Ligue1_Golden_Boot:14; Ligue1_Golden_Boot:22; Ligue1_Golden_Boot:26 |
| 瓦伦丁·卡波尼 | 2 | 0 | 0 | 2031/32 | Golden_Shoe:8; Serie_A_Capocannoniere:8 |
| 伊莱耶·瓦希 | 1 | 1 | 3 | 2032/33、2030/31、2026/27、2025/26 | Bundesliga_Elf_des_Jahres:23; Bundesliga_Torjagerkanone:5; Bundesliga_Torjagerkanone:13; Bundesliga_Torjagerkanone:24; Bundesliga_Torjagerkanone:28 |
| 尼科 | 1 | 4 | 0 | 2031/32、2030/31、2029/30、2028/29 | Ligue1_UNFP_Best_XI:29; Ligue1_UNFP_Best_XI:40; Ligue1_UNFP_Best_XI:51; Ligue1_UNFP_Best_XI:62; Ligue1_UNFP_MVP:5 |
| 尼科洛·巴雷拉 | 1 | 4 | 0 | 2029/30、2028/29、2026/27、2023/24 | Serie_A_Team_of_Year:53; Serie_A_Team_of_Year:63; Serie_A_Team_of_Year:85; Serie_A_Team_of_Year:118; Serie_A_MVP_Player:12 |

## 失效列號對照

現有來源列的姓名／期間與 Record_Identity_Map 舊對照不符。網站已拒用；JSON 與工作台保留兩側姓名、期間、ID 及列號，可逐列回查。

| 來源表 | 不符列數 | 來源列 |
|---|---:|---|
| Barcelona_Season_Leaders | 11 | Barcelona_Season_Leaders:35; Barcelona_Season_Leaders:36; Barcelona_Season_Leaders:37; Barcelona_Season_Leaders:39; Barcelona_Season_Leaders:40; Barcelona_Season_Leaders:41; Barcelona_Season_Leaders:42; Barcelona_Season_Leaders:43; Barcelona_Season_Leaders:44; Barcelona_Season_Leaders:45; Barcelona_Season_Leaders:59 |
| PL_PFA_Team_of_Year | 6 | PL_PFA_Team_of_Year:112; PL_PFA_Team_of_Year:114; PL_PFA_Team_of_Year:117; PL_PFA_Team_of_Year:119; PL_PFA_Team_of_Year:120; PL_PFA_Team_of_Year:122 |
| Barcelona_LaLiga_Best_XI | 5 | Barcelona_LaLiga_Best_XI:75; Barcelona_LaLiga_Best_XI:86; Barcelona_LaLiga_Best_XI:96; Barcelona_LaLiga_Best_XI:108; Barcelona_LaLiga_Best_XI:117 |
| Ligue1_UNFP_Best_XI | 5 | Ligue1_UNFP_Best_XI:117; Ligue1_UNFP_Best_XI:118; Ligue1_UNFP_Best_XI:119; Ligue1_UNFP_Best_XI:120; Ligue1_UNFP_Best_XI:121 |
| Bundesliga_Elf_des_Jahres | 2 | Bundesliga_Elf_des_Jahres:116; Bundesliga_Elf_des_Jahres:119 |
| Serie_A_Capocannoniere | 2 | Serie_A_Capocannoniere:32; Serie_A_Capocannoniere:33 |
| Serie_A_Team_of_Year | 2 | Serie_A_Team_of_Year:112; Serie_A_Team_of_Year:122 |
| Bundesliga_VDV_Newcomer | 1 | Bundesliga_VDV_Newcomer:33 |
| Golden_Shoe | 1 | Golden_Shoe:32 |
| Ligue1_UNFP_MVP | 1 | Ligue1_UNFP_MVP:12 |
| PL_PFA_Young_POTY | 1 | PL_PFA_Young_POTY:12 |
| Premier_League_PFA_POTY | 1 | Premier_League_PFA_POTY:12 |

## 完整交付

- 網站「優先核對」涵蓋全部項目，支援優先級／類別／姓名／ID／期間搜尋及來源展開。
- [全部核對明細 JSON](dist/honour-review.json)：包含原始獎項、候選依據、俱樂部引用、失效對照及證據指紋。
- [全部核對清單 CSV](dist/honour-review.csv)：適合排序與分工。
- 瀏覽器筆記僅存於本機；狀態不表示主檔已修正。帶筆記的 JSON 可由網站匯出。
- 核對完成後仍需在新版 Master 明確採用正確身分或更正來源，再重新建置；不能將候選清單當正式數據。
