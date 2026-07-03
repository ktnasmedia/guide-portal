#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이미 공개된 작품(취사병 등)의 공개일이 왜 '미정'으로 되는지 진단"""
import re
from bs4 import BeautifulSoup
import parse_tvingads as P

TARGETS = ["취사병", "언더커버 셰프", "콩콩팜팜", "스트릿 레스토랑", "내일도 출근", "신입사원 강회장"]

html = P.fetch()
soup = BeautifulSoup(html, "html.parser")
text = soup.get_text("\n")
heads = P.extract_headings(soup)

works = P.parse_blocks(text, heads)
print("=== parse_blocks 결과: 타겟 작품의 공개일 ===")
for t in TARGETS:
    found = [w for w in works if t in w["title"]]
    for w in found:
        print("  '%s' → 공개일: '%s' | 매체:%s" % (w["title"], w["release_date"], "/".join(w["media"])))
    if not found:
        print("  '%s' → parse_blocks에서 못 찾음" % t)
print()

print("=== 페이지 텍스트에서 타겟 주변 200자 ===")
for t in TARGETS:
    idx = text.find(t)
    if idx == -1:
        print("  '%s': 텍스트에 없음" % t)
        continue
    snippet = text[idx:idx + 200].replace("\n", " | ")
    print("  '%s':" % t)
    print("     %s" % snippet)
    print()
