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

# 매체 배지가 글자가 아니라 SVG 아이콘으로만 표시되는 카드가 있다.
# 화면 글자만 읽으면 그런 카드는 매체를 놓치므로(예: '그래, 이혼하자'),
# 아이콘이 가리키는 심볼 id로도 매체를 읽는다.
# 주의: 이 id는 티빙이 페이지를 다시 배포하면 바뀔 수 있다.
#       모르는 id가 나오면 수집 로그에 경고를 남기도록 해 두었다.
MEDIA_ICON_IDS = {
    "svg177245548_772":   "T",
    "svg-188789769_750":  "W",
    "svg1271991855_2234": "T ORIGINAL",
    "svg1439202280_5396": "W ORIGINAL",
    "svg-222033957_1108": "T ONLY",
}
# 매체가 아닌 배지 아이콘 — 알고 있지만 매체로 세지 않는다
NON_MEDIA_ICON_IDS = {
    "svg-1575766977_1186": "Sponsored",
    "svg1767110964_1186":  "Special",
    "svg-1272718827_400":  "Icon",      # 일반 아이콘
    "svg1698067022_413":   "Video",     # 예고편 재생
}
# 작품이 아닌 섹션 제목 — 배지 판독에서 제외
SECTION_TITLES = ("신작 및 주목할 콘텐츠", "향후 3개월 오픈 예정 콘텐츠",
                  "지금 주목해야 할 인기작과 공개 예정작", "성·연령별 시청 상위")
# 제목 자리에 있지만 작품이 아닌 라벨
NON_TITLE_LABELS = ("예고편미리보기", "더보기", "PDF다운로드", "다운로드하기")
# 매체를 뜻하는 이름(사람이 붙인 값이라 id보다 덜 바뀐다) — 보조 판독용
MEDIA_NAME_RE = re.compile(
    r'data-framer-name="((?:T|W)(?:&amp;W)?(?:\s*(?:Only|Original))?)\s*-\s*(?:sm|lg)"',
    re.I)
ICON_USE_RE = re.compile(r'href="#(svg[\w-]+)"')


def media_by_icons(raw_html):
    """제목(h3) 사이 구간을 한 카드로 보고, 그 안의 아이콘에서 매체를 읽는다.
    돌려주는 값: {제목: [매체, ...]} / 처음 보는 아이콘 id 목록"""
    result, unknown = {}, set()
    # 작품 제목은 섹션마다 태그가 다르다.
    #  - 아래쪽 카드형 섹션: <h3>
    #  - 위쪽 가로 목록 섹션: <p class="... framer-styles-preset-1h4d2v7 ...">
    # 둘 다 잡지 않으면 위쪽 섹션 작품이 통째로 누락된다(T ONLY 8건이 그랬음).
    heads = []
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", raw_html, re.S):
        heads.append((m.start(), m.end(), re.sub(r"<[^>]+>", "", m.group(1)).strip()))
    for m in re.finditer(
            r'<p[^>]*framer-styles-preset-1h4d2v7[^>]*>(.*?)</p>', raw_html, re.S):
        heads.append((m.start(), m.end(), re.sub(r"<[^>]+>", "", m.group(1)).strip()))
    heads.sort()
    prev = 0
    for start, end, title in heads:
        seg = raw_html[prev:start]      # 이전 제목 끝 ~ 이번 제목 = 이 카드의 배지 영역
        prev = end
        if not title:
            continue
        # 섹션 제목·작품이 아닌 라벨은 건너뛴다 (앞 구간 아이콘이 통째로 섞임)
        if any(title.startswith(x) for x in SECTION_TITLES):
            continue
        if title.replace(" ", "") in NON_TITLE_LABELS:
            continue
        found = []
        for m in ICON_USE_RE.finditer(seg):
            sid = m.group(1)
            if sid in MEDIA_ICON_IDS:
                found.append(MEDIA_ICON_IDS[sid])
            elif sid in NON_MEDIA_ICON_IDS:
                pass                    # 협찬·특판 등 매체가 아닌 배지
            elif "svgContainer" in seg[max(0, m.start() - 400):m.start()]:
                unknown.add(sid)        # 배지 자리인데 모르는 아이콘
        # 이름으로도 한 번 더 (T&W 처럼 한 덩어리로 적힌 경우)
        for m in MEDIA_NAME_RE.finditer(seg):
            nm = m.group(1).replace("&amp;", "&").upper()
            if "&" in nm:
                found += ["T", "W"]
            else:
                found.append(nm)
        if found:
            seen = []
            for f in found:
                if f not in seen:
                    seen.append(f)
            result[title.replace(" ", "")] = seen
    return result, sorted(unknown)
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
    데이터 구조: "포스터URL"(+srcSet 중복) ... "제목" ... 출연진 ... 줄거리
    포스터 URL 뒤 가장 가까운 한글 제목으로 매칭. 카드 HTML 구조 비의존.
    포스터가 든 script 위치가 페이지 개편으로 바뀔 수 있어, 인덱스를 고정하지 않고
    포스터 URL이 가장 많은 script 를 자동으로 찾는다.
    반환: {제목(공백제거): poster_url}
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if not scripts:
        return {}
    poster_url_re = re.compile(
        r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)'
    )
    # 포스터 URL이 가장 많이 든 script 선택
    best_idx, best_cnt = -1, 0
    for i, s in enumerate(scripts):
        c = len(poster_url_re.findall(s))
        if c > best_cnt:
            best_cnt, best_idx = c, i
    if best_idx < 0:
        return {}
    data = scripts[best_idx]
    posters = {}
    for m in re.finditer(
        r'"(https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png))\?[^"]*"',
        data,
    ):
        url = m.group(1)
        # srcSet 중복 URL·토큰이 끼어 제목이 멀어질 수 있어 범위를 넓게(600자)
        after = data[m.end():m.end() + 600]
        # 포스터 뒤 문자열 토큰들을 순서대로 수집 (JSON 구조 문자열은 제외)
        cands = []
        for cand in re.finditer(r'"([^"]{1,50})"', after):
            txt = cand.group(1)
            if txt.startswith("http") or "framerusercontent" in txt:
                continue
            # JSON 구조 조각(콜론·중괄호·대괄호·type/value 키 등) 제외 — 실제 값만
            if re.search(r'[:{}\[\]]', txt):
                continue
            if txt in ("type", "value", "src", "srcSet"):
                continue
            cands.append(txt)
            if len(cands) >= 6:  # 제목은 앞쪽에 있으니 앞 몇 개만 보면 충분
                break
        # 제목 구성: 한글 포함 토큰을 찾되, 바로 앞이 숫자/연도 토큰이면 이어붙임
        tm = None
        for i, txt in enumerate(cands):
            if re.search(r"[가-힣]", txt):
                # 앞 토큰이 순수 숫자(연도 등)면 제목의 일부일 수 있어 병합
                if i > 0 and re.fullmatch(r"\d{2,4}", cands[i - 1].strip()):
                    tm = cands[i - 1].strip() + " " + txt
                else:
                    tm = txt
                break
        if tm:
            key = tm.replace(" ", "")
            posters.setdefault(key, url)
    return posters


def extract_headings(soup):
    """작품 제목 후보 모음.
    섹션마다 제목 태그가 달라서(<h3> 또는 <p class="...preset-1h4d2v7...">)
    둘 다 봐야 위쪽 가로 목록 섹션의 작품이 누락되지 않는다."""
    heads = set()
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = tag.get_text(strip=True)
        if t and len(t) <= 40:
            heads.add(t)
    for tag in soup.find_all("p"):
        cls = " ".join(tag.get("class") or [])
        if "framer-styles-preset-1h4d2v7" not in cls:
            continue
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
             "지금 주목해야", "향후 3개월", "오픈 예정",
             "신작 및 주목할", "주목할 콘텐츠", "PDF 다운로드", "다운로드하기",
             "예고편 미리보기", "예고편미리보기")
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
    icon_media, unknown_icons = media_by_icons(html)
    if unknown_icons:
        print(f"  [경고] 처음 보는 매체 아이콘 {len(unknown_icons)}종: {', '.join(unknown_icons[:5])}")
        print("        티빙이 페이지를 바꿨을 수 있습니다. MEDIA_ICON_IDS 갱신이 필요합니다.")

    seen, uniq = set(), []
    for w in works:
        key = w["title"].replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        w["poster"] = posters.get(key, "")   # 제목 기준 포스터 매칭
        # 글자로 매체를 못 읽은 카드는 아이콘 판독 결과로 채운다
        if not w["media"] and key in icon_media:
            w["media"] = icon_media[key]
        elif key in icon_media:
            # 글자로 읽은 것과 아이콘이 다르면 아이콘 쪽을 합친다(누락 방지)
            for m in icon_media[key]:
                if m not in w["media"]:
                    w["media"].append(m)
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
