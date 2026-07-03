#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""특정 티빙 작품의 포스터-제목 매칭 실패 원인 진단"""
import urllib.request
import re

URL = "https://www.tvingads.com/content"
TARGETS = ["윔블던", "피의게임", "오싹한 연애"]


def fetch():
    req = urllib.request.Request(URL)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


html = fetch()
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
poster_re = re.compile(r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)')

best_idx, best_cnt = -1, 0
for i, s in enumerate(scripts):
    c = len(poster_re.findall(s))
    if c > best_cnt:
        best_cnt, best_idx = c, i
data = scripts[best_idx]
print("포스터 script 인덱스:", best_idx)
print()

for t in TARGETS:
    idx = data.find(t)
    print("===== '%s' =====" % t)
    if idx == -1:
        print("  데이터에서 찾을 수 없음 (제목 자체가 다르거나 없음)")
        print()
        continue
    before = data[max(0, idx - 400):idx]
    print("  [제목 앞 400자]")
    print("  " + before.replace("\n", " "))
    print()
    after = data[idx:idx + 120]
    print("  [제목부터 120자]")
    print("  " + after.replace("\n", " "))
    print()
