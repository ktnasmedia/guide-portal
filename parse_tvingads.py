#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 광고센터 콘텐츠 페이지 파싱 테스트 (일회성)
대상: https://www.tvingads.com/content
  - "신작 및 주목할 콘텐츠" (HOT)
  - "향후 3개월 오픈 예정 콘텐츠" (COMING SOON)

목적: 각 작품의 제목·매체구분(T ONLY/T ORIGINAL/W 등)·등급·장르·부작·요일·출연진·공개일을
      자동으로 추출할 수 있는지 테스트. 결과는 콘솔 + tving_ads_parsed.json 으로 저장.

사용법 (GitHub Actions):
  pip install requests beautifulsoup4
  python parse_tvingads.py

주의:
  - Framer 사이트라 구조가 바뀌면 파싱이 깨질 수 있음(테스트 목적).
  - 포스터 이미지 URL도 함께 추출 시도.
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

# 매체 구분 토큰 (배지)
MEDIA_TOKENS = ["T ONLY", "T ORIGINAL", "W ORIGINAL", "T", "W", "특판", "전체"]
# 등급 토큰
RATING_TOKENS = ["전체", "7", "12", "15", "19", "청불"]
DATE_RE = re.compile(r"(20)?\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?")


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def extract_images(soup):
    """본문 이미지 URL 목록 (포스터 추정)"""
    imgs = []
    for im in soup.find_all("img"):
        src = im.get("src", "")
        if "framerusercontent.com/images" in src:
            # width=480&height=693 형태의 포스터 비율만
            imgs.append(src.split("?")[0])
    return imgs


def parse_blocks(text):
    """
    텍스트를 줄 단위로 보고, '공개일' 다음 날짜로 작품 경계를 잡아
    각 블록에서 제목/매체/등급/장르/출연/날짜를 추출.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    works = []
    cur = []
    for ln in lines:
        cur.append(ln)
        # 날짜 줄을 만나면 한 작품의 끝으로 간주
        if DATE_RE.fullmatch(ln.replace(" ", "")) or DATE_RE.search(ln) and len(ln) <= 14:
            block = cur[:]
            cur = []
            w = parse_one(block)
            if w and w.get("title"):
                works.append(w)
    return works


def parse_one(block):
    """한 작품 블록(여러 줄)에서 필드 추출"""
    media = []
    rating = ""
    title = ""
    genres = []
    cast = ""
    date = ""
    parts = 부작 = ""
    day = ""
    # 토큰 분류
    candidates = []
    for ln in block:
        b = ln.strip("* ").strip()
        if not b:
            continue
        if DATE_RE.search(b) and len(b) <= 14:
            date = b
            continue
        if b in ("T ONLY", "T ORIGINAL", "W ORIGINAL", "T", "W", "특판"):
            media.append(b)
            continue
        if b in RATING_TOKENS:
            rating = b
            continue
        if b == "공개일":
            continue
        if re.match(r"^\d+부작$", b):
            부작 = b
            continue
        if re.match(r"^[월화수목금토일\-, ]+$", b) and len(b) <= 8:
            day = b
            continue
        candidates.append(b)
    # candidates 중 첫 번째가 보통 제목, 그 뒤 장르들, 마지막이 출연진(쉼표 포함)
    if candidates:
        title = candidates[0]
        rest = candidates[1:]
        for r in rest:
            if "," in r or "·" in r:
                cast = r       # 출연진 추정
            else:
                genres.append(r)
    return {
        "title": title,
        "media": media,
        "rating": rating,
        "genres": genres,
        "parts": 부작,
        "day": day,
        "cast": cast,
        "release_date": date,
    }


def main():
    print("티빙 광고센터 콘텐츠 페이지 파싱 테스트")
    print("=" * 60)
    try:
        html = fetch()
    except Exception as e:
        print(f"ERROR: 페이지 fetch 실패: {e}")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")

    works = parse_blocks(text)

    # 중복 제거 (제목+공개일 기준)
    seen = set()
    uniq = []
    for w in works:
        key = (w["title"], w["release_date"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(w)

    print(f"\n추출된 작품 수(중복 제거): {len(uniq)}건\n")
    for i, w in enumerate(uniq, 1):
        media = "/".join(w["media"]) if w["media"] else "-"
        g = ", ".join(w["genres"]) if w["genres"] else "-"
        print(f"{i:>2}. {w['title']}")
        print(f"     매체:{media} | 등급:{w['rating'] or '-'} | 장르:{g} | {w['parts'] or ''} {w['day'] or ''}")
        print(f"     출연:{w['cast'] or '-'} | 공개일:{w['release_date'] or '-'}")

    # 이미지 URL 목록
    imgs = extract_images(soup)
    print(f"\n포스터 이미지 후보: {len(imgs)}개 (처음 5개)")
    for u in imgs[:5]:
        print(f"   {u}")

    # JSON 저장
    with open("tving_ads_parsed.json", "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=2)
    print("\ntving_ads_parsed.json 저장 완료")
    print("※ 결과가 깨끗하면 자동수집에 활용 가능. 패턴 오류 있으면 파싱 규칙 보정 필요.")


if __name__ == "__main__":
    main()
