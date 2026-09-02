#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
넷플릭스 광고 정책 자동 수집.

원천 2곳
  ① 광고 정책          https://help.netflix.com/ko/legal/ads-policy      → 기본(공통) 탭
  ② 제한된 광고 카테고리  https://help.netflix.com/ko/legal/ad-restrictions → 업종 탭

구조: 넷플릭스 헬프센터는 제목 태그(h2/h3)를 쓰지 않고
      <label> 안의 <p class="export-block__parent"> 가 섹션 제목,
      그 뒤 detail 영역이 본문인 '접었다 펴는' 구조다.
      제목이 굵은 글씨로 한 겹 더 감싸인 경우가 있어 태그를 벗겨내고 읽는다.

티빙 수집기(collect_tving_policies.py)와 같은 원칙
  · 해시 + 유사도로 실질 변경만 감지 (미세 수정 무시)
  · 실패하면 기존 파일을 그대로 두어 화면이 비지 않게 함
  · 이전 수집분의 updated_at / manual_summary 를 이어받음
  · 변경분은 policy_changes.md 에 이전·이후 전문을 남김 (최신이 맨 위)
"""
import os
import re
import sys
import json
import hashlib
import difflib
import urllib.request
from datetime import datetime, timezone, timedelta

POLICY_URL = 'https://help.netflix.com/ko/legal/ads-policy'
RESTRICT_URL = 'https://help.netflix.com/ko/legal/ad-restrictions'
OUT = 'netflix_ad_policies.json'
CHANGELOG = 'policy_changes.md'
KST = timezone(timedelta(hours=9))

UA = 'Mozilla/5.0 (compatible; guide-portal-policy-collector/1.0)'

# 섹션 제목: <label> 안 첫 export-block__parent
TITLE_RE = re.compile(
    r'<label[^>]*>.*?<p class="export-block__parent">(.*?)</p>', re.S)
LABEL_SPLIT = re.compile(r'(?=<label[^>]*>)')


def today():
    return datetime.now(KST).strftime('%Y-%m-%d')


def strip_tags(html):
    """태그를 줄바꿈으로 바꾸고 텍스트만 남긴다."""
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'</(p|div|li|h\d)>', '\n', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = (t.replace('&nbsp;', ' ').replace('&amp;', '&')
          .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    lines = [x.strip() for x in t.split('\n')]
    return [x for x in lines if x]


def norm_for_hash(s):
    """공백·기호 차이를 무시한 비교용 문자열."""
    return re.sub(r'\s+', '', re.sub(r'[·•\-–—*_]', '', s or ''))


def sec_hash(lines):
    return hashlib.sha256(
        norm_for_hash('\n'.join(lines)).encode('utf-8')).hexdigest()[:16]


def parse_sections(html):
    """<label> 단위로 잘라 제목과 본문을 뽑는다."""
    out = []
    for part in LABEL_SPLIT.split(html):
        m = TITLE_RE.search(part)
        if not m:
            continue
        name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not name or len(name) > 60:
            continue
        lines = strip_tags(part)
        # 첫 줄은 제목 자신이므로 제외
        body = [x for x in lines[1:] if x != name]
        if not body:
            continue
        out.append({
            'name': name,
            'lines': body,
            'hash': sec_hash(body),
            'items': len(body),
        })
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'ko-KR,ko;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return raw.decode('utf-8', errors='replace')


def diff_lines(prev_lines, cur_lines):
    """바뀐 줄만 골라낸다. (없어진 줄, 새로 생긴 줄)"""
    a = [norm_for_hash(x) for x in prev_lines]
    b = [norm_for_hash(x) for x in cur_lines]
    sm = difflib.SequenceMatcher(None, a, b)
    removed, added = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('replace', 'delete'):
            removed += prev_lines[i1:i2]
        if tag in ('replace', 'insert'):
            added += cur_lines[j1:j2]
    return removed, added


def changed(prev, cur):
    """실질 변경 여부.

    글자 단위 유사도만 쓰면 긴 문서에서 한 문장 변경이 묻힌다.
    (넷플릭스 제한 업종은 100줄이 넘는 항목이 많아 유사도가 0.99를 넘김)
    그래서 '바뀐 줄이 있는가'로 판단하고, 공백·기호 차이만 있는 줄은 무시한다.
    """
    if prev is None or 'lines' not in prev:
        return False                       # 최초 수집·형식 불일치 → 일자 비움
    if prev.get('hash') == cur.get('hash'):
        return False
    if prev.get('items') != cur.get('items'):
        return True                        # 줄 수가 달라졌으면 구조 변경
    removed, added = diff_lines(prev.get('lines', []), cur.get('lines', []))
    return bool(removed or added)


def merge(prev_doc, cur_doc):
    """이전 수집분의 updated_at / 수동 요약을 이어받고, 변경분만 일자 갱신."""
    changes = []
    for key in ('basic', 'restricted'):
        # 이전 파일이 이 수집기가 만든 형식이 아닐 수 있다.
        # (손으로 정리해 둔 옛 netflix_ad_policies.json 은 구조가 달랐다)
        # 형식이 다르면 비교를 포기하고 최초 수집처럼 다룬다.
        prev_list = (prev_doc or {}).get(key)
        if not isinstance(prev_list, list):
            prev_list = []
        prev_map = {v['name']: v for v in prev_list
                    if isinstance(v, dict) and 'name' in v}
        # 이전 파일이 이 수집기 형식인지 (아니면 최초 수집처럼 다룬다)
        same_format = bool(prev_map) and any(
            'lines' in v for v in prev_map.values())
        for v in cur_doc[key]:
            p = prev_map.get(v['name'])
            v['manual_summary'] = (p or {}).get('manual_summary', '')
            if changed(p, v):
                v['updated_at'] = today()
                v['review_needed'] = True
                removed, added = diff_lines(p.get('lines', []), v['lines'])
                changes.append({
                    'section': key, 'name': v['name'],
                    'before': removed, 'after': added,
                })
            else:
                v['updated_at'] = (p or {}).get('updated_at', '')
                v['review_needed'] = (p or {}).get('review_needed', False)
            # 새로 생긴 항목 — 이전 파일에 같은 구획(basic/restricted)이
            # 이 수집기 형식으로 들어 있을 때만 '새 항목'으로 본다.
            if p is None and same_format:
                changes.append({
                    'section': key, 'name': v['name'],
                    'before': [], 'after': v['lines'], 'new': True,
                })
        # 사라진 항목
        cur_names = {v['name'] for v in cur_doc[key]}
        for name, p in prev_map.items():
            if name not in cur_names:
                changes.append({
                    'section': key, 'name': name,
                    'before': p.get('lines', []), 'after': [], 'removed': True,
                })
    return cur_doc, changes


def write_changelog(changes):
    """최신이 맨 위. 이전·이후 전문을 남긴다."""
    if not changes:
        return
    head = '# 정책 원문 변경 기록\n'
    block = ['## %s · 넷플릭스\n' % today()]
    for c in changes:
        sec = '기본(공통)' if c['section'] == 'basic' else '제한 업종'
        if c.get('new'):
            block.append('- **[%s] %s** — 새 항목' % (sec, c['name']))
        elif c.get('removed'):
            block.append('- **[%s] %s** — 원문에서 사라짐' % (sec, c['name']))
        else:
            block.append('- **[%s] %s** — 문구 변경' % (sec, c['name']))
        if c['before']:
            block.append('  <details><summary>이전</summary>\n')
            block += ['  > ' + x for x in c['before']]
            block.append('\n  </details>')
        if c['after']:
            block.append('  <details><summary>이후</summary>\n')
            block += ['  > ' + x for x in c['after']]
            block.append('\n  </details>')
        block.append('')
    new_block = '\n'.join(block) + '\n'

    old = ''
    if os.path.exists(CHANGELOG):
        old = open(CHANGELOG, encoding='utf-8').read()
        if old.startswith(head):
            old = old[len(head):]
    with open(CHANGELOG, 'w', encoding='utf-8') as f:
        f.write(head + '\n' + new_block + old.lstrip('\n'))
    print('  → %s 에 변경 %d건 기록' % (CHANGELOG, len(changes)))


def build(policy_html, restrict_html):
    basic = parse_sections(policy_html)
    restricted = parse_sections(restrict_html)
    if not basic:
        raise RuntimeError('기본 정책 섹션을 찾지 못함 — 원문 구조 변경 의심')
    if not restricted:
        raise RuntimeError('제한 카테고리 섹션을 찾지 못함 — 원문 구조 변경 의심')
    return {
        'source_url': {'policy': POLICY_URL, 'restrictions': RESTRICT_URL},
        'collected_at': today(),
        'basic': basic,
        'restricted': restricted,
    }


def main():
    # 인자로 로컬 파일 두 개를 주면 그걸로 파싱 (테스트용)
    if len(sys.argv) > 2:
        p = open(sys.argv[1], encoding='utf-8').read()
        r = open(sys.argv[2], encoding='utf-8').read()
    else:
        p = fetch(POLICY_URL)
        r = fetch(RESTRICT_URL)

    prev = None
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            prev = None

    try:
        doc, changes = merge(prev, build(p, r))
    except Exception as e:
        print('수집 실패:', e, file=sys.stderr)
        return 1 if prev is None else 0    # 기존 파일 유지

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('저장 %s — 기본 %d개 / 제한 업종 %d개'
          % (OUT, len(doc['basic']), len(doc['restricted'])))
    write_changelog(changes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
