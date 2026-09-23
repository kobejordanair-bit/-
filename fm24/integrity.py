"""Actionable integrity checks, distinct from the workbook's issue history."""
from collections import Counter, defaultdict
from data_rules import ISSUE_BUCKETS, collective_host, host_parts, issue_bucket, source_value, transfer_direction
from evidence import reference
from resolver import ClubResolver, IdentityResolver, normalise


def report(archive):
    q = archive.q
    issues = q('SELECT * FROM Data_Issues ORDER BY _row')
    facts = q('SELECT * FROM Canonical_Award_Facts ORDER BY _row')
    unresolved = [r for r in facts if not source_value(r['Player_ID'])]
    buckets = Counter(issue_bucket(r['Status']) for r in issues)
    domains = Counter(r['Domain'] or '未分類' for r in issues)
    findings = []

    def add(key, title, status, severity, table, detail, rows=(), action='', view='reference', samples=()):
        findings.append(dict(id=key, title=title, status=status, severity=severity, where=table,
            detail=detail, count=len(rows), action=action, view=view, sample=list(samples),
            evidence=[reference(r.get('Source_ID'), table, r['_row'],
                       r.get('Status') or r.get('Verification_Status')) for r in rows]))

    world = archive.world()
    groups = world['snapshots']
    multi = {k:v for k,v in groups.items() if len(v)>1}
    paired = sum(any(s['state']=='final' for s in v) and any(s['state']=='provisional' for s in v)
                 for v in multi.values())
    add('snapshots', '積分榜快照選取與狀態', 'handled', 'low', 'Domestic_League_Standings',
        f'{len(multi)} 組聯賽賽季有多份快照，其中只有 {paired} 組同時明示季中與季末。'
        '網站優先選最新正式季末表，否則選最新觀測；未標註與狀態混合不再冒充季中。',
        action='查看保留的全部快照', view='leagues', samples=list(multi))

    superseded = q("SELECT * FROM Player_Club_Season_Totals WHERE COALESCE(Statistical_Adoption_Status,'') != 'ADOPTED'")
    add('superseded', '非正式採用的逐季觀測', 'handled', 'low', 'Player_Club_Season_Totals',
        f'{len(superseded)} 列保留原始證據，巴薩逐季統計僅讀明示 ADOPTED 的列，未知狀態不自動採用。',
        superseded, '查看逐季核對與保留觀測', 'squad')

    transfers = q('SELECT * FROM Barcelona_Transfers')
    unknown = [r for r in transfers if not transfer_direction(r['Direction'])]
    add('directions', '轉會方向正規化', 'review' if unknown else 'handled', 'medium' if unknown else 'low',
        'Barcelona_Transfers', f'{len(transfers)} 列依轉入／IN、轉出／OUT 分組；{len(unknown)} 列方向未知。'
        '原文保留；未知方向獨立展示，不默認為轉出。', unknown, '查看巴薩賽季', 'seasons')

    standings = q('SELECT * FROM Domestic_League_Standings')
    nulls = [r for r in standings if any(r[k]=='NULL' for k in ('Qualification_Raw','Info_Raw'))]
    add('nulls', 'NULL 字串與缺值', 'handled', 'low', 'Domestic_League_Standings',
        f'{len(nulls)} 列資格／註記含 NULL 字串，顯示為未知；身分積欠排除 NULL，來源資料仍保留。',
        action='查看積分榜', view='leagues')
    bangs = [r for r in standings if r['Qualification_Raw']=='!']
    tables = defaultdict(list)
    for r in standings: tables[(r['Competition_Raw'],r['Season'],r['Snapshot'])].append(r)
    invalid = [r for rs in tables.values() for r in rs if r['Qualification_Raw']=='!'
               and int(r['Rank']) < max(int(x['Rank']) for x in rs)-2]
    add('relegation', '降級符號保留', 'review' if invalid else 'handled', 'medium' if invalid else 'low',
        'Domestic_League_Standings', f'{len(bangs)} 列驚嘆號保留並顯示降級，{len(invalid)} 列不在該快照最後三名。'
        '文字資格與原始註記均保留。', invalid, '查看積分榜', 'leagues')

    clubs = archive.clubs()
    duplicates = clubs['duplicates']
    add('club-duplicates', '俱樂部重複身分待主檔核對', 'review', 'high', 'Club_Dim',
        f'{len(duplicates)} 組名稱正規化後相近或相同，需確認主 ID 與轉向關係。'
        '相同別名若命中多個 ID，網站不再任選第一個；不因移除綴詞就改寫主檔身分。',
        action='核對重複身分及資料列', view='clubs', samples=[d['key'] for d in duplicates])
    add('club-missing', '俱樂部參照尚無唯一受控身分', 'review', 'medium', 'Club_Dim',
        f"{len(clubs['unresolved'])} 個原始字串、{clubs['unresolvedRows']} 次參照仍需核對，"
        '包含未建檔、截斷或多個 ID 的情況；相似候選不是已確認身分。',
        action='查看逐項候選與出處', view='clubs', samples=[r['raw'] for r in clubs['unresolved'][:8]])

    competitions = archive.competitions()
    add('competition-missing', '賽事名稱尚未受控', 'review', 'medium', 'Competition_Dim',
        f"{len(competitions['unresolved'])} 個名稱、{competitions['unresolvedRows']} 次參照待核對；"
        f"{len(competitions['clusters'])} 組是相似寫法候選，不當成已證實同一賽事。"
        '新增賽事或別名需主檔建立正式 ID；網站保留原文與候選。',
        action='核對賽事與層級', view='comps')
    add('categories', '出賽分類與賽事身分分開', 'handled', 'low', 'Player_Club_Competition_Stats',
        f"{competitions['categoryRows']} 列中英文出賽分類已依分類鍵合併展示，不當成待建賽事。",
        action='查看分類對照', view='comps')

    hosts = q('SELECT * FROM Intl_Tournament_Results')
    separated = [r for r in hosts if host_parts(r['Host'])[1]]
    add('host-venue', '主辦地與場館分開顯示', 'handled', 'low', 'Intl_Tournament_Results',
        f'{len(separated)} 列以分號明確分隔的主辦地與場館已分欄；原始全文仍在來源核對中保留。'
        '若原文國家與球場地理不一致，網站不自行更正。', separated, '查看世界總覽', 'world')
    nations = q('SELECT * FROM Nation_Dim')
    collective = [r for r in nations if collective_host(r['Canonical_Display_Name'])]
    add('cohosts', '多國主辦不是國家隊身分', 'handled', 'low', 'Nation_Dim',
        f'{len(collective)} 個多國主辦描述已排除於國家／地區身分數，原始 ID 保留於主檔。'
        '未推測是哪幾個國家，也未刪除來源列。', collective, samples=[r['Canonical_Display_Name'] for r in collective])

    missing = [r for r in q('SELECT * FROM Barcelona_Season_Master')
               if not source_value(r['LaLiga_GF']) or not source_value(r['LaLiga_GA'])]
    add('season-gaps', '賽季主表的進失球缺值', 'source_limit', 'low', 'Barcelona_Season_Master',
        f'{len(missing)} 季的 GF 或 GA 未提供；依主檔逐欄採用限制保留未知。'
        '積分榜旁證可查閱，但不越過採用政策回填主表。', missing,
        '查看賽季欄位來源及採用範圍', 'seasons', [r['Season'] for r in missing])

    # Only exact normalized aliases accepted in the Master are offered as links.
    resolver = IdentityResolver(archive.con)
    alias_matches = []
    for r in unresolved:
        ids = resolver.index.get(normalise(r['Player_Raw']),set())
        if len(ids)==1 and next(iter(ids)) in resolver.canonical:
            pid=next(iter(ids))
            alias_matches.append(dict(row=r['_row'], name=r['Player_Raw'], playerId=pid,
                canonical=resolver.canonical[pid], award=r['Award'], season=r['Season'],
                evidence=reference(r['Source_ID'],'Canonical_Award_Facts',r['_row']),
                basis='既有主檔別名正規化後唯一相同；僅提供核對連結，未改寫正式事實 Player_ID'))
    add('player-missing', '獎項球員身分待主檔採用', 'review', 'medium', 'Canonical_Award_Facts',
        f'{len(unresolved)} 筆正式事實未綁定 Player_ID，其中 {len(alias_matches)} 筆可唯一對應既有受控別名。'
        '提供球員核對入口；未憑音譯相似度替其餘球員建 ID，也未增加獎項次數。',
        action='查看球員身分候選', view='resolve')

    group_rows=q('SELECT * FROM National_Tournament_Groups')
    by_team=defaultdict(list)
    for r in group_rows:
        if source_value(r['Team_Raw']): by_team[(r['Source_ID'],normalise(r['Team_Raw']))].append(r)
    repeated=[rs for rs in by_team.values() if len({r['Group_Raw'] for r in rs})>1]
    if repeated:
        add('tournament-duplicate', '同屆賽事同隊出現在多個分組', 'review', 'high', 'National_Tournament_Groups',
            f'{len(repeated)} 組需回查原始分組來源，網站保留全部觀測，不擅自替換國家或分組。',
            [r for rs in repeated for r in rs], '查看國際賽程', 'tournaments',
            [f"{rs[0]['Period']} {rs[0]['Team_Raw']}" for rs in repeated])

    statuses=Counter(f['status'] for f in findings)
    names=Counter(r['Player_Raw'] for r in unresolved)
    sheet_names=defaultdict(set)
    for r in unresolved: sheet_names[r['Player_Raw']].add(r['Origin_Sheet'] or '')
    findings.sort(key=lambda f: ({'review':0,'source_limit':1,'handled':2}[f['status']],
                                {'high':0,'medium':1,'low':2}[f['severity']],f['id']))
    return dict(issueTotal=len(issues),domains=[dict(domain=k,count=v) for k,v in domains.most_common()],
        issueBuckets=[dict(status=k,label=label,count=buckets[k]) for k,label in ISSUE_BUCKETS.items()],
        issueStatuses=[dict(status=k,count=v) for k,v in Counter(r['Status'] for r in issues).most_common()],
        issueRows=[dict(row=r['_row'],bucket=issue_bucket(r['Status']),
            values={k:source_value(v) for k,v in r.items() if k!='_row'},
            source=reference(r['Source_ID'],'Data_Issues',r['_row'],r['Status'])) for r in issues],
        resolution=[dict(status=k,count=v) for k,v in Counter(r['Resolution_Status'] for r in q('SELECT * FROM Award_Resolution_Status')).most_common()],
        unresolvedAwards=len(unresolved),totalAwards=len(facts),
        topUnresolved=[dict(name=k,count=v,sheets=', '.join(sorted(sheet_names[k]))) for k,v in names.most_common(25)],
        aliasMatches=alias_matches, findings=findings,
        findingCounts={k:statuses[k] for k in ('review','source_limit','handled')})
