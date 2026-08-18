#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""티빙 KBO 리그 청약 정보(GitBook) 자동 수집 → tving_kbo.json

- 원문: https://tvingads.gitbook.io/guide/solution/kbo/overview.md
- 청약 일정 + 잔여 구좌 3종(월 단위 / 주 단위 / 팬덤)을 수집한다.
- 잔여 구좌는 팔릴 때마다 바뀌므로 수집 시각을 함께 기록한다.
- 마크다운 표와 HTML 표가 섞여 있어 둘 다 처리한다.
- 상태는 청약 가능 / 판매 완료 / 판매 종료 세 가지로 정규화한다.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

SRC_URL = 'https://tvingads.gitbook.io/guide/solution/kbo/overview.md'
PAGE_URL = 'https://tvingads.gitbook.io/guide/solution/kbo/overview'
OUT = 'tving_kbo.json'

KST = timezone(timedelta(hours=9))

# 원문 색 강조 → 포털 상태값
STATUS_OPEN = '청약 가능'
STATUS_SOLD = '판매 완료'
STATUS_CLOSED = '판매 종료'


def now_kst():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M')


def today():
    return datetime.now(KST).strftime('%Y-%m-%d')


# ────────────────────────── 텍스트 정리 ──────────────────────────

def clean(s):
    """기트북 마크업을 걷어내고 사람이 읽는 문장만 남긴다."""
    s = re.sub(r'<a\s+href="#[^"]*"[^>]*></a>', '', s)
    s = re.sub(r'</?(mark|strong|em|p|br)[^>]*>', ' ', s)
    s = s.replace('&#x20;', ' ').replace('&amp;', '&')
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'\1', s)
    s = s.replace('\\~', '~').replace('\\[', '[').replace('\\]', ']')
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_status(cell):
    """셀 원문에서 상태값을 뽑는다. 색 강조가 없으면 글자만 본다."""
    t = clean(cell)
    if STATUS_OPEN in t:
        return STATUS_OPEN
    if STATUS_SOLD in t:
        return STATUS_SOLD
    if STATUS_CLOSED in t:
        return STATUS_CLOSED
    return t or '-'


# ────────────────────────── 표 파서 ──────────────────────────

def parse_md_tables(block):
    """마크다운 표를 모두 찾아 [{header:[...], rows:[[...]]}] 로 돌려준다."""
    tables = []
    lines = block.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[i + 1].strip()):
            header = [clean(c) for c in ln.strip('|').split('|')]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith('|'):
                cells = lines[j].strip().strip('|').split('|')
                rows.append([c for c in cells])
                j += 1
            tables.append({'header': header, 'rows': rows})
            i = j
        else:
            i += 1
    return tables


def parse_html_table(block):
    """HTML <table> 하나를 파싱한다."""
    m = re.search(r'<table[^>]*>(.*?)</table>', block, re.S)
    if not m:
        return None
    body = m.group(1)
    header = [clean(x) for x in re.findall(r'<th[^>]*>(.*?)</th>', body, re.S)]
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if tds:
            rows.append(tds)
    return {'header': header, 'rows': rows} if rows else None


# ────────────────────────── 구간 분리 ──────────────────────────

def slice_section(md, title, next_titles):
    m = re.search(r'^#{2,3}\s*\*{0,2}%s' % re.escape(title), md, re.M)
    if not m:
        return None
    start = m.end()
    end = len(md)
    for t in next_titles:
        m2 = re.search(r'^#{2,3}\s*\*{0,2}%s' % re.escape(t), md[start:], re.M)
        if m2:
            end = min(end, start + m2.start())
    return md[start:end]


def parse_schedule(block):
    """청약 일정 — '* 5월 청약 : 4/15(수)' 형식"""
    out = []
    for ln in block.split('\n'):
        t = ln.strip()
        if not t.startswith('*') or t.startswith('**'):
            continue
        v = clean(t[1:])
        m = re.match(r'^(\d+월)\s*청약\s*[:：]\s*(.+)$', v)
        if m:
            out.append({'month': m.group(1), 'open_date': m.group(2).strip()})
    note = ''
    mn = re.search(r'\(([^)]*오전[^)]*)\)', block)
    if mn:
        note = clean(mn.group(1))
    return out, note


def build_status_table(tbl, label, first_col_name):
    """표 하나를 {columns, rows} 형태로 정규화."""
    if not tbl:
        return None
    cols = tbl['header'][1:]
    rows = []
    for r in tbl['rows']:
        if not r:
            continue
        name = clean(r[0])
        if not name:
            continue
        cells = {}
        for idx, c in enumerate(cols):
            cells[c] = norm_status(r[idx + 1]) if idx + 1 < len(r) else '-'
        rows.append({'name': name, 'status': cells})
    if not rows:
        return None
    return {'label': label, 'first_col': first_col_name or tbl['header'][0], 'columns': cols, 'rows': rows}


# ────────────────────────── 조립 ──────────────────────────

def build(md):
    sec_sched = slice_section(md, '2026 KBO 청약일정', ['구좌형 상품 잔여 구좌 안내'])
    if sec_sched is None:
        sec_sched = slice_section(md, 'KBO 청약일정', ['구좌형 상품 잔여 구좌 안내'])
    sec_month = slice_section(md, '월 단위 상품', ['주 단위 상품', 'KBO 팬덤'])
    sec_week = slice_section(md, '주 단위 상품', ['KBO 팬덤'])
    sec_fan = slice_section(md, 'KBO 팬덤', [])

    if sec_month is None or sec_week is None or sec_fan is None:
        raise RuntimeError('구간 제목을 찾지 못함 — 원문 구조 변경 의심')

    schedule, sched_note = parse_schedule(sec_sched or '')

    monthly = build_status_table(
        (parse_md_tables(sec_month) or [None])[0], '월 단위 상품', '청약월')

    weekly = []
    for t in parse_md_tables(sec_week):
        w = build_status_table(t, t['header'][0], t['header'][0])
        if w:
            weekly.append(w)

    fandom = build_status_table(parse_html_table(sec_fan), 'KBO 팬덤', '구분')

    doc = {
        'source_url': PAGE_URL,
        'collected_at': now_kst(),
        'schedule': schedule,
        'schedule_note': sched_note,
        'monthly': monthly,
        'weekly': weekly,
        'fandom': fandom,
    }
    if not (monthly and weekly and fandom):
        raise RuntimeError('표 파싱 결과가 비었음 — 원문 구조 변경 의심')

    payload = json.dumps(
        {k: doc[k] for k in ('schedule', 'monthly', 'weekly', 'fandom')},
        ensure_ascii=False, sort_keys=True)
    doc['hash'] = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
    return doc


def merge(prev, cur):
    """내용이 실제로 바뀐 경우에만 갱신 일자를 찍는다."""
    if prev and prev.get('hash') == cur.get('hash'):
        cur['updated_at'] = prev.get('updated_at', '')
        cur['changed'] = False
    else:
        cur['updated_at'] = today()
        cur['changed'] = bool(prev)
    return cur


def fetch(url):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'guide-portal-collector'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


def main():
    local = sys.argv[1] if len(sys.argv) > 1 else None
    md = open(local, encoding='utf-8').read() if local else fetch(SRC_URL)

    prev = None
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            prev = None

    try:
        doc = merge(prev, build(md))
    except Exception as e:
        print('수집 실패:', e, file=sys.stderr)
        return 1 if prev is None else 0

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print('저장 %s — 일정 %d개 / 월 단위 %d행 / 주 단위 %d표 / 팬덤 %d행 %s'
          % (OUT, len(doc['schedule']), len(doc['monthly']['rows']),
             len(doc['weekly']), len(doc['fandom']['rows']),
             '(변경 감지)' if doc.get('changed') else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
