#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 광고센터 콘텐츠 페이지 파싱 (모달 기반 + 매체/등급 폴백)
대상: https://www.tvingads.com/content

방식:
  1) 모달(상세 팝업, data-framer-name='Badge + Info+ Strategy')에서
     제목·줄거리·장르·출연진·요일·공개일 + (있으면) 매체·등급 추출.
  2) 매체/등급이 모달에 없으면, 목록 카드 영역(data-framer-name='Single - lg' 등)
     에서 같은 제목을 찾아 매체/등급을 보완(폴백).
  → 모달의 깔끔한 정보 + 목록의 매체/등급을 제목 기준으로 합침.

출력: 콘솔 + tving_ads_parsed.json
사용법(GitHub Actions): pip install requests beautifulsoup4 && python parse_tvingads.py
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
RATING_TOKENS = ("전체", "7", "12", "15", "19", "청불")
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


def norm(s):
    return (s or "").replace(" ", "").lower()


def parse_modal(modal):
    """모달 컨테이너 1개에서 작품 정보 추출"""
    h4 = modal.find("h4")
    title = h4.get_text(strip=True) if h4 else ""
    if not title:
        return None

    texts = []
    for p in modal.find_all("p"):
        t = p.get_text(strip=True)
        preset = p.get("data-styles-preset", "")
        if t:
            texts.append((t, preset))

    synopsis = ""
    genres, media = [], []
    cast = day = date = rating = parts = ""

    for t, preset in texts:
        if t == title:
            continue
        if preset == "zNPjUVKu5":
            synopsis = t
            continue
        if DATE_RE.search(t) and len(t) <= 16:
            date = t
            continue
        if t in MEDIA_TOKENS:
            media.append(t)
            continue
        if t in RATING_TOKENS and not rating:
            rating = t
            continue
        if re.match(r"^\d+부작$", t):
            parts = t
            continue
        if DAY_RE.match(t) and len(t) <= 8:
            day = t
            continue
        if ("," in t) or ("·" in t):
            cast = t
            continue
        if len(t) <= 12 and t not in ("공개일", "|"):
            genres.append(t)

    return {
        "title": title, "media": media, "rating": rating,
        "genres": genres, "parts": parts, "day": day,
        "cast": cast, "release_date": date, "synopsis": synopsis,
    }


def extract_card_media(soup):
    """
    목록 카드 영역에서 제목→(매체, 등급) 추출 (폴백용).
    카드 컨테이너는 data-framer-name 이 'Single - lg'(또는 유사)로 시작.
    카드 내 제목은 p 태그(framer-styles-preset-1h4d2v7 계열).
    """
    card_info = {}
    # 카드: 'Single' 들어가는 컨테이너
    cards = soup.find_all(attrs={"data-framer-name": re.compile(r"Single")})
    for c in cards:
        # 제목: Title 영역의 p
        title = ""
        title_box = c.find(attrs={"data-framer-name": "Title"})
        if title_box:
            p = title_box.find("p")
            if p:
                title = p.get_text(strip=True)
        if not title:
            continue
        # 매체/등급: 카드 내 모든 strong/p 훑기
        media, rating = [], ""
        for p in c.find_all(["p", "strong"]):
            t = p.get_text(strip=True)
            if t in MEDIA_TOKENS and t not in media:
                media.append(t)
            elif t in RATING_TOKENS and not rating:
                rating = t
        card_info[norm(title)] = {"media": media, "rating": rating}
    return card_info


def main():
    print("티빙 광고센터 콘텐츠 페이지 파싱 (모달 기반 + 폴백)")
    print("=" * 60)
    try:
        html = fetch()
    except Exception as e:
        print(f"ERROR: 페이지 fetch 실패: {e}")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")
    modals = soup.find_all(attrs={"data-framer-name": "Badge + Info+ Strategy"})
    card_info = extract_card_media(soup)
    print(f"[진단] 모달 발견: {len(modals)}개 / 목록카드(매체·등급): {len(card_info)}개\n")

    works = []
    seen = set()
    for m in modals:
        w = parse_modal(m)
        if not w:
            continue
        key = norm(w["title"])
        if key in seen:
            continue
        seen.add(key)
        # 매체/등급 폴백: 모달에 없으면 목록 카드에서 보완
        ci = card_info.get(key, {})
        if not w["media"] and ci.get("media"):
            w["media"] = ci["media"]
        if not w["rating"] and ci.get("rating"):
            w["rating"] = ci["rating"]
        works.append(w)

    syn_cnt = sum(1 for w in works if w.get("synopsis"))
    print(f"추출된 작품 수: {len(works)}건 / 줄거리 확보: {syn_cnt}건\n")
    for i, w in enumerate(works, 1):
        media = "/".join(w["media"]) if w["media"] else "-"
        g = ", ".join(w["genres"]) if w["genres"] else "-"
        print(f"{i:>2}. {w['title']}")
        print(f"     매체:{media} | 등급:{w['rating'] or '-'} | 장르:{g} | {w['parts']} {w['day']}")
        print(f"     출연:{w['cast'] or '-'} | 공개일:{w['release_date'] or '-'}")
        if w.get("synopsis"):
            print(f"     줄거리:{w['synopsis']}")

    imgs = extract_images(soup)
    print(f"\n포스터 이미지 후보: {len(imgs)}개")

    with open("tving_ads_parsed.json", "w", encoding="utf-8") as f:
        json.dump(works, f, ensure_ascii=False, indent=2)
    print("\ntving_ads_parsed.json 저장 완료")
    print("※ 모달 0개면 페이지가 모달을 HTML에 안 담는 것 → 다른 방법 필요.")


if __name__ == "__main__":
    main()
