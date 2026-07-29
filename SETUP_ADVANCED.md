# 통합 대시보드 자동화 — 설정 가이드

기존에 이미 매일 자동으로 도는 `나라장터 종합` 대시보드(choiys2.github.io/g2b-education-dashboard)에,
나이스 학교데이터·AI 선도학교·자사 영업 파이프라인까지 합친 **통합 대시보드**를 추가로 매일 자동
생성·배포하도록 확장했습니다. 아래 두 가지만 해주시면 다음 날 새벽부터 바로 돌아갑니다.

## 1. GitHub 저장소에 시크릿(secrets) 2개 추가

`github.com/choiys2/g2b-education-dashboard` → **Settings → Secrets and variables → Actions** →
**New repository secret**

| 이름 | 값 | 비고 |
|---|---|---|
| `NEIS_KEY` | `35217cc2959b490990e25e95a1085b19` | 나이스 개방포털 마이페이지에서 발급받은 인증키(이미 갖고 계신 것) |
| `ODCLOUD_KEY` | `d8ac83ebf8376f59ad04d82aae37e8a69a2661b0d1b6a624d9bc8415a65ff464` | 공공데이터포털(data.go.kr) 일반 인증키. 지금 쓰시는 `G2B_SERVICE_KEY`와 같은 값입니다 — 나라장터·AI선도학교 둘 다 같은 계정 키를 씁니다 |

기존에 이미 등록돼 있는 `G2B_SERVICE_KEY`는 그대로 두시면 됩니다.

## 2. 이번에 새로 생긴 파일들을 커밋·푸시

아래 파일들을 만들어뒀는데, **제가 대신 `git push`는 하지 않았습니다**(계정 접근 권한 관련 조치라 확인 없이 하지 않는 게 맞다고 판단했습니다). 검토 후 직접 커밋해주세요.

```
g2b_full_export.py        나라장터 분석 데이터를 analytics.py로 재계산해 JSON으로 내보냄
neis_full_export.py       나이스 학교수 + AI 선도학교(odcloud) + 연락처/학급수 조회
own_pipeline_export.py    자사 영업 파이프라인 구글시트 조회 (안전 필드만, 담당자 자동 익명화)
beta_features.py          "베타" 탭 2종 계산 — 경쟁사 수주 추세, 파이프라인 모멘텀 스코어(아래 설명)
combine_dashboard.py      위 4개 + 기존 full_live.json을 합쳐 통합 대시보드 HTML 생성
history_tracker.py        매일 핵심 지표를 history/daily_stats.jsonl에 한 줄씩 누적
dashboard_template.html   통합 대시보드의 HTML 틀(데이터 자리에 __XXX_JSON__ 플레이스홀더)
.github/workflows/deploy.yml   기존 워크플로에 위 단계들을 추가(수정됨)
```

```bash
git add g2b_full_export.py neis_full_export.py own_pipeline_export.py beta_features.py combine_dashboard.py \
        history_tracker.py dashboard_template.html .github/workflows/deploy.yml fetch_g2b_listings.py
git commit -m "통합 대시보드 자동화 파이프라인 추가"
git push
```

(`fetch_g2b_listings.py`는 발주계획현황서비스 활성화 수정분이 이미 로컬에 있던 걸 같이 커밋하시면 됩니다.)

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
- **새로 추가된 "베타 기능" 탭은 두 가지 모두 표본이 얇습니다.** ① 경쟁사 수주 추세는 최근 90일 vs
  이전 90일 건수만 비교하는 단순 규칙이고, 표본 3건 미만인 업체는 "표본부족"으로만 표시합니다.
  ② 자사 파이프라인은 지금까지 실패/탈락 이력이 전혀 없어서(전량 성사 또는 진행중) 통계적인
  "낙찰확률"은 아예 만들지 않았고, 대신 진행단계·모집현황·마감임박도로만 계산하는 "모멘텀
  스코어"로 대체했습니다 — 머신러닝이 아니고, 수주 여부를 맞히는 예측 모델도 아닙니다.
- **S2B(학교장터) 자동 수집은 만들지 않았습니다.** 로그인 없이 열람 가능한 공개 검색 페이지를
  찾았지만 `s2b.kr/robots.txt`가 `Disallow: /`로 모든 자동화 접근을 명시적으로 금지하고 있어서,
  운영자 의사를 존중해 스크레이핑 파이프라인을 만들지 않기로 했습니다. 필요하시면 수작업 스냅샷을
  전달해주시거나, The-K 측에 공식 데이터 제공을 요청하는 방법을 고려해보세요.
