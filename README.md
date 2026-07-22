# 나라장터 교육청 B2G 전략 대시보드

data.go.kr 조달청 나라장터 OpenAPI에서 **교육청·연수원이 발주한** 입찰공고/사전규격/낙찰정보를
자동으로 모아 스코어링하고, KPI·추이·랭킹·경쟁사 분석이 담긴 전략 대시보드로 보여준다.

**대시보드 보기 (매일 자동 갱신):** GitHub Pages 배포 후 이 저장소 Settings → Pages에서
URL 확인 (`https://<사용자명>.github.io/<저장소명>/`)

## 구성

| 파일 | 역할 |
| --- | --- |
| `fetch_g2b_listings.py` | data.go.kr OpenAPI 호출 (입찰공고/사전규격/낙찰정보), 교육청·연수원 발주 건만 필터링 |
| `score_listings.py` | 키워드·예산·지역·마감임박도 기준 스코어링 |
| `analytics.py` | 월별추이·지역별·기관별·경쟁사 랭킹, 정책키워드 빈도, 규칙기반 인사이트 집계 |
| `build_dashboard.py` | 스코어링·집계 결과 → 단일 HTML 대시보드(`render_v2`) |
| `run_pipeline.py` | 위 과정을 한 번에 실행 (올해 1/1~오늘 범위) |
| `g2b_config.example.json` | 설정 템플릿(서비스키 자리는 플레이스홀더) |
| `.github/workflows/deploy.yml` | 매일 자동 수집·재생성 후 GitHub Pages 배포 |

## 로컬 실행

```bash
cp g2b_config.example.json g2b_config.json
# g2b_config.json 안의 service_key를 data.go.kr에서 발급받은 값으로 교체
python run_pipeline.py
# live/dashboard_live.html 을 브라우저로 열기
```

## 서비스키 관리

`g2b_config.json`은 `.gitignore`에 포함되어 있어 실제 서비스키가 저장소에 커밋되지 않는다.
GitHub Actions에서는 저장소 Settings → Secrets and variables → Actions에 등록한
`G2B_SERVICE_KEY` 값을 `fetch_g2b_listings.load_config()`가 환경변수로 읽어 덮어쓴다.

## 대상 범위 / 알려진 제한

- 발주기관·수요기관명에 "교육청" 또는 "연수원"이 포함된 건만 수집한다 (`g2b_config.json`의
  `org_filter_keywords`로 조정 가능).
- 발주계획현황서비스(OrderPlanSttusService)는 시도한 오퍼레이션명이 모두 게이트웨이 단계에서
  실패해 아직 미연동 상태다.
- 대시보드의 "AI 인사이트"는 LLM 호출 없이 규칙(전주/전월 대비 증감 등)으로 계산한 값이다.
