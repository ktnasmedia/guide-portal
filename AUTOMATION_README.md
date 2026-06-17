# 콘텐츠 라인업 자동 수집 - 운영 안내

## 무엇을 하는 시스템인가
넷플릭스 한국 콘텐츠 라인업을 매일 자동으로 수집해 가이드 포탈의 '콘텐츠 라인업' 탭을 갱신합니다.
사람이 손대지 않아도 GitHub Actions가 매일 새벽에 스크립트를 돌려 최신 데이터로 유지합니다.

## 구성 파일
- `collect_lineup.py` : 수집 스크립트 (TMDB에서 데이터를 받아 content_lineup.json 생성)
- `content_lineup.json` : 포탈이 읽는 실제 데이터 (스크립트가 자동 갱신)
- `content_schema.json` : 데이터 형식 정의 (참고용 문서)
- `collection_log.md` : 실행 이력 (한 줄 요약 + 변경 작품 목록 누적)
- `.github/workflows/lineup_collect.yml` : 자동 실행 설정
- `ad_guideportal_dashboard.html` : 포탈 화면

## 수집 범위
- 대상 OTT: 넷플릭스 (TMDB provider_id = 8)
- 지역: 한국 (KR)
- 제작국: 한국 (with_origin_country=KR)
- 기간: 전년도 / 올해 / 내년 (실행 시점 기준 자동 계산)
- 종류: 시리즈 + 영화

## 데이터 출처와 신뢰도
- 기본 메타데이터(제목·출연·공개일·장르·등급·포스터): TMDB API (confirmed)
- 공개 상태(공개중/공개예정): 포탈에서 접속일과 공개일을 비교해 자동 판정
- 빈 값: 화면에 '미정'으로 표시
- 넷플릭스 뉴스룸 캐스팅·키비주얼은 향후 보강 예정 (현재는 TMDB 기준)

## 토큰 관리 (중요)
- TMDB 토큰은 코드에 절대 넣지 않습니다.
- GitHub 저장소의 Settings > Secrets and variables > Actions 에 `TMDB_TOKEN` 이름으로 등록합니다.
- 스크립트는 환경변수 TMDB_TOKEN 에서 토큰을 읽습니다.

## 수동 실행 방법
- 로컬: `TMDB_TOKEN="본인토큰" python3 collect_lineup.py`
- GitHub: Actions 탭 > '콘텐츠 라인업 자동 수집' > Run workflow 버튼

## 실행 주기
- 매일 새벽 3시(KST) 자동 실행
- 변경사항이 있을 때만 커밋됨 (없으면 커밋 생략)
