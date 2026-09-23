"""Read-side rules: preserve source values and never invent missing facts."""
import re


def source_value(raw):
    if raw is None or str(raw).strip().lower() in ('', 'null'):
        return None
    return str(raw).strip()


def snapshot_state(statuses):
    states = set()
    for raw in statuses:
        s = source_value(raw) or ''
        states.add('final' if s.startswith('FINAL') else
                   'provisional' if s.startswith('PROVISIONAL') else 'unknown')
    return next(iter(states)) if len(states) == 1 else 'mixed'


def snapshot_order(snapshot):
    # Prefer the newest final snapshot; otherwise the newest observation.
    return (snapshot['final'], snapshot.get('snapshot') or '')


def transfer_direction(raw):
    return {'轉入':'in', 'IN':'in', '轉出':'out', 'OUT':'out'}.get(source_value(raw))


def host_parts(raw):
    text = source_value(raw)
    if not text:
        return None, None
    parts = text.split('；', 1)
    return parts[0].strip(), parts[1].strip() if len(parts) == 2 else None


def collective_host(raw):
    return bool(re.fullmatch(r'(?:3|三)國(?:聯辦|聯合主辦)', source_value(raw) or ''))


ISSUE_BUCKETS = {'resolved':'主檔已處理／已確認', 'preserved':'來源限制／備註保留',
                 'review':'待核對／尚未修正'}


def issue_bucket(raw):
    s = source_value(raw) or ''
    if s.startswith(('RESOLVED;', '已解決', '已確認', '已由 schema')):
        return 'resolved'
    if s == 'PRESERVED_NOT_CORRECTED' or '人工確認' in s:
        return 'review'
    if s.startswith(('SOURCE_', '來源備註', '來源限制', '原始 EXTRACTION_ISSUES', '原始限制')):
        return 'preserved'
    # A new or blank status must not silently be declared resolved.
    return 'review'
