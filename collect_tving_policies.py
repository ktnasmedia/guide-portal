#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""티빙 심사 가이드(GitBook) 자동 수집 → tving_ad_policies.json

- 원문: https://tvingads.gitbook.io/guide/operations-guide/ad-policies.md
- 업종 단위로 구간을 잘라 저장하고, 이전 수집분과 비교해 실제 변경이 있을 때만
  updated_at 을 갱신한다. 오탈자·띄어쓰기 수준의 미세 변경은 무시한다.
- 화면에 쓸 한 줄 발췌(highlight)는 원문에서 '그대로' 가져온다. 요약 생성 없음.
"""

import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

SRC_URL = 'https://tvingads.gitbook.io/guide/operations-guide/ad-policies.md'
PAGE_URL = 'https://tvingads.gitbook.io/guide/operations-guide/ad-policies'
OUT = 'tving_ad_policies.json'

# 미세 변경 판정: 정규화 후 유사도가 이 값 이상이고 항목 수가 같으면 '변경 없음'
SIM_THRESHOLD = 0.98

KST = timezone(timedelta(hours=9))


def today():
    return datetime.now(KST).strftime('%Y-%m-%d')


# ────────────────────────────── 텍스트 정리 ──────────────────────────────

def clean_inline(s):
    """마크다운/기트북 고유 마크업을 걷어내고 사람이 읽는 문장만 남긴다."""
    s = re.sub(r'<a\s+href="#[^"]*"[^>]*></a>', '', s)
    s = re.sub(r'</?mark[^>]*>', '', s)
    s = re.sub(r'</?strong>', '', s)
    s = s.replace('&#x20;', ' ').replace('&amp;', '&')
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'\1', s)   # 링크 → 텍스트
    s = s.replace('\\[', '[').replace('\\]', ']')
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', s)
    s = re.sub(r'<br\s*/?>', ' ', s)
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_for_hash(s):
    """해시 비교용 정규화 — 마크업/공백/문장부호 흔들림 제거."""
    s = clean_inline(s)
    s = re.sub(r'[\s·ㆍ,.、]', '', s)
    return s


def count_items(block):
    """불릿/번호 항목 개수 — 구조가 바뀌었는지 판단하는 보조 지표."""
    n = 0
    for ln in block.split('\n'):
        t = ln.strip()
        if t.startswith('* ') or t.startswith('- ') or re.match(r'^\d+\.\s', t):
            n += 1
    return n


# ────────────────────────────── 구간 분리 ──────────────────────────────

def slice_between(md, start_anchor, end_anchors):
    """앵커 id 기준으로 구간을 잘라낸다."""
    m = re.search(r'^#{2,4}[^\n]*id="%s"[^\n]*$' % re.escape(start_anchor), md, re.M)
    if not m:
        return None
    start = m.end()
    end = len(md)
    for a in end_anchors:
        m2 = re.search(r'^#{2,4}[^\n]*id="%s"[^\n]*$' % re.escape(a), md[start:], re.M)
        if m2:
            end = min(end, start + m2.start())
    return md[start:end].strip()


def parse_prohibited(block):
    """금지(불가) 업종 — 최상위 불릿이 업종, 하위 불릿이 예외/단서."""
    out = []
    cur = None
    for ln in block.split('\n'):
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        t = ln.strip()
        if not t.startswith('*'):
            continue
        body = t[1:].strip()
        if indent == 0:
            if cur:
                out.append(cur)
            cur = {'name': clean_inline(body), 'notes': []}
        elif cur is not None:
            cur['notes'].append(clean_inline(body))
    if cur:
        out.append(cur)
    return [v for v in out if v['name']]


SENT_END = re.compile(r'(다|요)\.?$')


def extract_highlight(block):
    """원문에서 핵심 문장을 '발췌'한다. 생성하지 않는다.
    우선순위: <mark> 강조 → 굵은 글씨 문장 → (없으면 빈 값)
    """
    picks = []
    for m in re.finditer(r'<mark[^>]*>(.+?)</mark>', block, re.S):
        t = clean_inline(m.group(1))
        if t:
            picks.append(t)
    if picks:
        return picks, 'mark'

    for m in re.finditer(r'\*\*(.+?)\*\*', block, re.S):
        t = clean_inline(m.group(1))
        # 소제목 라벨(예: '금융 공통')이 아니라 서술 문장만 채택
        if len(t) >= 12 and SENT_END.search(t):
            picks.append(t)
    if picks:
        return picks, 'bold'

    return [], 'none'


def extract_subsections(block):
    """하위 소제목(예: 금융 공통 / 대출 / 보험 …) — 발췌 실패 시 대체 표시용."""
    subs = []
    for ln in block.split('\n'):
        t = ln.strip()
        m = re.match(r'^\*\s+\*\*(.+?)\*\*\s*$', t)
        if m:
            name = clean_inline(m.group(1))
            if name and not SENT_END.search(name):
                subs.append(name)
    return subs


def parse_restricted(block):
    """제한 업종 — '#### **1. 주류**' 단위로 분리."""
    heads = list(re.finditer(r'^####\s+\*\*(\d+)\.\s*(.+?)\*\*\s*$', block, re.M))
    out = []
    for i, h in enumerate(heads):
        start = h.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(block)
        body = block[start:end].strip()
        hi, how = extract_highlight(body)
        out.append({
            'no': int(h.group(1)),
            'name': clean_inline(h.group(2)),
            'highlight': hi,
            'highlight_from': how,
            'subsections': extract_subsections(body),
            'raw_md': body,
            'hash': hashlib.sha256(norm_for_hash(body).encode('utf-8')).hexdigest()[:16],
            'items': count_items(body),
        })
    return out


# ────────────────────────────── 변경 감지 ──────────────────────────────

def changed(prev, cur):
    """실질 변경 여부. 미세 수정은 False."""
    if prev is None:
        return False                      # 최초 구축 → 일자 비움
    if prev.get('hash') == cur.get('hash'):
        return False
    if prev.get('items') != cur.get('items'):
        return True                       # 항목 수가 달라졌으면 구조 변경
    a = norm_for_hash(prev.get('raw_md', ''))
    b = norm_for_hash(cur.get('raw_md', ''))
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio < SIM_THRESHOLD


def merge(prev_doc, cur_doc):
    """이전 수집분의 updated_at / 수동 요약을 이어받고, 변경분만 일자 갱신."""
    prev_map = {}
    for v in (prev_doc or {}).get('restricted', []):
        prev_map[v['name']] = v

    for v in cur_doc['restricted']:
        p = prev_map.get(v['name'])
        v['manual_summary'] = (p or {}).get('manual_summary', '')
        if changed(p, v):
            v['updated_at'] = today()
            v['review_needed'] = True     # 발췌가 바뀌었을 수 있음 → 확인 표시
        else:
            v['updated_at'] = (p or {}).get('updated_at', '')
            v['review_needed'] = (p or {}).get('review_needed', False)
    return cur_doc


# ────────────────────────────── 메인 ──────────────────────────────

def build(md):
    proh = slice_between(md, 'prohibited-verticals', ['restricted-verticals'])
    rest = slice_between(md, 'restricted-verticals', [])
    if proh is None or rest is None:
        raise RuntimeError('구간 앵커를 찾지 못함 — 원문 구조 변경 의심')
    doc = {
        'source_url': PAGE_URL,
        'collected_at': today(),
        'prohibited': parse_prohibited(proh),
        'restricted': parse_restricted(rest),
    }
    if not doc['restricted']:
        raise RuntimeError('제한 업종 파싱 결과 없음 — 원문 구조 변경 의심')
    return doc


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
        # 실패 시 기존 파일 유지 — 화면이 비지 않게
        print('수집 실패:', e, file=sys.stderr)
        return 1 if prev is None else 0

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('저장 %s — 금지 %d개 / 제한 %d개'
          % (OUT, len(doc['prohibited']), len(doc['restricted'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
