# 통합 대시보드 자동화 — 설정 가이드

기존에 이미 매일 자동으로 도는 `나라장터 종합` 대시보드(choiys2.github.io/g2b-education-dashboard)에,
나이스 학교데이터·AI 선도학교·자사 영업 파이프라인까지 합친 **통합 대시보드**를 추가로 매일 자동
생성·배포하도록 확장했습니다. 1번(시크릿)과 4번(커밋·푸시)만 해주시면 다음 날 새벽부터 바로 돌아갑니다.
2번·3번은 선택 사항입니다.

## 1. GitHub 저장소에 시크릿(secrets) 3개 추가

`github.com/choiys2/g2b-education-dashboard` → **Settings → Secrets and variables → Actions** →
**New repository secret**

| 이름 | 값 | 비고 |
|---|---|---|
| `NEIS_KEY` | `35217cc2959b490990e25e95a1085b19` | 나이스 개방포털 마이페이지에서 발급받은 인증키(이미 갖고 계신 것) |
| `ODCLOUD_KEY` | `d8ac83ebf8376f59ad04d82aae37e8a69a2661b0d1b6a624d9bc8415a65ff464` | 공공데이터포털(data.go.kr) 일반 인증키. 지금 쓰시는 `G2B_SERVICE_KEY`와 같은 값입니다 — 나라장터·AI선도학교 둘 다 같은 계정 키를 씁니다 |
| `KOSIS_KEY` | `OTg3OTkzNWRlOTIxZjNmZGUzMzA0OGIxZTgyYTUxOWU=` | KOSIS(국가통계포털) Open API 인증키. "영업 파이프라인" 탭의 시도교육청 교육재정 규모 표에 씁니다 |

기존에 이미 등록돼 있는 `G2B_SERVICE_KEY`는 그대로 두시면 됩니다.

## 2. (선택) 파이프라인 상태 인라인 변경을 쓰려면 Apps Script 배포

"영업 파이프라인" 탭에서 상태를 클릭 한 번으로 구글시트에 바로 반영하고 싶다면:

1. 자사 파이프라인 구글시트를 여세요.
2. 확장 프로그램 → Apps Script 클릭.
3. `pipeline_status_webhook.gs.txt` 파일 내용 전체를 붙여넣으세요.
4. 파일 안의 `SECRET_TOKEN`을 본인만 아는 임의의 긴 문자열로 반드시 바꾸세요.
5. `SHEET_NAME`을 실제 탭 이름으로 확인/수정하세요.
6. 배포 → 새 배포 → 웹 앱 (실행 계정: 나 / 액세스 권한: 전체).
7. 나오는 웹 앱 URL을, 대시보드 "영업 파이프라인" 탭의 "⚙ 상태연동 설정"에 4번 토큰과 함께 입력·저장.

건너뛰어도 무방합니다 — 설정하지 않으면 그 탭은 지금처럼 읽기 전용 칩으로만 보입니다.

## 3. (선택) 입찰 마감일 캘린더 구독

`ics_feed.py`가 매일 `live/g2b_deadlines.ics`를 만들고, `/full/calendar.ics`로 배포됩니다.
구글 캘린더 → 다른 캘린더 추가 → URL로 추가 → `https://choiys2.github.io/g2b-education-dashboard/full/calendar.ics`
입력. 한 번만 등록해두면 캘린더 앱이 알아서 주기적으로(보통 몇 시간~하루 간격) 다시 읽어갑니다.

## 4. 이번에 새로 생긴 파일들을 커밋·푸시

아래 파일들을 만들어뒀는데, **제가 대신 `git push`는 하지 않았습니다**(계정 접근 권한 관련 조치라 확인 없이 하지 않는 게 맞다고 판단했습니다). 검토 후 직접 커밋해주세요.

```
g2b_full_export.py        나라장터 분석 데이터를 analytics.py로 재계산해 JSON으로 내보냄
neis_full_export.py       나이스 학교수 + AI 선도학교(odcloud) + 연락처/학급수 조회
own_pipeline_export.py    자사 영업 파이프라인 구글시트 조회 (안전 필드만, 담당자 자동 익명화)
beta_features.py          "베타" 탭 4종 계산 — 경쟁사 수주 추세, 파이프라인 모멘텀, 낙찰가 추정, 지표 추세예측
combine_dashboard.py      위 4개 + 기존 full_live.json을 합쳐 통합 대시보드 HTML 생성
history_tracker.py        매일 핵심 지표를 history/daily_stats.jsonl에 한 줄씩 누적
ics_feed.py                AI 관련 진행중 공고의 마감일을 .ics 캘린더 피드로 내보냄
pdf_report.py              핵심 지표 1페이지 PDF 리포트 생성(한글 TTF 임베드, 대시보드 상단 다운로드 링크)
kosis_edu_finance.py       KOSIS 시도교육청 "교육비특별회계 세출결산" 17개 지역 조회(아래 알아두실 점 참고)
s2b_fetch.py               S2B(학교장터) 조회 기술검증 스크립트 — robots.txt 문제로 자동 실행에는 연결 안 함(아래 참고)
competitor_g2b_export.py   경쟁사(티처빌/아이스크림/비바샘/한교원) 나라장터 낙찰 매트릭스 — history/competitor_wins.jsonl에 누적
competitor_content_scrape.py   경쟁사 3사 홈페이지 진행중 이벤트 목록 스크레이핑(Playwright, robots.txt 확인됨)
pipeline_status_webhook.gs.txt   구글 Apps Script(위 2번 참고) — 파이프라인 시트에 붙여넣는 코드
dashboard_template.html   통합 대시보드의 HTML 틀(데이터 자리에 __XXX_JSON__ 플레이스홀더)
.github/workflows/deploy.yml   기존 워크플로에 위 단계들을 추가(수정됨)
```

```bash
git add g2b_full_export.py neis_full_export.py own_pipeline_export.py beta_features.py combine_dashboard.py \
        history_tracker.py ics_feed.py pdf_report.py kosis_edu_finance.py s2b_fetch.py \
        competitor_g2b_export.py competitor_content_scrape.py pipeline_status_webhook.gs.txt \
        dashboard_template.html .github/workflows/deploy.yml fetch_g2b_listings.py g2b_config.example.json
git add history/competitor_wins.jsonl
git commit -m "통합 대시보드 확장: PDF 리포트, 참가자격 표시, 경쟁사 재계약 패턴, 카카오맵, KOSIS 교육재정, 경쟁사 연수 탭"
git push
```

(`fetch_g2b_listings.py`/`g2b_config.example.json`은 발주계획현황서비스 활성화 수정분이 이미 로컬에 있던 걸 같이 커밋하시면 됩니다.)

## 배포 후 접속 주소

- 기존 나라장터 단독 대시보드: `https://choiys2.github.io/g2b-education-dashboard/` (변화 없음)
- **새 통합 대시보드**: `https://choiys2.github.io/g2b-education-dashboard/full/`

## 알아두실 점

- **학교단위 발주(물품구매) 탭은 이번 자동화에 포함되지 않았습니다.** 나라장터 물품(Thng) API를
  17개 지역 x 7개 키워드로 훑는 데 시간이 걸려서(약 5~8분) 이번엔 뺐습니다. 그 탭은 지금 템플릿에
  박아둔 스냅샷(22건, 이번 세션 기준)이 계속 유지됩니다. 필요하시면 다음에 이 부분도 자동화 스텝으로
  추가해드릴 수 있습니다.
- 시크릿 하나라도 없거나 API 호출이 실패해도(`continue-on-error: true`) **기존 단독 대시보드는
  그대로 배포됩니다** — 새 기능이 실패해서 지금 잘 돌아가던 게 멈추는 일은 없게 만들어뒀습니다.
- `history/daily_stats.jsonl`은 매일 한 줄씩 실제로 git에 커밋되어 쌓입니다. 며칠~몇 주 지나면
  이 파일을 열어보시고, 다년치가 쌓였을 때 예측 모델링에 쓸 만한지 같이 판단해보면 됩니다.
- **"베타 기능" 탭은 네 가지 모두 표본이 얇거나 데이터가 아직 적습니다.** ① 경쟁사 수주 추세는
  최근 90일 vs 이전 90일 건수만 비교하는 단순 규칙이고, 표본 3건 미만인 업체는 "표본부족"으로만
  표시합니다. ② 자사 파이프라인은 지금까지 실패/탈락 이력이 전혀 없어서(전량 성사 또는 진행중)
  통계적인 "낙찰확률"은 아예 만들지 않았고, 대신 진행단계·모집현황·마감임박도로만 계산하는
  "모멘텀 스코어"로 대체했습니다. ③ 낙찰가 추정은 과거 낙찰율(%) 분포를 예산에 곱한 참고치일
  뿐 사업 성격·경쟁 강도는 반영하지 않습니다. ④ 지표 추세예측은 `history/daily_stats.jsonl`이
  최소 14일치 쌓이기 전까지는 "축적중"으로만 표시되고 계산되지 않습니다 — 전부 머신러닝이 아니고,
  수주 여부·미래를 확정적으로 맞히는 예측 모델이 아닙니다.
- **S2B(학교장터) 자동 수집은 만들지 않았습니다(중요).** 로그인 없이 열람 가능한 공개 검색
  페이지가 있고 실제로 데이터를 받아올 수 있다는 것까지 기술적으로 검증했습니다(`s2b_fetch.py`,
  "학교단위 발주" 탭 하단의 경기·서울 스냅샷 3건이 그 결과물). 다만 `s2b.kr/robots.txt`가
  `Disallow: /`로 모든 자동화 접근을 명시적으로 금지하고 있어서, 운영자 의사를 존중해
  **자동/정기 실행 파이프라인에는 연결하지 않았습니다**(`deploy.yml`에 없음, 로컬 1회성 실행만
  가능). 이 시장을 계속 보고 싶으시면 The-K 측에 공식 데이터 제공을 요청하거나, 각 시도교육청이
  자체 공개하는 S2B 낙찰 내역 게시판을 스크레이핑하는 방법을 검토해야 합니다.
- **참가자격 배지("⚠ 자격확인")는 자동 판정이 아닙니다.** 나라장터 API의 지역제한·실적제한·
  지정경쟁·공동계약의무지역 플래그가 하나라도 켜져 있으면 표시만 할 뿐, 비바샘이 그 조건을
  충족하는지는 판단하지 않습니다 — 반드시 공고문을 직접 확인하세요. (업종제한 플래그는 실측
  결과 93%가 "예"라 변별력이 없어 배지 계산에서 제외했습니다.)
- **경쟁사 재계약(락인) 패턴은 표본이 매우 적습니다.** 지금까지 쌓인 공개 낙찰 데이터에서
  같은 업체·같은 기관 조합이 2회 이상 나온 경우만 잡아내는데, 현재는 2건뿐입니다. 데이터가
  쌓일수록 이 표가 의미를 갖게 됩니다.
- **카카오맵의 JavaScript 키는 코드에 기본값으로 박아뒀습니다** — 이 키는 구글맵 API 키처럼
  브라우저에 그대로 노출되도록 설계된 키라(보안은 카카오 디벨로퍼스의 "플랫폼 Web 등록" 도메인
  화이트리스트로 처리) 안전합니다. 지도에 표시되는 지역은 학교 개별 위치가 아니라 시도 단위
  근사 좌표이며, 원 크기·색은 "지역 통합 기회점수"를 그대로 시각화한 것입니다.
- **"경쟁사 연수 분석" 탭의 낙찰 매트릭스는 티처빌·아이스크림·비바샘·한교원 4개사의 사업자
  등록 법인명(테크빌교육/아이스크림미디어/비상교육/한국교원연수원)으로 낙찰업체명을 정확히
  매칭한 결과만 집계합니다. 나라장터 API가 브랜드명이 아닌 법인명으로만 낙찰업체를 기록하기
  때문입니다. `history/competitor_wins.jsonl`에 계속 누적되며, 매일은 최근 60일치만 새로
  조회해 이 누적 파일에 더합니다(과거분은 처음 도입 시 --days 730으로 한 번 채웠습니다).
- **콘텐츠(이벤트/프로모션) 카드는 각 사 홈페이지의 비로그인 공개 화면만 읽습니다.** 로그인
  후에만 보이는 개인화 정보나 가격은 포함하지 않으며, 3개 사이트 모두 robots.txt에서 자동화를
  허용하는 것을 확인한 뒤 연결했습니다(S2B와 달리 이 3곳은 `Allow: /`).
- **KOSIS 교육재정 표는 지역마다 기준연도가 다릅니다(2009~2024).** 서울·경기처럼 최근
  갱신되는 지역이 있는 반면, 충남은 2009년 자료가 KOSIS에서 구할 수 있는 최신치입니다(그
  이후로 이 경로의 갱신이 끊긴 것으로 보임). 그래서 이 표는 **기회점수 계산에는 반영하지
  않고** 별도 참고 표로만 뒀습니다 — 절대금액을 지역 간 비교할 때 기준연도를 꼭 같이 보세요.
  강원은 "지출액"(결산) 데이터 자체가 없어 "예산액"(당초 예산)으로 대체했습니다.
