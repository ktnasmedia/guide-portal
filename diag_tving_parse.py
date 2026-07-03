#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""티빙 특정 작품 파싱 실패 진단: 대탈출/100일의 거짓말이 왜 안 잡히나"""
import re
from bs4 import BeautifulSoup
import parse_tvingads as P

TARGETS = ["대탈출", "100일의 거짓말", "우주떡집", "로또", "포핸즈"]

html = P.fetch()
soup = BeautifulSoup(html, "html.parser")
text = soup.get_text("\n")
heads = P.extract_headings(soup)

print("=== extract_headings 결과 (제목 후보 %d개) ===" % len(heads))
for t in TARGETS:
    matches = [h for h in heads if t in str(h)]
    print("  '%s' → heads에 %s" % (t, "있음: " + str(matches) if matches else "없음"))
print()

works = P.parse_blocks(text, heads)
print("=== parse_blocks 결과 (작품 %d개) ===" % len(works))
titles = [w["title"] for w in works]
for t in TARGETS:
    found = [ti for ti in titles if t in ti]
    print("  '%s' → %s" % (t, found if found else "파싱 안 됨"))
print()

print("=== 페이지 텍스트에서 타겟 주변 ===")
for t in TARGETS:
    idx = text.find(t)
    if idx == -1:
        print("  '%s': 텍스트에 없음" % t)
        continue
    snippet = text[max(0, idx-30):idx+80].replace("\n", " | ")
    print("  '%s': ...%s..." % (t, snippet))
print()

print("=== parse_blocks가 잡은 전체 제목 ===")
for ti in titles:
    print("  -", ti)
