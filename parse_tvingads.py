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
    r.encoding = "utf-8"   # 한글 깨짐 방지
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
    '공개일' 다음 날짜로 작품 경계를 잡아 블록 분리.
    헤더/네비 등 노이즈 블록은 제외.
    """
    NOISE = ("TVING Ads", "광고정보센터", "LINE UP", "HOT", "COMING SOON",
             "PDF Document", "더보기", "인기 콘텐츠", "DEMO RANKING",
             "성·연령별", "광고 문의", "캠페인 시작")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    works = []
    cur = []
    for ln in lines:
        cur.append(ln)
        is_date = bool(DATE_RE.search(ln)) and len(ln) <= 14
        if is_date:
            block = cur[:]
            cur = []
            w = parse_one(block)
            t = w.get("title", "")
            # 노이즈 제거: 제목이 비었거나 잡음 키워드 포함
            if not t:
                continue
            if any(n in t for n in NOISE):
                continue
            # 제목이 매체/장르 단독 토큰이면 제외
            if t in ("드라마", "예능", "전체", "특판", "더보기", "스포츠", "교양"):
                continue
            works.append(w)
    return works


def parse_one(block):
    """
    한 작품 블록에서 필드 추출.
    페이지 구조 순서: [매체배지...] [등급] 제목 [장르...] [부작] [요일] [출연진] '공개일' 날짜
    """
    media = []
    rating = ""
    parts = ""
    day = ""
    date = ""
    # '공개일' 토큰 위치를 찾아 그 뒤 날짜, 그 직전을 출연진 후보로
    body = [ln.strip("* |").strip() for ln in block]
    body = [b for b in body if b]

    # 날짜 추출
    for b in body:
        if DATE_RE.search(b) and len(b) <= 14:
            date = b.strip()
            break

    # '공개일' 인덱스
    try:
        gi = body.index("공개일")
    except ValueError:
        gi = len(body)

    # 공개일 앞부분만 사용 (날짜/공개일 이후는 버림)
    head = body[:gi]
    # 토큰 분류
    leftover = []
    for b in head:
        if b in ("T ONLY", "T ORIGINAL", "W ORIGINAL", "T", "W", "특판", "전체"):
            media.append(b)
        elif b in ("7", "12", "15", "19", "청불"):
            rating = b
        elif re.match(r"^\d+부작$", b):
            parts = b
        elif re.match(r"^[월화수목금토일\-, ]+$", b) and len(b) <= 8:
            day = b
        else:
            leftover.append(b)

    # leftover: [제목, 장르, 세부장르..., 출연진]
    title = leftover[0] if leftover else ""
    cast = ""
    genres = []
    if len(leftover) > 1:
        # 마지막 항목이 쉼표/가운뎃점 많으면 출연진
        last = leftover[-1]
        if ("," in last) or ("·" in last):
            cast = last
            genres = leftover[1:-1]
        else:
            genres = leftover[1:]
    return {
        "title": title,
        "media": media,
        "rating": rating,
        "genres": genres,
        "parts": parts,
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

    # 중복 제거 (제목 기준, 띄어쓰기 무시)
    seen = set()
    uniq = []
    for w in works:
        key = w["title"].replace(" ", "")
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
