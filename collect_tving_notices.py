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

LIST_URL = "https://tving.framer.website/notices"
BASE = "https://tving.framer.website"
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
    # /notices/notice-숫자 링크를 가진 a 태그를 모두 찾는다
    # href="...notices/notice-067" 형태와 그 안의 텍스트(구분 제목 게시일)를 함께 추출
    pattern = re.compile(
        r'href=["\'](?:https?://[^"\']*)?/notices/(notice-\d+)["\'][^>]*>(.*?)</a>',
        re.DOTALL
    )
    for m in pattern.finditer(html_text):
        notice_id = m.group(1)
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
        if notice_id not in items:
            items[notice_id] = {
                "notice_id": notice_id,
                "url": BASE + "/notices/" + notice_id,
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
    구조: # 제목  /  **구분**  /  날짜  /  본문...
    본문은 제목(h1) 이후 ~ 푸터('Advertise with Intelligence') 이전까지.
    """
    # 푸터 이전까지 자르기
    cut = html_text.find("Advertise with Intelligence")
    if cut != -1:
        html_text = html_text[:cut]

    # h1(제목) 위치 찾기 — 그 이후가 본문 영역
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
    title = strip_tags(h1.group(1)) if h1 else ""

    body_area = html_text[h1.end():] if h1 else html_text

    # 블록 요소를 줄바꿈으로, 리스트는 불릿으로 변환
    b = body_area
    b = re.sub(r"<li[^>]*>", "\n• ", b, flags=re.I)
    b = re.sub(r"</li>", "", b, flags=re.I)
    b = re.sub(r"</(p|div|h[1-6]|tr)>", "\n", b, flags=re.I)
    b = re.sub(r"<br\s*/?>", "\n", b, flags=re.I)
    b = re.sub(r"</td>", " ", b, flags=re.I)
    # 링크는 텍스트만 (href는 버림 — 필요시 추후 보존 가능)
    b = strip_tags(b)

    # 본문 앞쪽의 구분/날짜 줄 제거 (제목 다음에 오는 짧은 메타)
    lines = [ln.strip() for ln in b.split("\n")]
    cleaned = []
    for ln in lines:
        if ln == "":
            if cleaned and cleaned[-1] == "":
                continue
            cleaned.append("")
            continue
        # 구분 단독 줄 / 날짜 단독 줄 / '뒤로가기' 제거
        if ln in CATEGORIES:
            continue
        if re.match(r"^\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?$", ln):
            continue
        if ln in ("뒤로가기",):
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
