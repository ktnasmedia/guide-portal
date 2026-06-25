#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""script[11]에 포스터 이미지 URL이 작품 데이터와 함께 있는지 진단"""
import re, requests

URL = "https://www.tvingads.com/content"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

out = []
def w(s=""):
    print(s); out.append(str(s))

r = requests.get(URL, headers=H, timeout=20)
r.encoding = "utf-8"
html = r.text
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
data = scripts[11]
w(f"script[11] 길이: {len(data):,}")

# 줄거리 '오직 웃음으로' 주변 1500자 (포스터 URL이 근처에 있는지)
i = data.find("오직 웃음으로")
if i >= 0:
    w("\n=== '오직 웃음으로'(코미디숏리그) 주변 1500자 ===")
    w(data[max(0,i-1000):i+500])

# 예정작 '도깨비' 주변도 확인
i2 = data.find("도깨비 주역")
if i2 >= 0:
    w("\n\n=== 도깨비 줄거리 주변 1200자 ===")
    w(data[max(0,i2-900):i2+300])

# framerusercontent 이미지가 script[11]에 몇 개 있는지
imgs = re.findall(r'framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)', data)
w(f"\n\nscript[11] 내 framerusercontent 이미지: {len(imgs)}개")
for u in imgs[:25]:
    w(f"   {u}")

with open("diag_poster_result.txt","w",encoding="utf-8") as f:
    f.write("\n".join(out))
print("\ndiag_poster_result.txt 저장 완료")
