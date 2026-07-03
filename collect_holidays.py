#!/usr/bin/env python3
"""
공휴일 수집 스크립트 (공공데이터포털 - 한국천문연구원 특일 정보 API)
- 올해·내년 공휴일(국경일·공휴일)을 받아 holidays.json으로 저장
- 콘텐츠 수집과 분리된 별도 워크플로에서 매일 실행
- 대시보드 달력이 holidays.json을 읽어 공휴일 표시 (임시공휴일도 자동 반영)

환경변수:
  HOLIDAY_API_KEY  공공데이터포털 일반 인증키 (Decoding 키 권장)
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

API_KEY = os.environ.get("HOLIDAY_API_KEY", "").strip()
# 특일 정보 - 국경일/공휴일 조회 (getRestDeInfo = 공휴일 정보)
BASE = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
OUTPUT = "holidays.json"


def fetch_month(year, month):
    """해당 연·월의 공휴일 목록(YYYY-MM-DD, 이름) 반환"""
    params = {
        "serviceKey": API_KEY,
        "solYear": str(year),
        "solMonth": f"{month:02d}",
        "_type": "json",
        "numOfRows": "50",
    }
    url = BASE + "?" + urllib.parse.urlencode(params, safe="%+/=")
    req = urllib.request.Request(url)
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8")
    data = json.loads(raw)

    out = []
    try:
        items = data["response"]["body"]["items"]
        if not items:
            return out
        item_list = items.get("item", [])
        if isinstance(item_list, dict):
            item_list = [item_list]
        for it in item_list:
            # isHoliday == "Y" 인 날짜만 (공휴일)
            if str(it.get("isHoliday", "")).strip().upper() != "Y":
                continue
            locdate = str(it.get("locdate", "")).strip()  # 예: 20260101
            name = str(it.get("dateName", "")).strip()
            if len(locdate) == 8:
                ymd = f"{locdate[0:4]}-{locdate[4:6]}-{locdate[6:8]}"
                out.append({"date": ymd, "name": name})
    except (KeyError, TypeError):
        pass
    return out


def main():
    if not API_KEY:
        print("ERROR: HOLIDAY_API_KEY 환경변수가 없습니다. GitHub Secrets 확인 필요.", file=sys.stderr)
        sys.exit(1)

    this_year = datetime.date.today().year
    years = [this_year, this_year + 1]  # 올해 + 내년

    holidays = []
    seen = set()
    errors = 0
    for y in years:
        for m in range(1, 13):
            try:
                for h in fetch_month(y, m):
                    if h["date"] not in seen:
                        seen.add(h["date"])
                        holidays.append(h)
            except Exception as e:
                errors += 1
                print(f"WARN: {y}-{m:02d} 공휴일 조회 오류: {e}", file=sys.stderr)

    holidays.sort(key=lambda h: h["date"])

    result = {
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "years": years,
        "count": len(holidays),
        "holidays": holidays,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"공휴일 {len(holidays)}건 저장 ({years[0]}~{years[-1]}), 오류 {errors}건")
    for h in holidays:
        print(f"  {h['date']}  {h['name']}")


if __name__ == "__main__":
    main()
