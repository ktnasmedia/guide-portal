#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 광고 공지사항 자동 수집 스크립트
- 소스: https://tving.framer.website/notices (목록) + 각 공지 개별 페이지 (본문)
- 출력: tving_notices.json (누적 보관, notice_id 기준 중복 제거)
- 동작:
    1) 목록 페이지에서 공지 링크(notice-xxx) + 구분 + 제목 + 게시일 추출
    2) 각 공지 개별 페이지에서 본문 추출
    3) 이미 수집한 notice_id 는 건너뛰고 새 것만 본문 수집 (효율)
    4) 누적 결과를 게시일 기준 최신순 정렬하여 저장

표준 라이브러리(urllib)만 사용 — GitHub Actions에서 별도 설치 불필요.
로컬 실행:  python3 collect_tving_notices.py
"""

import os
import re
import json
import time
import html
import urllib.request
import urllib.error

LIST_URL = "https://www.tvingads.com/notices"
BASE = "https://www.tvingads.com"
OUT_FILE = "tving_notices.json"

CATEGORIES = ["공지", "솔루션", "시스템", "콘텐츠", "프로모션", "기타"]


def fetch(url, timeout=25):
    """페이지 HTML 가져오기 (User-Agent 포함)"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def strip_tags(s):
    """HTML 태그 제거 + 엔티티 디코딩 + 공백 정리"""
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\u200b", "").replace("\ufeff", "")
    return s.strip()


def parse_list(html_text):
    """
    목록 HTML에서 공지 항목 추출.
    각 항목 링크 형태: /notices/notice-067  (구분/제목/게시일이 같은 a 태그 텍스트에 포함)
    반환: [{notice_id, url, category, title, date}]
    """
    items = {}
    # /notices/<slug> 링크를 모두 찾는다. slug 는 notice-067 또는 이름 형식(kbosponsorship-2607update 등)
    pattern = re.compile(
        r'href=["\'](?:\.?/|https?://[^"\']*?/)?notices/([A-Za-z0-9][A-Za-z0-9\-_]*)["\'][^>]*>(.*?)</a>',
        re.DOTALL
    )
    for m in pattern.finditer(html_text):
        slug = m.group(1)
        # 목록 페이지 자기 자신(/notices)이나 빈 slug 제외
        if not slug or slug == 'notices':
            continue
        inner = strip_tags(m.group(2))
        if not inner:
            continue
        # inner 예: "공지 2026년 7월 KBO 광고 청약 일정 안내 26. 6. 11."
        cat = ""
        rest = inner
        for c in CATEGORIES:
            if inner.startswith(c):
                cat = c
                rest = inner[len(c):].strip()
                break
        # 끝의 날짜(YY. M. D.) 분리
        date = ""
        dm = re.search(r"(\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*$", rest)
        if dm:
            date = dm.group(1).strip()
            title = rest[:dm.start()].strip()
        else:
            title = rest.strip()
        if slug not in items:
            items[slug] = {
                "notice_id": slug,
                "url": BASE + "/notices/" + slug,
                "category": cat or "기타",
                "title": title,
                "date": normalize_date(date),
            }
    return list(items.values())


def normalize_date(d):
    """'26. 6. 11.' → '2026-06-11' (실패 시 원본 반환)"""
    m = re.match(r"(\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})", d)
    if not m:
        return d
    yy, mm, dd = m.groups()
    return "20%s-%02d-%02d" % (yy, int(mm), int(dd))


def parse_detail(html_text):
    """
    개별 공지 페이지에서 본문 추출.
    1) script/style/head/noscript 등 코드 영역을 먼저 통째로 제거
    2) 마지막 h1(제목) 이후 ~ 푸터/네비 이전까지를 본문으로
    3) 블록 태그를 줄바꿈·불릿으로 변환 후 태그 제거
    4) 구분/날짜/네비게이션 잔여 줄 정리
    """
    # 1) 코드/메타 영역 통째 제거
    b = html_text
    b = re.sub(r"<head[^>]*>.*?</head>", " ", b, flags=re.I | re.S)
    b = re.sub(r"<script[^>]*>.*?</script>", " ", b, flags=re.I | re.S)
    b = re.sub(r"<style[^>]*>.*?</style>", " ", b, flags=re.I | re.S)
    b = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", b, flags=re.I | re.S)
    b = re.sub(r"<svg[^>]*>.*?</svg>", " ", b, flags=re.I | re.S)

    # 푸터 이후 제거
    cut = b.find("Advertise with Intelligence")
    if cut != -1:
        b = b[:cut]
    # 하단 CTA 영역 제거
    cut2 = b.find("캠페인 시작을 위한 첫 걸음")
    if cut2 != -1:
        b = b[:cut2]

    # 2) 제목(h1) 추출 후 그 이후를 본문 영역으로
    h1s = list(re.finditer(r"<h1[^>]*>(.*?)</h1>", b, re.DOTALL))
    title = ""
    if h1s:
        title = strip_tags(h1s[-1].group(1))
        body_area = b[h1s[-1].end():]
    else:
        body_area = b

    # 3) 블록 태그 변환
    x = body_area
    # 이미지: <img src="..."> → [[IMG:주소]] 마커로 보존
    x = re.sub(
        r'<img[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>',
        lambda m: "\n[[IMG:" + m.group(1) + "]]\n",
        x, flags=re.I
    )
    # 링크: <a href="...">텍스트</a> → [텍스트](주소) 마커로 보존
    def _link(m):
        href = m.group(1).strip()
        txt = strip_tags(m.group(2)).strip()
        if not href or href.startswith("mailto:") or href.startswith("#"):
            return txt
        # 상대경로 → 절대경로
        if href.startswith("./"):
            href = BASE + "/" + href[2:]
        elif href.startswith("/"):
            href = BASE + href
        if not txt:
            txt = href
        return "[" + txt + "](" + href + ")"
    x = re.sub(r'<a\s[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', _link, x, flags=re.I | re.S)

    x = re.sub(r"<li[^>]*>", "\n• ", x, flags=re.I)
    x = re.sub(r"</li>", "", x, flags=re.I)
    x = re.sub(r"</(p|div|h[1-6]|tr)>", "\n", x, flags=re.I)
    x = re.sub(r"<br\s*/?>", "\n", x, flags=re.I)
    x = re.sub(r"</td>", " ", x, flags=re.I)
    x = strip_tags(x)

    # 4) 잔여 줄 정리 (구분/날짜/네비게이션/헤더 텍스트 제거)
    NAV_NOISE = {
        "광고정보센터", "TVING Ads", "콘텐츠", "광고 솔루션", "인사이트",
        "이용 방법 보기", "광고 시작하기", "이용 방법", "공지사항", "공지 사항",
        "광고 문의", "솔루션 소개서", "뉴스레터", "광고 문의하기", "뒤로가기",
        "Why TVING", "TVING NEWS", "콘텐츠 라인업", "일반 광고", "KBO리그 광고",
        "TVING Labs", "TVING Special", "마케팅 트렌드", "성공 사례", "개인정보처리방침",
        "전체", "TVING 광고 솔루션 운영, 정책, 시스템 변경 사항을 안내합니다.",
    }
    lines = [ln.strip() for ln in x.split("\n")]
    cleaned = []
    for ln in lines:
        if ln == "":
            if cleaned and cleaned[-1] == "":
                continue
            cleaned.append("")
            continue
        if ln in CATEGORIES:
            continue
        if ln in NAV_NOISE:
            continue
        if re.match(r"^\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?$", ln):
            continue
        # 저작권 줄 제거
        if ln.startswith("©"):
            continue
        cleaned.append(ln)
    body = "\n".join(cleaned).strip()
    return title, body


def load_existing():
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return {n["notice_id"]: n for n in data.get("notices", [])}
        except Exception:
            return {}
    return {}


def main():
    print("티빙 공지 목록 수집 중...")
    list_html = fetch(LIST_URL)
    items = parse_list(list_html)
    print("  목록에서 %d개 공지 발견" % len(items))

    existing = load_existing()
    print("  기존 누적 %d개" % len(existing))

    result = dict(existing)  # notice_id → record
    new_count = 0
    for it in items:
        nid = it["notice_id"]
        if nid in result and result[nid].get("body"):
            # 이미 본문까지 수집됨 → 메타만 갱신
            result[nid].update({
                "category": it["category"],
                "title": it["title"],
                "date": it["date"],
            })
            continue
        # 새 공지 → 본문 수집
        try:
            detail_html = fetch(it["url"])
            d_title, body = parse_detail(detail_html)
            it["title"] = d_title or it["title"]
            it["body"] = body
            result[nid] = it
            new_count += 1
            print("  + 수집: %s | %s" % (nid, it["title"][:30]))
            time.sleep(0.5)  # 과도한 요청 방지
        except Exception as e:
            print("  ! 실패: %s (%s)" % (nid, e))
            # 본문 없이 메타만이라도 저장
            it.setdefault("body", "")
            result[nid] = it

    # 최신순 정렬 (날짜 desc, 같으면 notice_id desc)
    records = list(result.values())
    def sortkey(r):
        return (r.get("date", ""), r.get("notice_id", ""))
    records.sort(key=sortkey, reverse=True)

    out = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(records),
        "notices": records,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("완료. 총 %d개 (신규 %d개) → %s" % (len(records), new_count, OUT_FILE))


if __name__ == "__main__":
    main()
