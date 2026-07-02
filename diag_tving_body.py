#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개별 공지 페이지 원본 HTML 구조 진단"""
import urllib.request, re

URL = "https://tving.framer.website/notices/notice-067"

def fetch(url, timeout=25):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

html = fetch(URL)
print("총 길이:", len(html))
print("<script 개수:", html.count("<script"))
print("<style 개수:", html.count("<style"))
print()

# 본문 핵심 문구가 어디 있는지
for kw in ["안녕하세요", "청약 일정", "상품별 판매", "광고팀"]:
    idx = html.find(kw)
    print("'%s' 위치: %d" % (kw, idx))
print()

# h1 태그 찾기
for m in re.finditer(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL):
    print("h1:", re.sub(r"<[^>]+>","",m.group(1))[:50], "(위치 %d)" % m.start())
print()

# '안녕하세요' 주변 HTML 구조 (본문이 어떤 태그에 있는지)
idx = html.find("안녕하세요")
if idx != -1:
    print("=== '안녕하세요' 주변 600자 ===")
    print(html[idx-300:idx+300])
