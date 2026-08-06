# 수도권 아파트 실거래가 대시보드

국토교통부 아파트 매매 실거래가 OpenAPI(data.go.kr)에서 **서울·인천·경기 77개 시군구**의
최근 12개월 매매 거래를 수집해, KPI·월별 추이·지역 랭킹 대시보드로 보여준다.

## 진행 상태

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 1 | 수집기 (API 호출·XML 파싱·정규화·캐시) + 파서 테스트 | 코드 완료, **API 실측 확인 대기** |
| 2 | 집계 (`apt_analytics.py`) — KPI, 월별 추이, 지역 랭킹 | 코드 완료 (테스트 34개 통과) |
| 3 | 대시보드 HTML 생성 (`build_apt_dashboard.py`) | 예정 |
| 4 | 매일 자동 갱신 + GitHub Pages 배포 | 예정 |

## 구성

| 파일 | 역할 |
| --- | --- |
| `lawd_codes.py` | 수도권 77개 시군구 법정동코드 테이블 (서울 25 · 인천 10 · 경기 42) |
| `fetch_apt_trades.py` | API 호출, XML 파싱, 정규화, gzip 캐시 |
| `apt_analytics.py` | KPI · 월별 추이 · 시군구/법정동 랭킹 · 면적 구간 분포 집계 |
| `test_parse.py` / `test_analytics.py` | 단위 테스트 34개 (네트워크 불필요) |
| `apt_config.example.json` | 설정 템플릿 (인증키 자리는 플레이스홀더) |
| `.github/workflows/probe.yml` | API 실측 확인용 수동 워크플로 |

## 데이터 소스 특성

- **호출 단위**: `LAWD_CD`(시군구 5자리) × `DEAL_YMD`(계약연월 YYYYMM) 1회 = 그 지역 그 달 전체 거래
- **수집 비용**: 77개 시군구 × 12개월 = **924회 호출** (개발계정 일일 트래픽 1만건 한도 내)
- **캐시 전략**: 과거 월은 확정값이라 재호출하지 않고 `data/raw/{시군구}/{연월}.json.gz` 에서 읽는다.
  신고 지연·해제(취소) 반영을 위해 최근 3개월만 매번 재수집한다 (`--refresh-months`).
- **용량**: 수도권 12개월이면 원본 25만 건 안팎. 비압축 JSON은 100MB를 넘어 gzip으로 저장한다(약 1/8).

## 실행

```bash
cp apt_config.example.json apt_config.json
# apt_config.json 의 service_key 를 data.go.kr 발급값으로 교체
# (또는 export MOLIT_SERVICE_KEY=...)

python test_parse.py && python test_analytics.py        # 단위 테스트
python fetch_apt_trades.py probe --lawd 11680 --ymd 202606   # 단일 호출 실측
python fetch_apt_trades.py fetch --months 12            # 수도권 전체 수집
python fetch_apt_trades.py fetch --months 12 --sido 서울특별시  # 서울만
python apt_analytics.py live/trades.json live/analytics.json  # 집계
```

## 집계 규칙

- **해제(취소) 거래는 제외한다.** 성사되지 않은 계약이라 가격 통계를 왜곡한다. 원본에는
  `canceled` 플래그로 보존한다.
- **대표 단가는 중위 평당가**를 쓴다. 평균은 초고가 몇 건에 끌려가는데, 지역별로 월 거래량이
  적은 경우가 많아 그 영향이 특히 크다.
- 전용면적이 없는 건은 **거래량에는 포함, 단가 계산에서는 제외**한다.
- 법정동 랭킹은 표본 10건 미만이면 중위값이 튀므로 제외한다.
- 최근 2개월은 신고 지연(계약 후 30일 내 신고)으로 거래량이 과소 집계되며, `provisional`
  플래그로 표시해 대시보드에서 잠정치로 구분한다.

## 인증키 관리

`apt_config.json` 은 `.gitignore` 에 있어 실제 인증키가 저장소에 커밋되지 않는다.
GitHub Actions 에서는 Settings → Secrets and variables → Actions 에 등록한
`MOLIT_SERVICE_KEY` 를 `load_config()` 가 환경변수로 읽어 덮어쓴다.

## 알려진 제한 / 확인 필요 사항

- **응답 필드명이 아직 실측되지 않았다.** 파서는 `<item>` 자식 태그를 이름 그대로 전부 원본
  캐시에 담고 정규화 단계에서만 필드를 매핑하므로, 필드명이 달라도 재수집 없이 매핑만 고치면 된다.
  `probe` 워크플로로 실제 필드명을 먼저 확인할 것.
- **부천시**는 2016년 일반구 폐지로 `41190` 단일 코드를 쓴다. 과거 거래분이 구 코드
  (`41192`/`41194`/`41196`)로 남아 있으면 `lawd_codes.OLD_CODES` 를 `REGIONS` 에 합쳐야 한다.
- 해제(취소) 거래는 `canceled` 플래그로 보존하되, 집계에서는 기본 제외할 예정이다.
- 실거래가는 **계약일 기준 신고분**이라 최근 1~2개월치는 신고 지연으로 과소 집계된다.
