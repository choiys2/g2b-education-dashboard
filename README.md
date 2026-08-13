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
| `build_news_briefing.py` | `briefings/*.json` → 조간 신문 지면(`/news/`) 렌더링 |
| `.github/workflows/deploy.yml` | 매일 06:00 KST 자동 수집·재생성 후 GitHub Pages 배포 |
| `.github/workflows/news.yml` | `briefings/` 변경 시 신문 지면만 재생성·배포 (나라장터 API 미호출) |

## 조간 브리핑 (`/news/`)

매일 아침 경제·사회·교육 뉴스를 신문 지면 한 장으로 보여주는 별도 페이지다.
대시보드와 데이터 소스를 공유하지 않고, `briefings/` 안의 날짜별 JSON 하나만 읽는다.

```bash
python build_news_briefing.py          # briefings/ -> live/news/
# live/news/index.html 을 브라우저로 열기 (최신호)
```

발행 호수는 `briefings/` 안의 날짜 순서로 자동 부여되고, 각 호 하단 셀렉트로 지난 호를 오간다.
새 호를 추가하려면 `briefings/YYYY-MM-DD.json`을 같은 스키마로 하나 더 넣으면 된다
(`briefings/2026-08-13.json`이 레퍼런스). 필드 구성:

| 키 | 내용 |
| --- | --- |
| `date` / `weekday` | 발행일. `weekday`는 생략 가능(날짜에서 계산) |
| `indices[]` | 상단 지수 스트립. `label` / `value` / `delta` / `dir`(`up`·`down`·`flat`) |
| `lead` | 1면 톱. `kicker` / `headline` / `sub` / `lede` / `facts[]`(`label`+`text`) |
| `sections[]` | `id` / `name` / `tone`(`carmine`·`slate`·`forest`) / `items[]` |
| `sections[].items[]` | `title` / `body` / `tags[]` / `priority`(true면 전폭 기사로 강조) |
| `implications[]` | 하단 시사점 박스. `news` + `impact` |
| `sources` | 판권에 표기할 출처 |

본문 문자열에는 `<strong>` `<em>` `<br>`만 살아남고 나머지 마크업은 이스케이프된다.

### 자동 갱신 경로

매일 08:03 KST에 Claude 예약 작업이 그날 뉴스를 모아 `briefings/<오늘>.json`을 만들고
`main`에 커밋·푸시한다. 그 푸시가 `news.yml`을 깨우면 신문 지면만 다시 만들어 배포한다.

```
08:03  Claude 예약 작업 → briefings/YYYY-MM-DD.json 커밋 → main 푸시
       ↓ (push 트리거, paths: briefings/**)
       news.yml → build_news_briefing.py → 현재 배포본 회수 + news/ 교체 → Pages 배포
```

`news.yml`은 나라장터 OpenAPI를 호출하지 않으므로 G2B 장애일에도 브리핑은 정상 갱신된다.
다만 Pages 배포본은 저장소당 하나뿐이라, 이 워크플로는 **지금 떠 있는 사이트를 curl로
내려받아 `news/`만 갈아끼운 뒤** 다시 올린다. 대시보드 회수에 실패하면 배포를 건너뛰고
(빈 사이트로 덮어쓰지 않는다) 다음 06:00 정기 배포에서 함께 반영된다.

`deploy.yml`도 같은 렌더링 스텝을 갖고 있어, 06:00 정기 배포 때 지면이 다시 만들어진다.
두 워크플로는 `concurrency: pages` 그룹을 공유해 배포가 서로 밟지 않는다.

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
