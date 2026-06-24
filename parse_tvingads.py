#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 광고센터 콘텐츠 페이지 파싱 (목록 카드 기반 — 20건 안정 버전)
대상: https://www.tvingads.com/content
  - 신작 및 주목할 콘텐츠 + 향후 3개월 오픈 예정 콘텐츠
추출: 제목·매체구분·등급·장르·부작·요일·출연진·공개일·포스터
※ 줄거리는 JS 모달에 있어 여기선 제외(별도 보완).
출력: 콘솔 + tving_ads_parsed.json
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


def extract_headings(soup):
    heads = set()
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = tag.get_text(strip=True)
        if t and len(t) <= 40:
            heads.add(t)
    return heads


def parse_one(block, heads):
    body = [ln.strip("* |").strip() for ln in block]
    body = [b for b in body if b]
    date = ""
    for b in body:
        if DATE_RE.search(b) and len(b) <= 16:
            date = b
            break
    try:
        gi = body.index("공개일")
    except ValueError:
        gi = len(body)
    head = body[:gi]
    media, leftover = [], []
    rating = parts = day = ""
    for b in head:
        if b in MEDIA_TOKENS:
            media.append(b)
        elif b in RATING_TOKENS:
            rating = b
        elif re.match(r"^\d+부작$", b):
            parts = b
        elif DAY_RE.match(b) and len(b) <= 8:
            day = b
        else:
            leftover.append(b)
    title, cast, genres = "", "", []
    head_match = [b for b in leftover if b in heads]
    if head_match:
        title = head_match[0]
        rest = [b for b in leftover if b != title]
    elif leftover:
        title = leftover[0]
        rest = leftover[1:]
    else:
        rest = []
    for r in rest:
        if ("," in r) or ("·" in r):
            cast = r
        else:
            genres.append(r)
    return {"title": title, "media": media, "rating": rating, "genres": genres,
            "parts": parts, "day": day, "cast": cast, "release_date": date}


def parse_blocks(text, heads):
    NOISE = ("TVING Ads", "광고정보센터", "LINE UP", "HOT", "COMING SOON",
             "PDF Document", "더보기", "인기 콘텐츠", "DEMO RANKING",
             "성·연령별", "광고 문의", "캠페인 시작", "콘텐츠 라인업",
             "지금 주목해야", "향후 3개월", "오픈 예정")
    BAD = ("드라마", "예능", "전체", "특판", "더보기", "스포츠", "교양", "다큐멘터리", "공개일")

    def valid(w):
        t = w.get("title", "")
        if not t or t in BAD:
            return False
        if any(n in t for n in NOISE):
            return False
        if DATE_RE.search(t) and len(t) <= 16:
            return False
        return True

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    works, cur = [], []
    for ln in lines:
        cur.append(ln)
        if bool(DATE_RE.search(ln)) and len(ln) <= 16:
            w = parse_one(cur[:], heads)
            if valid(w):
                works.append(w)
            cur = []
    if cur:
        w = parse_one(cur, heads)
        if valid(w):
            works.append(w)
    return works


def main():
    print("티빙 광고센터 콘텐츠 페이지 파싱 (목록 카드 기반)")
    print("=" * 60)
    try:
        html = fetch()
    except Exception as e:
        print(f"ERROR: 페이지 fetch 실패: {e}")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    heads = extract_headings(soup)
    works = parse_blocks(text, heads)

    seen, uniq = set(), []
    for w in works:
        key = w["title"].replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(w)

    print(f"\n추출된 작품 수: {len(uniq)}건\n")
    for i, w in enumerate(uniq, 1):
        media = "/".join(w["media"]) if w["media"] else "-"
        g = ", ".join(w["genres"]) if w["genres"] else "-"
        print(f"{i:>2}. {w['title']}")
        print(f"     매체:{media} | 등급:{w['rating'] or '-'} | 장르:{g} | {w['parts']} {w['day']}")
        print(f"     출연:{w['cast'] or '-'} | 공개일:{w['release_date'] or '-'}")

    imgs = extract_images(soup)
    print(f"\n포스터 이미지 후보: {len(imgs)}개")

    with open("tving_ads_parsed.json", "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=2)
    print("\ntving_ads_parsed.json 저장 완료")


if __name__ == "__main__":
    main()
