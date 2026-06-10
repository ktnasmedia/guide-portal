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
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

# ── 설정 ──
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w500"
NETFLIX_PROVIDER_ID = 8     # 넷플릭스 watch provider (볼 수 있음)
NETFLIX_NETWORK_ID = 213    # 넷플릭스 network (오리지널 제작/배급)
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


def _discover_pages(media_type, base_params, genre_map):
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
            out[it["id"]] = normalize(media_type, it, genre_map)
        if page >= data.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.2)
    return out


def discover(media_type, year, genre_map):
    """특정 연도의 넷플릭스 KR 콘텐츠 수집.
    TV: provider(볼 수 있음) + network(넷플릭스 제작) OR 합집합 → 신작 누락 방지
    영화: network 개념이 없으므로 provider만 사용
    """
    date_field = "first_air_date" if media_type == "tv" else "primary_release_date"
    common = {
        "language": LANG,
        "sort_by": f"{date_field}.desc",
        f"{date_field}.gte": f"{year}-01-01",
        f"{date_field}.lte": f"{year}-12-31",
    }
    merged = {}

    # provider 조건 (넷플릭스에서 볼 수 있는 작품)
    prov_params = dict(common)
    prov_params.update({"watch_region": REGION, "with_watch_providers": NETFLIX_PROVIDER_ID,
                        "with_origin_country": ORIGIN_COUNTRY})
    merged.update(_discover_pages(media_type, prov_params, genre_map))

    # network 조건 (넷플릭스가 만든 오리지널) — TV만 적용
    if media_type == "tv":
        net_params = dict(common)
        net_params.update({"with_networks": NETFLIX_NETWORK_ID, "with_origin_country": ORIGIN_COUNTRY})
        merged.update(_discover_pages(media_type, net_params, genre_map))

    return list(merged.values())


def fetch_is_original(media_type, tmdb_id):
    """넷플릭스 오리지널 여부 판별.
    TV: networks에 넷플릭스(213) 포함 여부
    영화: production_companies에 넷플릭스 계열 포함 여부
    """
    try:
        d = http_get(f"/{media_type}/{tmdb_id}", {"language": LANG})
        if media_type == "tv":
            net_ids = [n.get("id") for n in d.get("networks", [])]
            return NETFLIX_NETWORK_ID in net_ids
        else:
            # 영화: 제작사명에 Netflix 포함 여부로 판단
            companies = [c.get("name", "") for c in d.get("production_companies", [])]
            return any("Netflix" in c for c in companies)
    except Exception:
        return False


def normalize(media_type, raw, genre_map):
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

    is_orig = fetch_is_original(media_type, tmdb_id)

    return {
        "content_id": f"tmdb-{media_type}-{tmdb_id}",
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
        "ott": "netflix",
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
    """제목에서 'A-B-C' 또는 'AXB' 형태 출연진 추출"""
    m = re.search(r"([가-힣]{2,4}(?:[-X×][가-힣]{2,4}){1,6})", title)
    if not m:
        return []
    return [n for n in re.split(r"[-X×]", m.group(1)) if 2 <= len(n) <= 4]


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
    # 공개일: 제목에 'M월 D일 공개' 있으면 연도 추정해서 채움 (없으면 미정)
    rd = None
    return {
        "content_id": "newsroom-" + url.rstrip("/").split("/")[-1],
        "title": work,
        "title_original": None,
        "poster_url": poster,
        "cast": newsroom_extract_cast(title_raw),
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
    for y in years:
        try:
            all_items += discover("tv", y, tv_genres)
            all_items += discover("movie", y, movie_genres)
        except Exception as e:
            errors += 1
            print(f"WARN: {y}년 수집 중 오류: {e}", file=sys.stderr)

    # TMDB에서 모은 제목 집합 (뉴스룸 중복 제거용)
    tmdb_titles = {it["title"] for it in all_items}

    # 넷플릭스 뉴스룸 수집 (TMDB에 없는 신작·미정 작품 보강)
    nr_items, nr_err = newsroom_collect(tmdb_titles)
    errors += nr_err
    all_items += nr_items

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

    summary = f"TMDB {len(all_items)-len(nr_items)}건 + 뉴스룸 {len(nr_items)}건 = 총 {len(items)}건 (대상연도 {years}). 신규 {len(added)} · 갱신 {len(updated)} · 수동보정 {len(overridden)} · 오류 {errors}"
    write_log(summary, added, updated, errors)
    print(summary)


if __name__ == "__main__":
    main()
