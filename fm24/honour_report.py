"""Export the same evidence queue shown in the site; never writes source data."""
from pathlib import Path
import csv
import json


def export_reports(base):
    data=json.loads((base/'dist/fm24-data.json').read_text(encoding='utf-8'))
    review=data['honourReview']
    rows=review['items']
    def refs(es):
        return '; '.join(dict.fromkeys(f"{e['sheet']}:{e['row']}" for e in es))
    def cell(s):
        return str(s).replace('|','\\|').replace('\n',' ')
    report=dict(schema='fm24-review-report-v1',mode='REVIEW_ONLY_NOT_ADOPTED',master='v6.4.0',
                generated=data['meta']['generated'],policy=review['policy'],items=rows)
    (base/'dist/honour-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (base/'dist/honour-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['優先','類別','項目','影響列或引用','狀態','原因','建議','證據位置'])
        for r in rows:
            vals=[r['priority'],r['kind'],r['title'],r['count'],r['status'],r['reason'],r['recommendation'],refs(r['evidence'])]
            writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in vals])
    lines=['# 高影響資料缺口核對報告','',f"建置日期：{data['meta']['generated']}；依目前 Master v6.4.0 及網站相同明細重新核對。",
        '',f"共 {len(rows)} 項："+'、'.join(f'{k} {v} 項' for k,v in sorted(review['priorities'].items()))+'。',
        '',review['policy'],'',
        '本輪完成來源定位、失效對照核對及優先級整理；以下主檔矛盾尚未擅自修正。不同類別的影響數不可相加，也不是可新增的獎盃數。',
        '', '## P0：直接矛盾與俱樂部多 ID','']
    for r in rows:
        if r['priority']!='P0':continue
        lines += [f"### {r['title']}",'',r['reason'], '',f"影響：{r['count']} 列／引用。證據：{refs(r['evidence'])}。"]
        if r.get('groups'): lines += ['', '矛盾分組：'+' / '.join(r['groups'])+'。']
        for m in r.get('members',[]):
            lines += [f"- {m['id']} {m['name']}：{m['rows']} 引用列；"+'；'.join(f"{t['table']} {t['n']}" for t in m['tables'])]
        lines += ['',r['recommendation'],'']
    proposals=[r for r in rows if r.get('proposal')]
    lines += ['## 已找到受控別名的十組線索','',
        f"{len(proposals)} 組、涉及 {sum(r['count'] for r in proposals)} 筆原始獎項。正規化只處理簡繁、大小寫及分隔符。以下是逐列人工核對的候選，尚未採用或增加個人榮譽。",'',
        '| 原始姓名 | 候選 ID | 原始列數 | Player_Dim 證據 | 獎項來源 |','|---|---|---:|---|---|']
    for r in proposals:
        es=[x['evidence'] for c in r['candidates'] for x in c['evidence']]
        lines += ['| '+' | '.join(map(cell,[r['title'],r['proposal']['playerId'],r['count'],refs(es),refs(r['evidence'])]))+' |']
    lines += ['', '## 其他優先核對：得獎影響最大的前十組','',
        '| 原始姓名 | 得獎列 | 入選列 | 其他名次列 | 期間 | 證據 |','|---|---:|---:|---:|---|---|']
    for r in [r for r in rows if r['priority']=='P1' and r['kind']=='player'][:10]:
        c=r['counts']
        lines += ['| '+' | '.join(map(cell,[r['title'],c['winner'],c['selection'],c['placing'],'、'.join(r['periods']),refs(r['evidence'])]))+' |']
    lines += ['', '## 失效列號對照','',
        '現有來源列的姓名／期間與 Record_Identity_Map 舊對照不符。網站已拒用；JSON 與工作台保留兩側姓名、期間、ID 及列號，可逐列回查。','',
        '| 來源表 | 不符列數 | 來源列 |','|---|---:|---|']
    for r in rows:
        if r['kind']=='mapping': lines += [f"| {r['title']} | {r['count']} | {refs(r['evidence'])} |"]
    lines += ['', '## 完整交付','',
        '- 網站「優先核對」涵蓋全部項目，支援優先級／類別／姓名／ID／期間搜尋及來源展開。',
        '- [全部核對明細 JSON](dist/honour-review.json)：包含原始獎項、候選依據、俱樂部引用、失效對照及證據指紋。',
        '- [全部核對清單 CSV](dist/honour-review.csv)：適合排序與分工。',
        '- 瀏覽器筆記僅存於本機；狀態不表示主檔已修正。帶筆記的 JSON 可由網站匯出。',
        '- 核對完成後仍需在新版 Master 明確採用正確身分或更正來源，再重新建置；不能將候選清單當正式數據。','']
    (base/'PRIORITY_REVIEW.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f"Exported {len(rows)} cases; {len(proposals)} controlled-alias leads / {sum(r['count'] for r in proposals)} source facts")


if __name__=='__main__':
    export_reports(Path(__file__).resolve().parent)
