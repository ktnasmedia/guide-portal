#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
script[11] 데이터 구조 진단 + 결과를 파일로 저장(diag_result.txt).
제목↔줄거리 연결 방식 파악용.
"""
import re
import requests

URL = "https://www.tvingads.com/content"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

out = []
def w(s=""):
    print(s)
    out.append(str(s))

r = requests.get(URL, headers=H, timeout=20)
r.encoding = "utf-8"
html = r.text
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
data = scripts[11]
w(f"script[11] 길이: {len(data):,}")

PROBES = ["오직 웃음으로", "베테랑 메이저팀"]
for pr in PROBES:
    i = data.find(pr)
    if i >= 0:
        w(f"\n=== '{pr}' 주변 600자 ===")
        w(data[max(0,i-400):i+200])

w("\n\n=== 긴 한글 문장(줄거리 후보) 목록 ===")
candidates = re.findall(r'"([^"]{30,250})"', data)
seen = set()
n = 0
for c in candidates:
    if len(re.findall(r'[가-힣]', c)) < 15:
        continue
    if c in seen:
        continue
    seen.add(c)
    n += 1
    w(f"  {n}. {c}")
w(f"\n총 줄거리 후보: {len(seen)}개")

# 제목 후보(짧은 한글, 작품명) 주변에 ID가 어떻게 붙는지도 일부 출력
w("\n\n=== 데이터 일부 원본(앞 3000자) ===")
w(data[:3000])

with open("diag_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\ndiag_result.txt 저장 완료")
