"""Evidence-led work queue. Candidate evidence never changes accepted identities."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from evidence import reference, value
from resolver import normalise


def integrate_honour_review(archive, payload):
    people = {p['id']: p for p in payload['people']['players']}
    aliases = defaultdict(lambda: defaultdict(list))
    for r in archive.q('SELECT * FROM Player_Dim ORDER BY _row'):
        for field in ('Canonical_Display_Name', 'Alias_Name'):
            name = value(r.get(field))
            if name and r['Player_ID'] in people:
                aliases[normalise(name)][r['Player_ID']].append(dict(name=name, field=field,
                    evidence=reference(sheet='Player_Dim',row=r['_row'],status=r.get('Verification_Status'))))
    suggestions = {r['raw']: r.get('candidates', []) for r in payload['resolution']['items']}
    groups = defaultdict(list)
    for facts in payload['honours']['catalogueFacts'].values():
        for f in facts:
            if not f['resolved'] and f.get('actorKind') != 'coach':
                groups[f['player'] or '來源未填姓名'].append(f)
    queue = []

    def entry(kind, key, title, priority, reason, count, evidence, **extra):
        item=dict(id=kind+'-'+sha256(key.encode()).hexdigest()[:14], kind=kind, title=title,
            priority=priority, reason=reason, count=count, evidence=evidence, **extra)
        queue.append(item)
        return item

    for raw, facts in groups.items():
        exact = aliases.get(normalise(raw), {})
        candidates = [dict(id=pid,name=people[pid]['name'],route='受控別名正規化完全相同',
                           evidence=refs, reasons=['僅比較簡繁、大小寫與分隔符；沒有以近似分數確認身分'])
                      for pid,refs in sorted(exact.items())]
        if not candidates:
            candidates = [dict(id=c['id'],name=c['name'],route='近似候選，尚未確認',
                               evidence=[],reasons=c.get('reasons',[])) for c in suggestions.get(raw, [])[:5]]
        counts=Counter(f['kind'] for f in facts)
        priority = 'P1' if counts['winner'] or len(facts)>=5 or len(exact)==1 else 'P2'
        evidence=[dict(f['primary'], factKey=f['key']) for f in facts]
        item=entry('player',raw,raw,priority,
            '個人頁尚未計入得獎紀錄' if counts['winner'] else '影響至少五列獎項' if len(facts)>=5 else
            '已有唯一受控別名線索' if len(exact)==1 else '未唯一綁定的個人榮譽',len(facts),evidence,
            view='honours', candidates=candidates, candidateIds=[c['id'] for c in candidates],
            counts={k:counts[k] for k in ['winner','selection','placing']},
            periods=sorted({f['periodDisplay'] or f['season'] for f in facts},reverse=True),
            clubs=sorted({f['club'] for f in facts if f['club']}), facts=facts,
            status='既有別名可核對' if len(exact)==1 else '同名多身分，須判別' if len(exact)>1 else '需新增主檔證據',
            recommendation='逐列核對原名、期間與俱樂部後，由主檔採用既有 ID；網站尚未因此增加得獎。' if len(exact)==1 else
            '取得同期球員檔案或明確受控別名；不得只按近似姓名採用。',
            proposal=dict(playerId=next(iter(exact)),mode='REVIEW_ONLY_NOT_ADOPTED') if len(exact)==1 else None)

    for d in payload['clubs']['duplicates']:
        refs=[]
        ids=[m['id'] for m in d['members']]
        for r in archive.q('SELECT * FROM Club_Dim ORDER BY _row'):
            if r['Club_ID'] in ids:
                refs.append(reference(sheet='Club_Dim',row=r['_row'],status=r.get('Verification_Status')))
        count=sum(m['rows'] for m in d['members'])
        entry('club',d['key'],d['key'], 'P0' if d['bothCarryData'] else 'P2',
            '多個 Club_ID 均承載資料，合併前需核對引用' if d['bothCarryData'] else '受控俱樂部身分可能重複',
            count,refs,view='clubs',status='需主檔指定主 ID',members=d['members'],
            recommendation='核對各 ID 的來源、球隊級別及歷年身份；確認主 ID 與轉向關係後才遷移引用。',
            countScope='各 Club_ID 的引用列數合計；跨 ID 可能重疊，不是比賽場數')

    for t in payload['history']['tournaments']:
        for issue in t['groupIssues']:
            refs=issue['records']
            rows=[payload['reference']['tables'][r['sheet']]['rows'] for r in refs]
            evidence=[]
            for r,records in zip(refs,rows):
                row=next(x for x in records if x['row']==r['row'])
                evidence.append(row['source'])
            entry('tournament',t['id']+'|'+issue['team'],f"{t['period']} {issue['team']}",'P0',
                '同隊在同屆賽事出現在多個小組',len(refs),evidence,view='tournaments',selection=t['id'],
                groups=issue['groups'],status='來源直接矛盾',
                recommendation='回查對應分組截圖或原始文字，確認兩列的球隊名稱；不自行刪除任何一列。')

    stale=defaultdict(list)
    for issue in payload['people']['awardCoverage']['identityIssues']:
        stale[issue['sheet']].append(issue)
    maps=archive.q('SELECT * FROM Record_Identity_Map ORDER BY _row')
    for sheet,issues in stale.items():
        unique={(str(i['row']),i['name'],i['period']):i for i in issues}
        details=[]
        for (row,name,period),i in unique.items():
            old=[dict(id=r['Entity_ID'],name=r['Raw_Display_Name'],period=r['Period_ID'],
                      evidence=reference(sheet='Record_Identity_Map',row=r['_row'])) for r in maps
                 if r['Origin_Sheet']==sheet and str(r['Origin_Row'])==row and r['Entity_Role']=='Player']
            details.append(dict(row=row,name=name,period=period,old=old,evidence=reference(sheet=sheet,row=row)))
        entry('mapping',sheet,sheet,'P1','舊列號對照的姓名／期間與來源列不符',len(unique),
            [d['evidence'] for d in details],view='reference',selection=sheet,details=details,
            status='網站已拒用，主檔待修',recommendation='以來源列現有姓名及期間重建對照，不能只移動列號；網站已避免使用不符的舊 ID。')

    for f in payload['integrity']['findings']:
        if f['status'] in ('review','source_limit') and f['id'] not in ('club-duplicates','tournament-duplicate','unresolved-awards'):
            if f['view']=='resolve':continue # already expanded as individual award cases
            count = payload['clubs']['unresolvedRows'] if f['view']=='clubs' else payload['competitions']['unresolvedRows'] if f['view']=='comps' else f['count']
            entry('source',f['id'],f['title'],'P2',f['detail'],count,f['evidence'],view=f['view'],
                status='需新增來源' if f['status']=='source_limit' else '待核對',recommendation=f['action'],countScope='原完整性檢查的引用／缺值數，不與獎項列數相加')
    queue.sort(key=lambda r:(r['priority'],-r.get('counts',{}).get('winner',0),-r['count'],r['title']))
    for item in queue:
        item['fingerprint']=sha256(json.dumps(item,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    payload['honourReview']=dict(items=queue,priorities=dict(Counter(r['priority'] for r in queue)),
        unresolvedFacts=sum(len(fs) for fs in groups.values()),rawNames=len(groups),
        aliasProposals=sum(bool(r.get('proposal')) for r in queue),
        policy='P0：直接來源矛盾或多 ID 均有資料。P1：漏掛得獎、至少五列獎項、唯一既有別名線索、失效對照。P2：其餘缺口。相同優先級依得獎列數、影響列數排序。優先級不是身分信心；不同類別的影響數不能相加。')
    return payload
