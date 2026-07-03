#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 광고센터 콘텐츠 페이지 파싱 (목록 카드 기반)
대상: https://www.tvingads.com/content
  - 신작 및 주목할 콘텐츠 + 향후 3개월 오픈 예정 콘텐츠
추출: 제목·매체구분·등급·장르·부작·요일·출연진·공개일·포스터
"""
import json
import re
import sys
import requests
from bs4 import BeautifulSoup

URL = "https://www.tvingads.com/content"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DATE_RE = re.compile(r"\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.?|\d{4}년\s*\d{1,2}월\s*\d{1,2}일")
MEDIA_TOKENS = ("T ONLY", "T ORIGINAL", "W ORIGINAL", "W", "T", "특판", "전체")
RATING_TOKENS = ("7", "12", "15", "19", "청불")
DAY_RE = re.compile(r"^[월화수목금토일\-~, ]+$")


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def extract_images(soup):
    imgs = []
    for im in soup.find_all("img"):
        src = im.get("src", "")
        if "framerusercontent.com/images" in src:
            imgs.append(src.split("?")[0])
    return imgs


def extract_posters(html):
    """
    Framer 데이터 script에서 제목→포스터 URL 매핑.
    포스터가 든 script 위치가 개편으로 바뀔 수 있어 인덱스를 고정하지 않고
    포스터 URL이 가장 많은 script 를 자동으로 찾는다.
    반환: {제목(공백제거): poster_url}
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if not scripts:
        return {}
    poster_url_re = re.compile(
        r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)'
    )
    best_idx, best_cnt = -1, 0
    for
