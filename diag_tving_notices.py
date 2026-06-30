#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""티빙 공지 원본 HTML 구조 진단 — GitHub Actions에서 실행"""
import urllib.request, re

LIST_URL = "https://tving.framer.website/notices"

def fetch(url, timeout=25):
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

html = fetch(LIST_URL)
print("=== HTML 총 길이:", len(html))
print()
print("=== 'notice-' 등장 횟수:", html.count("notice-"))
print("=== '/notices/' 등장 횟수:", html.count("/notices/"))
print()
# notice- 주변 텍스트 샘플 (처음 3곳)
for i, m in enumerate(re.finditer(r"notice-\d+", html)):
    if i >= 3: break
    s = max(0, m.start()-200)
    e = min(len(html), m.end()+100)
    print("--- notice 등장 %d (위치 %d) ---" % (i+1, m.start()))
    print(html[s:e])
    print()
# script/json 데이터가 있는지
print("=== '__framer' 또는 data json 흔적 ===")
for kw in ["application/json", "__framer", "searchIndex", "<script"]:
    print("  '%s':" % kw, html.count(kw), "회")
# HTML 앞부분 1500자
print()
print("=== HTML 앞 1500자 ===")
print(html[:1500])
