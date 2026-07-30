# 통합 대시보드 자동화 — 설정 가이드

기존에 이미 매일 자동으로 도는 `나라장터 종합` 대시보드(choiys2.github.io/g2b-education-dashboard)에,
나이스 학교데이터·AI 선도학교·자사 영업 파이프라인까지 합친 **통합 대시보드**를 추가로 매일 자동
생성·배포하도록 확장했습니다. 1번(시크릿)과 4번(커밋·푸시)만 해주시면 다음 날 새벽부터 바로 돌아갑니다.
2번·3번은 선택 사항입니다.

## 1. GitHub 저장소에 시크릿(secrets) 2개 추가

`github.com/choiys2/g2b-education-dashboard` → **Settings → Secrets and variables → Actions** →
**New repository secret**

| 이름 | 값 | 비고 |
|---|---|---|
| `NEIS_KEY` | `35217cc2959b490990e25e95a1085b19` | 나이스 개방포털 마이페이지에서 발급받은 인증키(이미 갖고 계신 것) |
| `ODCLOUD_KEY` | `d8ac83ebf8376f59ad04d82aae37e8a69a2661b0d1b6a624d9bc8415a65ff464` | 공공데이터포털(data.go.kr) 일반 인증키. 지금 쓰시는 `G2B_SERVICE_KEY`와 같은 값입니다 — 나라장터·AI선도학교 둘 다 같은 계정 키를 씁니다 |

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
s2b_fetch.py               S2B(학교장터) 조회 기술검증 스크립트 — robots.txt 문제로 자동 실행에는 연결 안 함(아래 참고)
pipeline_status_webhook.gs.txt   구글 Apps Script(위 2번 참고) — 파이프라인 시트에 붙여넣는 코드
dashboard_template.html   통합 대시보드의 HTML 틀(데이터 자리에 __XXX_JSON__ 플레이스홀더)
.github/workflows/deploy.yml   기존 워크플로에 위 단계들을 추가(수정됨)
```

```bash
git add g2b_full_export.py neis_full_export.py own_pipeline_export.py beta_features.py combine_dashboard.py \
        history_tracker.py ics_feed.py s2b_fetch.py pipeline_status_webhook.gs.txt \
        dashboard_template.html .github/workflows/deploy.yml fetch_g2b_listings.py g2b_config.example.json
git commit -m "통합 대시보드 확장: 베타 낙찰가추정/추세예측, 파이프라인 상태연동, 캘린더 피드"
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
