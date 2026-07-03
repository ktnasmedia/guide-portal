#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""샤먼:미신전 포스터 매칭 실패 진단"""
import re
import parse_tvingads as P

html = P.fetch()

posters = P.extract_posters(html)
print("=== extract_posters 결과 중 '샤먼' 포함 키 ===")
found = False
for k, v in posters.items():
    if "샤먼" in k or "미신" in k:
        print("  키:", repr(k), "→", v[:60])
        found = True
if not found:
    print("  '샤먼'/'미신' 포함 키 없음")
print()

print("=== 전체 포스터 키 (%d개) ===" % len(posters))
for k in posters.keys():
    print("  -", repr(k))
print()

scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
poster_re = re.compile(r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)')
best_idx, best_cnt = -1, 0
for i, s in enumerate(scripts):
    c = len(poster_re.findall(s))
    if c > best_cnt:
        best_cnt, best_idx = c, i
data = scripts[best_idx]
idx = data.find("샤먼")
print("=== 포스터 데이터에서 '샤먼' 주변 ===")
if idx == -1:
    print("  포스터 script에 '샤먼' 없음")
else:
    print("  [앞 300자]")
    print("  " + data[max(0, idx-300):idx].replace("\n", " "))
    print("  [샤먼부터 100자]")
    print("  " + data[idx:idx+100].replace("\n", " "))
