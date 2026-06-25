#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
넷플릭스 콘텐츠 라인업 자동 수집 스크립트
- 소스: TMDB API (메타데이터·포스터)
- 범위: 전년도 / 올해 / 내년 (실행 시점 기준 자동)
- 대상: 넷플릭스(provider_id=8) 한국(KR) 콘텐츠 (시리즈 + 영화)
- 출력: content_lineup.json (스키마 준수, 빈 값은 화면에서 '미정' 표시)
- 로그: collection_log.md 에 한 줄 요약 + 변경 작품 목록 누적

토큰은 코드에 직접 쓰지 않고 환경변수 TMDB_TOKEN 에서 읽음.
로컬 실행:  TMDB_TOKEN="본인토큰" python3 collect_lineup.py
"""

import os
import sys
import json
import csv
import time
import datetime
import re
import urllib.request
import urllib.parse
import urllib.error

# ── 설정 ──
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w500"
NETFLIX_PROVIDER_ID = 8     # 넷플릭스 watch provider (볼 수 있음)
NETFLIX_NETWORK_ID = 213    # 넷플릭스 network (오리지널 제작/배급)

# OTT별 설정. mode: "both"=provider+network 합집합, "network"=오리지널(network)만
OTT_CONFIG = {
    "netflix": {"name": "넷플릭스", "provider_id": 8,    "network_id": 213,  "original_company": "Netflix", "mode": "both"},
    "tving":   {"name": "티빙",     "provider_id": 1883, "network_id": 3897, "original_company": "TVING",   "mode": "network"},
    "wavve":   {"name": "웨이브",    "provider_id": 356,  "network_id": 3357, "original_company": "wavve",   "mode": "network"},
}
# 수집할 OTT 목록 (순서대로).
ACTIVE_OTTS = ["netflix", "tving", "wavve"]
REGION = "KR"
ORIGIN_COUNTRY = "KR"
LANG = "ko-KR"
OUTPUT_JSON = "content_lineup.json"
LOG_FILE = "collection_log.md"

# 콘텐츠 분류 매핑 (TMDB 장르/타입 → 우리 분류)
TV_GENRE_TO_TYPE = {
    10764: "예능",  # Reality
    10767: "예능",  # Talk
    99: "다큐",      # Documentary
    16: "애니메이션", # Animation
}


def http_get(path, params):
    """TMDB API GET 요청. 토큰은 Bearer 헤더로."""
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TMDB_TOKEN}")
    req.add_header("accept", "application/json")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limit
                time.sleep(2)
                continue
            raise
        except Exception:
            if attempt < 2:
                time.sleep(1)
                continue
            raise
    return None


def derive_quarter(date_str):
    if not date_str:
        return None, None
    try:
        d = datetime.date.fromisoformat(date_str)
        return d.year, f"Q{(d.month - 1) // 3 + 1}"
    except Exception:
        return None, None


def map_tv_type(genre_ids):
    for gid in (genre_ids or []):
        if gid in TV_GENRE_TO_TYPE:
            return TV_GENRE_TO_TYPE[gid]
    return "시리즈"


def fetch_certification_tv(tv_id):
    """TV 시청등급 (KR 우선)"""
    try:
        data = http_get(f"/tv/{tv_id}/content_ratings", {})
        for r in (data or {}).get("results", []):
            if r.get("iso_3166_1") == "KR" and r.get("rating"):
                return r["rating"]
    except Exception:
        pass
    return None


def fetch_certification_movie(movie_id):
    """영화 시청등급 (KR 우선)"""
    try:
        data = http_get(f"/movie/{movie_id}/release_dates", {})
        for r in (data or {}).get("results", []):
            if r.get("iso_3166_1") == "KR":
                for rd in r.get("release_dates", []):
                    if rd.get("certification"):
                        return rd["certification"]
    except Exception:
        pass
    return None


def fetch_cast(media_type, tmdb_id):
    """주요 출연진 상위 5명"""
    try:
        data = http_get(f"/{media_type}/{tmdb_id}/credits", {"language": LANG})
        cast = [c["name"] for c in (data or {}).get("cast", [])[:5] if c.get("name")]
        return cast
    except Exception:
        return []


def fetch_genres_map(media_type):
    """장르 ID→이름 매핑 (한국어)"""
    try:
        data = http_get(f"/genre/{media_type}/list", {"language": LANG})
        return {g["id"]: g["name"] for g in (data or {}).get("genres", [])}
    except Exception:
        return {}


def _discover_pages(media_type, base_params, genre_map, ott="netflix"):
    """주어진 조건으로 페이지네이션하며 수집 (id→normalized item)"""
    out = {}
    date_field = "first_air_date" if media_type == "tv" else "primary_release_date"
    page = 1
    while page <= 10:
        params = dict(base_params)
        params["page"] = page
        data = http_get(f"/discover/{media_type}", params)
        if not data:
            break
        results = data.get("results", [])
        if not results:
            break
        for it in results:
            out[it["id"]] = normalize(media_type, it, genre_map, ott)
        if page >= data.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.2)
    return out


def discover(media_type, year, genre_map, ott="netflix"):
    """특정 연도의 OTT KR 콘텐츠 수집.
    TV: provider(볼 수 있음) + network(제작) 합집합 → 신작 누락 방지
    영화: network 개념이 없으므로 provider만 사용
    """
    cfg = OTT_CONFIG[ott]
    provider_id = cfg["provider_id"]
    network_id = cfg["network_id"]
    mode = cfg.get("mode", "both")
    date_field = "first_air_date" if media_type == "tv" else "primary_release_date"
    common = {
        "language": LANG,
        "sort_by": f"{date_field}.desc",
        f"{date_field}.gte": f"{year}-01-01",
        f"{date_field}.lte": f"{year}-12-31",
    }
    merged = {}

    # provider 조건 (해당 OTT에서 볼 수 있는 작품) — mode가 "both"일 때만
    if mode == "both":
        prov_params = dict(common)
        prov_params.update({"watch_region": REGION, "with_watch_providers": provider_id,
                            "with_origin_country": ORIGIN_COUNTRY})
        merged.update(_discover_pages(media_type, prov_params, genre_map, ott))

    # network 조건 (해당 OTT가 만든 오리지널) — TV만 적용
    if media_type == "tv":
        net_params = dict(common)
        net_params.update({"with_networks": network_id, "with_origin_country": ORIGIN_COUNTRY})
        merged.update(_discover_pages(media_type, net_params, genre_map, ott))

    return list(merged.values())


def fetch_is_original(media_type, tmdb_id, ott="netflix"):
    """OTT 오리지널 여부 판별.
    TV: networks에 해당 OTT network 포함 여부
    영화: production_companies에 해당 OTT 계열 포함 여부
    """
    cfg = OTT_CONFIG[ott]
    network_id = cfg["network_id"]
    company_kw = cfg["original_company"]
    try:
        d = http_get(f"/{media_type}/{tmdb_id}", {"language": LANG})
        if media_type == "tv":
            net_ids = [n.get("id") for n in d.get("networks", [])]
            return network_id in net_ids
        else:
            companies = [c.get("name", "") for c in d.get("production_companies", [])]
            return any(company_kw in c for c in companies)
    except Exception:
        return False


def normalize(media_type, raw, genre_map, ott="netflix"):
    """TMDB 응답 → 우리 스키마로 변환"""
    tmdb_id = raw.get("id")
    title = raw.get("name") or raw.get("title") or ""
    orig = raw.get("original_name") or raw.get("original_title")
    rd = raw.get("first_air_date") or raw.get("release_date") or None
    if rd == "":
        rd = None
    year, quarter = derive_quarter(rd)
    poster_path = raw.get("poster_path")
    poster_url = f"{IMG_BASE}{poster_path}" if poster_path else None
    genre_ids = raw.get("genre_ids", [])
    genres = [genre_map.get(g) for g in genre_ids if genre_map.get(g)]
    summary = raw.get("overview") or None

    if media_type == "tv":
        content_type = map_tv_type(genre_ids)
        cast = fetch_cast("tv", tmdb_id)
        rating = fetch_certification_tv(tmdb_id)
    else:
        content_type = "영화"
        cast = fetch_cast("movie", tmdb_id)
        rating = fetch_certification_movie(tmdb_id)

    is_orig = fetch_is_original(media_type, tmdb_id, ott)

    return {
        "content_id": f"tmdb-{ott}-{media_type}-{tmdb_id}",
        "title": title,
        "title_original": orig,
        "poster_url": poster_url,
        "cast": cast,
        "release_date": rd,
        "release_year": year,
        "release_quarter": (f"{year} {quarter}" if year and quarter else None),
        "summary": summary,
        "content_type": content_type,
        "genres": genres,
        "rating": rating,
        "ott": ott,
        "is_original": is_orig,
        "availability_status": None,  # 화면에서 접속일 기준 자동판정하므로 비워둠
        "_meta": {
            "sources": {"_all": "tmdb"},
            "confidence": "confirmed",
            "last_updated": datetime.date.today().isoformat(),
            "needs_review": False,
        },
    }


def load_previous():
    try:
        with open(OUTPUT_JSON, encoding="utf-8") as f:
            return {it["content_id"]: it for it in json.load(f).get("items", [])}
    except Exception:
        return {}


# ── 티빙 광고페이지 수집 + 누적 보관 ──
TVING_ADS_ACCUM = "tving_ads_accumulated.json"

# 광고페이지 매체배지 → (ott, is_original)
_BADGE_MAP = {
    "T ONLY":     ("tving", True),
    "T ORIGINAL": ("tving", True),
    "T":          ("tving", False),
    "W ORIGINAL": ("wavve", True),
    "W":          ("wavve", False),
}


def _parse_ads_date(s):
    """'26. 6. 19.' / '2026. 7. 4.' → '2026-06-19'. 실패 시 None"""
    if not s:
        return None
    m = re.search(r"(\d{2,4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
    if not m:
        return None
    y, mo, d = m.groups()
    y = int(y)
    if y < 100:
        y += 2000
    return f"{y:04d}-{int(mo):02d}-{int(d):02d}"


def tving_ads_to_schema(works):
    """
    광고페이지 파싱 결과(works)를 우리 스키마 아이템 리스트로 변환.
    매체배지에 따라 ott/is_original 결정. T/W는 티빙·웨이브 양쪽 생성.
    """
    items = []
    for w in works:
        media = w.get("media", []) or []
        # 'T'와 'W'가 둘 다 있으면 T/W (양쪽 생성). '특판'은 무시.
        has_t = any(x in ("T", "T ONLY", "T ORIGINAL") for x in media)
        has_w = any(x in ("W", "W ORIGINAL") for x in media)
        # 대표 배지 텍스트
        badge = "/".join([x for x in media if x != "특판"]) or None

        targets = []  # (ott, is_original)
        if has_t and has_w:
            targets = [("tving", False), ("wavve", False)]
        else:
            for x in media:
                if x in _BADGE_MAP:
                    targets.append(_BADGE_MAP[x])
                    break
            if not targets:
                targets = [("tving", False)]  # 기본값

        rd = _parse_ads_date(w.get("release_date"))
        year, quarter = derive_quarter(rd)
        cast_list = [c.strip() for c in (w.get("cast") or "").split(",") if c.strip()]
        genres = [g for g in (w.get("genres") or []) if g and g != "미정"]

        for ott, is_orig in targets:
            slug = w["title"].replace(" ", "").replace("/", "")
            items.append({
                "content_id": f"tvingads-{ott}-{slug}",
                "title": w["title"],
                "title_original": None,
                "poster_url": (w.get("poster") or None),  # 광고페이지 카드 포스터
                "cast": cast_list,
                "release_date": rd,
                "release_year": year,
                "release_quarter": (f"{year} {quarter}" if year and quarter else None),
                "summary": w.get("synopsis") or None,
                "content_type": (genres[0] if genres else None),
                "genres": genres,
                "rating": w.get("rating") or None,
                "ott": ott,
                "is_original": is_orig,
                "availability_status": None,
                "source_badge": badge,
                "trailer_url": w.get("trailer") or None,
                "_meta": {
                    "sources": {"_all": "tvingads"},
                    "confidence": "confirmed",
                    "last_updated": datetime.date.today().isoformat(),
                    "needs_review": False,
                },
            })
    return items


def collect_and_accumulate_tving_ads():
    """
    광고페이지 수집 → 스키마 변환 → 누적 파일과 병합(제목 기준 유지).
    누적: 한번 들어온 작품은 페이지에서 빠져도 보존. 다시 들어오면 정보 갱신.
    반환: 누적된 전체 광고페이지 아이템 리스트.
    """
    # 기존 누적 로드
    try:
        with open(TVING_ADS_ACCUM, encoding="utf-8") as f:
            accum = {it["content_id"]: it for it in json.load(f).get("items", [])}
    except Exception:
        accum = {}

    # 새로 수집
    try:
        from parse_tvingads import collect_tving_ads
        works = collect_tving_ads()
        poster_cnt = sum(1 for w in works if w.get("poster"))
        print(f"  → 티빙 광고페이지: 작품 {len(works)}건 / 포스터 {poster_cnt}건 매칭")
        new_items = tving_ads_to_schema(works)
    except Exception as e:
        print(f"WARN: 티빙 광고페이지 수집 실패: {e}", file=sys.stderr)
        new_items = []

    # 병합: 새 정보로 갱신, 기존에만 있는 건 유지
    for it in new_items:
        accum[it["content_id"]] = it  # 같은 ID면 최신 정보로 갱신

    merged = list(accum.values())

    # 누적 파일 저장
    try:
        with open(TVING_ADS_ACCUM, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.datetime.now().isoformat(),
                "source": "tvingads.com/content",
                "items": merged,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"WARN: 광고페이지 누적 저장 실패: {e}", file=sys.stderr)

    print(f"  → 티빙 광고페이지: 신규수집 {len(new_items)}건 / 누적 총 {len(merged)}건")
    return merged


# ── 넷플릭스 뉴스룸 수집 (상세 페이지 URL 목록 기반) ──
import re
import html as htmllib

NEWSROOM_URLS_FILE = "newsroom_urls.txt"


def newsroom_fetch_detail(url):
    """뉴스룸 상세 페이지 HTML 가져오기"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def newsroom_classify_type(title):
    if "예능" in title:
        return "예능"
    if "영화" in title:
        return "영화"
    if "다큐" in title:
        return "다큐"
    if "시리즈" in title:
        return "시리즈"
    return "미정"


def newsroom_extract_cast(title):
    """제목에서 'A-B-C', 'A X B', 'A × B' 형태 출연진 추출 (구분자 양옆 공백 허용)"""
    m = re.search(r"([가-힣]{2,4}(?:\s*[-X×]\s*[가-힣]{2,4}){1,6})", title)
    if not m:
        return []
    parts = re.split(r"\s*[-X×]\s*", m.group(1))
    return [n.strip() for n in parts if 2 <= len(n.strip()) <= 4]


def newsroom_extract_cast_from_body(html_text):
    """본문 작품정보 블록의 '출연: 변우석' 또는 '출연: A, B, C' 형태에서 출연진 추출"""
    m = re.search(r"출\s*연\s*[:：]\s*([^\n<]{2,80})", html_text)
    if not m:
        return []
    raw = m.group(1)
    # 다음 항목(제작/제공/연출 등) 전까지만
    raw = re.split(r"제\s*작|제\s*공|연\s*출|각\s*본", raw)[0]
    names = re.split(r"[,，·X×/]| 외 ", raw)
    return [n.strip() for n in names if 2 <= len(n.strip()) <= 5]


def newsroom_extract_cast_from_casting(html_text):
    """본문 '송혜교, 공유, ...의 캐스팅' 문장에서 출연진 추출 (쉼표 나열형)"""
    # 'A, B, C(, D...)의 캐스팅' 패턴 — 마지막 이름 뒤 '의/을/를' 조사 분리
    m = re.search(r"([가-힣]{2,4}(?:\s*,\s*[가-힣]{2,4}){1,8})\s*(?:의|을|를)?\s*캐스팅", html_text)
    if not m:
        return []
    names = re.split(r"\s*,\s*", m.group(1))
    out = []
    for n in names:
        n = n.strip()
        # 마지막에 붙은 조사 제거 (이하늬의 → 이하늬). 이름 끝글자와 안 겹치는 의/을/를만
        n = re.sub(r"(의|을|를)$", "", n) if len(n) >= 3 else n
        if 2 <= len(n) <= 4 and not _is_non_name(n):
            out.append(n)
    return out


# 이름이 아닌 흔한 단어(동사·명사 어미 등) — 출연진 추출 시 제외
_NON_NAME_WORDS = {
    "확정하고", "공개했다", "공개하고", "확정했다", "제작확정", "캐스팅을",
    "출연진은", "라인업을", "라인업", "공개", "확정", "제작", "공개한",
    "발표했다", "발표하고", "공개되며", "공개되어", "그리고", "비롯해",
    "물론", "특별", "함께한", "맡았다", "맡은", "역의",
}
def _is_non_name(word):
    if word in _NON_NAME_WORDS:
        return True
    # '~하고/~했다/~하며/~되며' 등 동사형 어미로 끝나면 이름 아님
    if re.search(r"(하고|했다|하며|되며|되어|한다|졌다|진다)$", word):
        return True
    return False


def newsroom_parse(url, html_text):
    """상세 페이지 HTML에서 작품 정보 추출 (검증된 패턴)"""
    # og:title (넷플릭스는 name 속성 사용, property도 대비)
    tm = re.search(r'<meta[^>]*(?:name|property)=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', html_text, re.I)
    title_raw = htmllib.unescape(tm.group(1)) if tm else ""
    if not title_raw:
        return None
    # og:image (포스터/키비주얼)
    im = re.search(r'<meta[^>]*(?:name|property)=["\']og:image["\'][^>]*content=["\']([^"\']*)["\']', html_text, re.I)
    poster = im.group(1) if im else None
    # 작품명: <...> 꺾쇠 안
    wm = re.search(r"<([^<>]{1,40})>", title_raw)
    work = wm.group(1).strip() if wm else None
    if not work:
        return None
    # 기사 작성일 추출: 'YYYY년 M월 D일' 패턴 (정렬용)
    article_date = None
    dm = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", html_text)
    if dm:
        try:
            y, mo, da = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            article_date = f"{y:04d}-{mo:02d}-{da:02d}"
        except Exception:
            article_date = None
    # 출연진 추출용: HTML 정리(태그 제거 → 엔티티 변환 → 특수공백 정규화)
    clean_text = re.sub(r"<[^>]+>", " ", html_text)      # 태그 제거
    clean_text = htmllib.unescape(clean_text)             # &nbsp; 등 엔티티 변환
    clean_text = clean_text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u200b", "")  # 특수공백 정규화
    # 출연진: 본문 '출연:' 블록 → '…의 캐스팅' 문장 → 제목 순으로 시도
    cast = newsroom_extract_cast_from_body(clean_text)
    if not cast:
        cast = newsroom_extract_cast_from_casting(clean_text)
    if not cast:
        cast = newsroom_extract_cast(title_raw)
    # 공개일: 제목에 'M월 D일 공개' 있으면 연도 추정해서 채움 (없으면 미정)
    rd = None
    return {
        "content_id": "newsroom-" + url.rstrip("/").split("/")[-1],
        "title": work,
        "title_original": None,
        "poster_url": poster,
        "cast": cast,
        "release_date": rd,
        "release_year": None,
        "release_quarter": None,
        "summary": None,
        "content_type": newsroom_classify_type(title_raw),
        "genres": [],
        "rating": None,
        "ott": "netflix",
        "is_original": True,
        "article_date": article_date,
        "availability_status": None,
        "_meta": {
            "sources": {"_all": "netflix_newsroom"},
            "confidence": "confirmed",
            "last_updated": datetime.date.today().isoformat(),
            "needs_review": True,
            "source_url": url,
        },
    }


def newsroom_collect(existing_titles):
    """newsroom_urls.txt의 상세 페이지들을 수집. TMDB에 있는 제목은 건너뜀."""
    items = []
    errors = 0
    try:
        with open(NEWSROOM_URLS_FILE, encoding="utf-8") as f:
            urls = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except FileNotFoundError:
        print(f"INFO: {NEWSROOM_URLS_FILE} 없음 - 뉴스룸 수집 건너뜀", file=sys.stderr)
        return items, 0

    for url in urls:
        try:
            html_text = newsroom_fetch_detail(url)
            parsed = newsroom_parse(url, html_text)
            if not parsed:
                print(f"WARN: 파싱 실패 {url}", file=sys.stderr)
                errors += 1
                continue
            # TMDB에 이미 있으면 건너뜀 (중복 방지)
            if parsed["title"] in existing_titles:
                continue
            items.append(parsed)
            time.sleep(0.3)
        except Exception as e:
            print(f"WARN: 수집 실패 {url}: {e}", file=sys.stderr)
            errors += 1
    return items, errors


MANUAL_OVERRIDES_FILE = "manual_overrides.json"
# 보정 가능한 필드 (이 필드만 덮어씀)
OVERRIDE_FIELDS = ["release_date", "content_type", "genres", "cast", "rating", "summary", "poster_url", "is_original"]


def apply_manual_overrides(items):
    """수동 보정 파일을 자동 수집 결과에 적용 (수동값 최우선).
    - 제목이 일치하는 작품은 지정 필드만 덮어씀
    - 자동 수집에 없는 작품은 새로 추가
    반환: (보정 적용된 items, 보정된 제목 목록)
    """
    try:
        with open(MANUAL_OVERRIDES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        overrides = data.get("overrides", [])
    except FileNotFoundError:
        return items, []
    except Exception as e:
        print(f"WARN: 보정 파일 읽기 실패: {e}", file=sys.stderr)
        return items, []

    by_title = {}
    for it in items:
        by_title.setdefault(it.get("title"), it)

    touched = []
    for ov in overrides:
        title = ov.get("title")
        if not title:
            continue
        target = by_title.get(title)
        if target is None:
            # 자동 수집에 없는 작품 → 새로 추가
            rd = ov.get("release_date")
            year, quarter = derive_quarter(rd) if rd else (None, None)
            new_item = {
                "content_id": "manual-" + title,
                "title": title,
                "title_original": ov.get("title_original"),
                "poster_url": ov.get("poster_url"),
                "cast": ov.get("cast", []),
                "release_date": rd,
                "release_year": year,
                "release_quarter": (f"{year} {quarter}" if year and quarter else None),
                "summary": ov.get("summary"),
                "content_type": ov.get("content_type", "미정"),
                "genres": ov.get("genres", []),
                "rating": ov.get("rating"),
                "ott": ov.get("ott", "netflix"),
                "is_original": ov.get("is_original", True),
                "availability_status": None,
                "_meta": {
                    "sources": {"_all": "manual"},
                    "confidence": "confirmed",
                    "last_updated": datetime.date.today().isoformat(),
                    "needs_review": False,
                    "manual_override": True,
                },
            }
            items.append(new_item)
            by_title[title] = new_item
            touched.append(title)
        else:
            # 기존 작품 → 지정 필드만 덮어씀
            changed = False
            for field in OVERRIDE_FIELDS:
                if field in ov:
                    target[field] = ov[field]
                    target.setdefault("_meta", {}).setdefault("sources", {})[field] = "manual"
                    changed = True
            # 공개일 보정 시 연도/분기 재계산
            if "release_date" in ov:
                y, q = derive_quarter(ov["release_date"]) if ov["release_date"] else (None, None)
                target["release_year"] = y
                target["release_quarter"] = (f"{y} {q}" if y and q else None)
            if changed:
                target.setdefault("_meta", {})["manual_override"] = True
                touched.append(title)
    return items, touched


def write_log(summary, added, updated, errors):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"\n## {ts}", f"- {summary}"]
    if added:
        lines.append(f"- 신규 추가 ({len(added)}건): " + ", ".join(added[:30]) + ("..." if len(added) > 30 else ""))
    if updated:
        lines.append(f"- 정보 갱신 ({len(updated)}건): " + ", ".join(updated[:30]) + ("..." if len(updated) > 30 else ""))
    if errors:
        lines.append(f"- ⚠️ 경고/실패: {errors}")
    block = "\n".join(lines) + "\n"
    # 기존 로그 위에 누적 (최신이 위로)
    header = "# 콘텐츠 라인업 수집 로그\n"
    old = ""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            old = f.read()
            if old.startswith(header):
                old = old[len(header):]
    except Exception:
        pass
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(header + block + old)


def main():
    if not TMDB_TOKEN:
        print("ERROR: 환경변수 TMDB_TOKEN 이 설정되지 않았습니다.", file=sys.stderr)
        print('실행 예: TMDB_TOKEN="본인토큰" python3 collect_lineup.py', file=sys.stderr)
        sys.exit(1)

    this_year = datetime.date.today().year
    years = [this_year - 1, this_year, this_year + 1]
    prev = load_previous()
    errors = 0

    tv_genres = fetch_genres_map("tv")
    movie_genres = fetch_genres_map("movie")

    all_items = []
    for ott in ACTIVE_OTTS:
        for y in years:
            try:
                all_items += discover("tv", y, tv_genres, ott)
                all_items += discover("movie", y, movie_genres, ott)
            except Exception as e:
                errors += 1
                print(f"WARN: {OTT_CONFIG[ott]['name']} {y}년 수집 중 오류: {e}", file=sys.stderr)

    # TMDB에서 모은 제목 집합 (뉴스룸 중복 제거용)
    tmdb_titles = {it["title"] for it in all_items}

    # 넷플릭스 뉴스룸 수집 (TMDB에 없는 신작·미정 작품 보강)
    nr_items, nr_err = newsroom_collect(tmdb_titles)
    errors += nr_err
    all_items += nr_items

    # 티빙 광고페이지 수집 (누적 보관) — TMDB가 놓치는 티빙 신작·줄거리 보강
    ads_items = collect_and_accumulate_tving_ads()
    # 제목 기준으로 기존 TMDB 작품과 병합
    #  - 같은 제목의 TMDB 작품이 있으면: 줄거리·매체배지·예고편·등급을 광고페이지로 보강,
    #    단 포스터(poster_url)는 TMDB 것이 있으면 유지
    #  - 없으면: 광고페이지 작품을 신규 추가
    title_to_item = {}
    for it in all_items:
        title_to_item.setdefault(it["title"].replace(" ", ""), it)
    for ad in ads_items:
        key = ad["title"].replace(" ", "")
        existing = title_to_item.get(key)
        if existing and existing.get("ott") == ad.get("ott"):
            # 같은 제목·같은 OTT → 광고페이지 정보로 보강
            if ad.get("summary"):
                existing["summary"] = ad["summary"]
            if ad.get("source_badge"):
                existing["source_badge"] = ad["source_badge"]
            if ad.get("trailer_url"):
                existing["trailer_url"] = ad["trailer_url"]
            if ad.get("rating") and not existing.get("rating"):
                existing["rating"] = ad["rating"]
            if not existing.get("poster_url") and ad.get("poster_url"):
                existing["poster_url"] = ad["poster_url"]
            existing["is_original"] = ad.get("is_original", existing.get("is_original"))
        else:
            all_items.append(ad)

    # content_id 기준 중복 제거 (뒤에 온 것 우선)
    dedup = {}
    for it in all_items:
        dedup[it["content_id"]] = it
    items = list(dedup.values())

    # 수동 보정 적용 (수동값 최우선, 자동 수집이 덮어쓰지 못함)
    items, overridden = apply_manual_overrides(items)
    # 보정으로 새 작품이 추가됐을 수 있으니 dedup 갱신
    dedup = {it["content_id"]: it for it in items}

    # 신규/갱신 판별
    added, updated = [], []
    for cid, it in dedup.items():
        if cid not in prev:
            added.append(it["title"])
        else:
            old = prev[cid]
            if (old.get("release_date") != it.get("release_date")
                    or old.get("cast") != it.get("cast")
                    or old.get("poster_url") != it.get("poster_url")):
                updated.append(it["title"])

    # 정렬: 공개일 최신순 (없으면 뒤로)
    def sort_key(it):
        rd = it.get("release_date")
        return (0, rd) if rd else (1, "")
    items.sort(key=lambda it: (sort_key(it)[0], sort_key(it)[1]), reverse=False)

    out = {
        "generated_at": datetime.datetime.now().isoformat(),
        "source": "TMDB",
        "range_years": years,
        "items": items,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 티빙·웨이브 작품 목록을 CSV로 별도 저장 (구글 시트로 가져와 확인용)
    # → TMDB가 뭘 수집했는지 보고, 빠진 작품만 수동 시트에 추가하는 용도
    try:
        tw_items = [it for it in items if it.get("ott") in ("tving", "wavve")]
        # 공개일 최신순 정렬
        tw_items.sort(key=lambda it: it.get("release_date") or "", reverse=True)
        ott_name = {"tving": "티빙", "wavve": "웨이브"}
        with open("tving_wavve_list.csv", "w", encoding="utf-8-sig", newline="") as cf:
            w = csv.writer(cf)
            w.writerow(["OTT", "오리지널", "제목", "유형", "공개일", "출연진", "장르", "content_id"])
            for it in tw_items:
                w.writerow([
                    ott_name.get(it.get("ott"), it.get("ott")),
                    "오리지널" if it.get("is_original") else "",
                    it.get("title", ""),
                    it.get("content_type", ""),
                    it.get("release_date", "") or "",
                    ", ".join(it.get("cast", []) or []),
                    ", ".join(it.get("genres", []) or []),
                    it.get("content_id", ""),
                ])
        print(f"  → tving_wavve_list.csv 생성: 티빙·웨이브 {len(tw_items)}건")
    except Exception as e:
        print(f"  WARN: 티빙·웨이브 CSV 생성 실패: {e}", file=sys.stderr)

    summary = f"TMDB {len(all_items)-len(nr_items)}건 + 뉴스룸 {len(nr_items)}건 = 총 {len(items)}건 (대상연도 {years}). 신규 {len(added)} · 갱신 {len(updated)} · 수동보정 {len(overridden)} · 오류 {errors}"
    write_log(summary, added, updated, errors)
    print(summary)


if __name__ == "__main__":
    main()
