#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""취사병 블록이 실제로 어떻게 나뉘고 parse_one이 날짜를 어떻게 처리하는지 진단"""
from bs4 import BeautifulSoup
import parse_tvingads as P

html = P.fetch()
soup = BeautifulSoup(html, "html.parser")
text = soup.get_text("\n")
heads = P.extract_headings(soup)

lines = [l.strip() for l in text.split("\n") if l.strip()]

for idx, ln in enumerate(lines):
    if "취사병" in ln:
        print("=== '취사병' 주변 실제 줄 구조 (idx %d) ===" % idx)
        for j in range(idx, min(idx + 25, len(lines))):
            mark = " <== 취사병" if j == idx else ""
            print("  %d: %r%s" % (j, lines[j], mark))
        break
print()

works = P.parse_blocks(text, heads)
print("=== parse_blocks 결과에서 '취사병' ===")
for w in works:
    if "취사병" in w["title"]:
        print("  제목:", w["title"])
        print("  공개일:", repr(w["release_date"]))
        print("  매체:", w["media"])
        print("  ---")
