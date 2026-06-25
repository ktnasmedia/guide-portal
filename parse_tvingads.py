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


def extract_posters(html):
    """
    script[11] 데이터에서 제목→포스터 URL 매핑.
    데이터 구조: "포스터URL"(+srcSet 중복) ... "제목" ... 출연진 ... 줄거리
    포스터 URL 뒤 가장 가까운 한글 제목으로 매칭. 카드 HTML 구조 비의존.
    반환: {제목(공백제거): poster_url}
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if len(scripts) < 12:
        return {}
    data = scripts[11]
    posters = {}
    for m in re.finditer(
        r'"(https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png))\?[^"]*"',
        data,
    ):
        url = m.group(1)
        after = data[m.end():m.end() + 300]
        # 포스터 뒤 가장 가까운 '한글이 포함된' 문자열을 제목으로 (숫자로 시작해도 OK)
        tm = None
        for cand in re.finditer(r'"([^"]{2,40})"', after):
            txt = cand.group(1)
            # 한글이 1글자 이상 포함되고, 날짜/URL/타입토큰이 아닌 것
            if re.search(r"[가-힣]", txt) and not txt.startswith("http") \
               and "framerusercontent" not in txt:
                tm = txt
                break
        if tm:
            key = tm.replace(" ", "")
            posters.setdefault(key, url)
    return posters


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


def decode_unicode(s):
    """\\u003C 같은 인코딩 디코딩"""
    if not s:
        return s
    try:
        return s.encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
    except Exception:
        # 부분 치환 폴백
        return s.replace("\\u003C", "<").replace("\\u003E", ">").replace("\\u0026", "&")


def extract_synopsis(html):
    """
    script[11] 데이터에서 줄거리·예고편을 '등장 순서대로' 추출.
    패턴: "p00ID",{...},"줄거리",{...},"예고편URL"
    각 항목 앞 500자에서 출연진 후보도 같이 확보.
    반환: 리스트 [{cast_key, synopsis, trailer}] (페이지 등장 순)
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if len(scripts) < 12:
        return []
    data = scripts[11]
    items = []
    pat = re.compile(r'"(p\d{6,})",\{[^}]*\},"([^"]{20,400})"(?:,\{[^}]*\},"(https?://[^"]+)")?')
    for m in pat.finditer(data):
        syn = decode_unicode(m.group(2))
        trailer = m.group(3) or ""
        start = m.start()
        before = data[max(0, start - 500):start]
        casts = re.findall(r'"([가-힣A-Za-z0-9]+(?:,\s*[가-힣A-Za-z0-9]+)+)"', before)
        cast_key = casts[-1].replace(" ", "") if casts else ""
        items.append({"cast_key": cast_key, "synopsis": syn, "trailer": trailer})
    return items



def title_keywords(title):
    """제목에서 숫자/짧은토큰 제외한 핵심 단어 추출"""
    toks = re.split(r"[\s:·\-~]+", title)
    kws = []
    for t in toks:
        t2 = re.sub(r"[0-9]", "", t).strip()
        if len(t2) >= 2:
            kws.append(t2)
    return kws


def collect_tving_ads():
    """
    티빙 광고페이지를 파싱해 작품 리스트 반환.
    각 작품: title, media[], rating, genres[], parts, day, cast,
             release_date, synopsis, trailer
    실패 시 빈 리스트 반환(예외 안 던짐) — 자동수집 파이프라인 보호.
    """
    html = fetch()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    heads = extract_headings(soup)
    works = parse_blocks(text, heads)
    posters = extract_posters(html)

    seen, uniq = set(), []
    for w in works:
        key = w["title"].replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        w["poster"] = posters.get(key, "")   # 제목 기준 포스터 매칭
        uniq.append(w)

    # 줄거리·예고편 매칭 (출연진 → 제목 핵심단어)
    syn_items = extract_synopsis(html)
    used = [False] * len(syn_items)
    for w in uniq:
        ck = (w.get("cast") or "").replace(" ", "")
        w["synopsis"] = ""
        w["trailer"] = ""
        if not ck:
            continue
        for idx, it in enumerate(syn_items):
            if not used[idx] and it["cast_key"] and it["cast_key"] == ck:
                w["synopsis"] = it["synopsis"]
                w["trailer"] = it["trailer"]
                used[idx] = True
                break
    for w in uniq:
        if w["synopsis"]:
            continue
        kws = title_keywords(w["title"])
        if not kws:
            continue
        for idx, it in enumerate(syn_items):
            if used[idx]:
                continue
            syn_nospace = it["synopsis"].replace(" ", "")
            if any(kw in syn_nospace for kw in kws):
                w["synopsis"] = it["synopsis"]
                w["trailer"] = it["trailer"]
                used[idx] = True
                break
    return uniq


def main():
    print("티빙 광고센터 콘텐츠 페이지 파싱 (목록 카드 기반)")
    print("=" * 60)
    try:
        uniq = collect_tving_ads()
    except Exception as e:
        print(f"ERROR: 파싱 실패: {e}")
        sys.exit(1)

    syn_cnt = sum(1 for w in uniq if w.get("synopsis"))
    print(f"\n추출된 작품 수: {len(uniq)}건 / 줄거리 확보: {syn_cnt}건\n")
    for i, w in enumerate(uniq, 1):
        media = "/".join(w["media"]) if w["media"] else "-"
        g = ", ".join(w["genres"]) if w["genres"] else "-"
        print(f"{i:>2}. {w['title']}")
        print(f"     매체:{media} | 등급:{w['rating'] or '-'} | 장르:{g} | {w['parts']} {w['day']}")
        print(f"     출연:{w['cast'] or '-'} | 공개일:{w['release_date'] or '-'}")
        if w.get("synopsis"):
            print(f"     줄거리:{w['synopsis']}")
        if w.get("trailer"):
            print(f"     예고편:{w['trailer']}")

    with open("tving_ads_parsed.json", "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=2)
    print("\ntving_ads_parsed.json 저장 완료")


if __name__ == "__main__":
    main()
