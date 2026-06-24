#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모달/줄거리 데이터가 페이지 HTML(또는 연결된 JSON)에 있는지 진단.
'오직 웃음으로' 같은 줄거리 텍스트가 어디에 들어있는지 추적.
"""
import re
import requests

URL = "https://www.tvingads.com/content"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

PROBE = "오직 웃음으로"   # 코미디숏리그 줄거리 일부

r = requests.get(URL, headers=H, timeout=20)
r.encoding = "utf-8"
html = r.text
print(f"HTML 길이: {len(html):,}자")

# 1) 줄거리 텍스트가 원본 HTML에 있나?
idx = html.find(PROBE)
print(f"\n[1] '{PROBE}' 위치: {idx}")
if idx >= 0:
    print("  → 원본 HTML에 줄거리 있음! 주변 200자:")
    print("  " + html[max(0,idx-100):idx+100].replace("\n", " "))
else:
    print("  → 원본 HTML에 줄거리 없음 (JS 렌더링 추정)")

# 2) script 태그 안 데이터 JSON 탐색
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
print(f"\n[2] script 태그 수: {len(scripts)}")
for i, s in enumerate(scripts):
    if PROBE in s:
        print(f"  → script[{i}]에 줄거리 있음! (길이 {len(s)})")
    # Framer 데이터 단서
    if "data" in s.lower() and ("synopsis" in s.lower() or "strategy" in s.lower() or "줄거리" in s):
        print(f"  → script[{i}]에 데이터 구조 단서 있음")

# 3) __framer 또는 application/json 타입 데이터
for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL):
    print(f"\n[3] application/json script 발견 (길이 {len(m.group(1))})")
    if PROBE in m.group(1):
        print("  → 여기에 줄거리 있음!")

# 4) 외부 JSON 데이터 URL 단서 (framerusercontent .json)
jsons = re.findall(r'https://[^"\']+\.json', html)
jsons = list(set(jsons))
print(f"\n[4] 페이지가 참조하는 .json URL: {len(jsons)}개")
for j in jsons[:20]:
    print(f"   {j}")
