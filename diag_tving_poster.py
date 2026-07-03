#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""티빙 콘텐츠 페이지 포스터 데이터 위치 진단 (GitHub Actions에서 실행)"""
import urllib.request
import re

URL = "https://www.tvingads.com/content"


def fetch():
    req = urllib.request.Request(URL)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


html = fetch()
print("HTML 길이:", len(html))

scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
print("script 태그 개수:", len(scripts))
print()

poster_re = re.compile(r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)')
for i, s in enumerate(scripts):
    cnt = len(poster_re.findall(s))
    if cnt > 0:
        print("  script[%d]: 포스터 URL %d개 발견 (길이 %d)" % (i, cnt, len(s)))

print()
all_posters = poster_re.findall(html)
print("HTML 전체 포스터 URL 개수:", len(all_posters))
if all_posters:
    print("첫 포스터 예시:", all_posters[0])

best_idx, best_cnt = -1, 0
for i, s in enumerate(scripts):
    c = len(poster_re.findall(s))
    if c > best_cnt:
        best_cnt, best_idx = c, i
print()
print("포스터가 가장 많은 script 인덱스:", best_idx, "(", best_cnt, "개 )")
if best_idx >= 0:
    data = scripts[best_idx]
    m = poster_re.search(data)
    if m:
        print("첫 포스터 주변 400자:")
        print(data[m.start():m.start() + 400])
