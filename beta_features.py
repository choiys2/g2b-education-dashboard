#!/usr/bin/env python3
"""
"최고 난이도" 확장 제안 중 표본이 얇아 신뢰도를 낮게 잡아야 하는 두 기능.
전부 규칙 기반(머신러닝 아님)이며, 대시보드에도 "베타" 표시와 함께 각 스코어의
근거·한계를 그대로 노출한다 — 과장 방지가 우선이라 정확도 주장은 하지 않는다.

1) competitor_trend(): G2B 낙찰정보(공개 데이터)를 최근/이전 구간으로 나눠 경쟁사별
   수주 건수 증감 추세만 본다. 표본이 몇 건 안 되는 경쟁사는 "표본부족"으로 명시한다.

2) pipeline_momentum(): 자사 파이프라인(own_pipeline_export.py)에는 "실패/탈락" 상태가
   아예 없다 — 지금까지 쌓인 61건이 전부 성사(완료) 또는 진행중 건이라 승/패 이력이
   존재하지 않는다. 그래서 "낙찰확률"은 통계적으로 만들 수 없다고 판단해 만들지 않았고,
   대신 진행 단계·모집 현황·마감 임박도로만 계산하는 "모멘텀(우선순위) 스코어"로
   대체했다 — 어떤 진행중 건에 먼저 집중할지 판단을 돕는 용도이지 수주 여부를
   맞추는 예측 모델이 아니다.
"""
import re
from datetime import date, datetime, timedelta

BETA_NOTE_TREND = (
    "베타 · 공개 나라장터 낙찰 데이터 기준 최근 90일 vs 이전 90일 수주 건수 비교. "
    "표본이 3건 미만인 업체는 추세를 판단하지 않고 '표본부족'으로 표시함."
)
BETA_NOTE_MOMENTUM = (
    "베타 · 자사 파이프라인에는 실패/탈락 이력이 없어(현재까지 전량 성사 또는 진행중) "
    "통계적 '낙찰확률'은 산출하지 않음. 대신 진행단계·모집현황·마감임박도만으로 "
    "계산한 우선순위 참고 스코어이며, 수주 여부를 예측하는 모델이 아님."
)


def _parse_iso(s):
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def competitor_trend(win_items, today=None, recent_days=90, prior_days=90, top_n=15):
    today = today or date.today()
    recent_start = today - timedelta(days=recent_days)
    prior_start = recent_start - timedelta(days=prior_days)

    totals = {}
    recent_cnt, prior_cnt = {}, {}
    for it in win_items:
        co = it.get("낙찰업체") or "-"
        if co == "-":
            continue
        d = _parse_iso(it.get("개찰일", ""))
        totals[co] = totals.get(co, 0) + (it.get("낙찰금액", 0) or 0)
        if d is None:
            continue
        if recent_start <= d <= today:
            recent_cnt[co] = recent_cnt.get(co, 0) + 1
        elif prior_start <= d < recent_start:
            prior_cnt[co] = prior_cnt.get(co, 0) + 1

    companies = sorted(totals.keys(), key=lambda c: totals[c], reverse=True)[:top_n]
    out = []
    for co in companies:
        r, p = recent_cnt.get(co, 0), prior_cnt.get(co, 0)
        sample = r + p
        if sample < 3:
            trend = "표본부족"
        elif r > p * 1.2 and r - p >= 1:
            trend = "상승"
        elif r < p * 0.8 and p - r >= 1:
            trend = "하락"
        else:
            trend = "보합"
        out.append({
            "낙찰업체": co, "최근90일건수": r, "이전90일건수": p,
            "추세": trend, "표본충분": sample >= 3,
        })
    return out


_KOREAN_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def _parse_korean_date(s):
    if not s:
        return None
    m = _KOREAN_DATE_RE.search(s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _to_int(s):
    try:
        return int(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _stage_score(contract_progress):
    text = contract_progress or ""
    if "완료" in text:
        return 40
    if re.search(r"\d+\.\d+", text):  # 특정 일자가 메모된 경우 (구체적 진행 근거 있음)
        return 25
    if text.strip():
        return 15
    return 5


def _fill_score(applied_count, target_count):
    a, t = _to_int(applied_count), _to_int(target_count)
    if not a or not t or t <= 0:
        return 10  # 판단 근거 없음 -> 중립값
    ratio = min(a / t, 1.5)
    return round(min(ratio, 1.0) * 30)


def _timeline_score(recruit_end, today):
    d = _parse_korean_date(recruit_end)
    if d is None:
        return 15  # 판단 근거 없음 -> 중립값
    days_left = (d - today).days
    if days_left < 0:
        return 10  # 마감 지났는데 아직 진행중 상태 -> 정체 신호
    if days_left <= 14:
        return 30  # 마감 임박, 관심 필요
    if days_left <= 30:
        return 22
    return 15


def pipeline_momentum(records, today=None):
    today = today or date.today()
    out = []
    for r in records:
        if (r.get("status") or "") == "완료":
            continue  # 이미 성사된 건은 모멘텀 스코어 대상이 아님
        stage = _stage_score(r.get("contractProgress"))
        fill = _fill_score(r.get("appliedCount"), r.get("targetCount"))
        timeline = _timeline_score(r.get("recruitEnd"), today)
        score = max(5, min(95, stage + fill + timeline))
        band = "임박" if score >= 80 else ("진행" if score >= 50 else "초기/정체")
        out.append({
            "gisu": r.get("gisu"), "org": r.get("org"), "courseName": r.get("courseName"),
            "region": r.get("region"), "status": r.get("status"), "salesRep": r.get("salesRep"),
            "targetAmount": r.get("targetAmount"), "recruitEnd": r.get("recruitEnd"),
            "모멘텀점수": score, "단계": band,
        })
    out.sort(key=lambda x: x["모멘텀점수"], reverse=True)
    return out


def build_beta(win_items, pipeline_records, today=None):
    return {
        "competitor_trend": competitor_trend(win_items, today=today),
        "trend_note": BETA_NOTE_TREND,
        "pipeline_momentum": pipeline_momentum(pipeline_records, today=today),
        "momentum_note": BETA_NOTE_MOMENTUM,
    }
