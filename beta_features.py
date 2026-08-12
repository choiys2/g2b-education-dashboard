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
import json, os, re
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


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


BETA_NOTE_BID_RANGE = (
    "베타 · 공개된 과거 낙찰율(%) 분포(p25~p75)를 현재 진행중 공고의 예산에 곱한 "
    "참고용 낙찰가 추정치입니다. 사업 성격·참여업체 수·특약조건은 전혀 반영하지 않은 "
    "단순 통계적 추정이며, 전체 표본이 5건 미만이면 추정하지 않습니다."
)


def bid_amount_estimates(open_bids, win_items, min_sample=5, top_n=20):
    """과거 낙찰율(%) 분포(p25~중앙값~p75)를 현재 진행중 입찰공고의 예산에 곱해
    참고용 낙찰가 범위를 추정한다. analytics.py의 경쟁사 랭킹과 달리 여기서는
    개별 공고 단위로, "이 공고는 대략 얼마에 낙찰될 가능성이 높은가"를 본다."""
    rates = []
    for it in win_items:
        try:
            r = float(str(it.get("낙찰율(%)", "")).strip())
        except (TypeError, ValueError):
            continue
        if 0 < r <= 100:
            rates.append(r)
    rates.sort()

    band = {"표본수": len(rates)}
    if len(rates) < min_sample:
        band["표본충분"] = False
        return {"estimates": [], "band": band, "note": BETA_NOTE_BID_RANGE}
    band.update({
        "표본충분": True,
        "p25": round(_percentile(rates, 0.25), 2),
        "중앙값": round(_percentile(rates, 0.5), 2),
        "p75": round(_percentile(rates, 0.75), 2),
        "분포": [round(r, 2) for r in rates],  # 입찰가 시뮬레이터가 백분위 위치를 계산하는 데 씀
    })

    out = []
    for b in open_bids:
        budget = b.get("예산") or 0
        if budget <= 0:
            continue
        out.append({
            "공고명": b.get("공고명"), "기관": b.get("발주기관"), "지역": b.get("지역"),
            "예산": budget, "마감일": b.get("마감일"), "url": b.get("url"),
            "예상낙찰가_하": round(budget * band["p25"] / 100),
            "예상낙찰가_중앙": round(budget * band["중앙값"] / 100),
            "예상낙찰가_상": round(budget * band["p75"] / 100),
        })
    out.sort(key=lambda x: x.get("마감일") or "9999")
    return {"estimates": out[:top_n], "band": band, "note": BETA_NOTE_BID_RANGE}


def _linear_trend(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / den
    intercept = mean_y - slope * mean_x
    return slope, intercept


BETA_NOTE_TREND_FORECAST = (
    "베타 · history/daily_stats.jsonl 일별 누적치에 대한 단순 선형 추세선(최소자승법)입니다. "
    "계절성, 정책 변화, 예산 집행 시기 같은 외부 요인은 전혀 반영하지 않은 산술적 추정치이며, "
    "최소 {min_days}일치 데이터가 쌓이기 전까지는 추세를 계산하지 않습니다."
)

TREND_METRICS = ["ai_rows_count", "ai_rows_amount_sum", "own_pipeline_total", "own_pipeline_target"]


def trend_forecast(history_path="history/daily_stats.jsonl", min_days=14, forecast_days=30):
    """일별 히스토리가 min_days 미만이면 예측하지 않고 '축적중' 상태만 알린다.
    파이프라인은 매일 도니 데이터는 계속 쌓이고, 임계치를 넘는 순간 자동으로
    활성화된다 - 코드 변경 없이 시간이 지나면 스스로 켜지는 구조."""
    rows = []
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    rows.sort(key=lambda r: r.get("date", ""))
    days_collected = len(rows)

    if days_collected < min_days:
        return {
            "status": "축적중", "days_collected": days_collected, "min_days": min_days,
            "note": (f"추세 예측에는 최소 {min_days}일치 일별 데이터가 필요합니다. "
                     f"현재 {days_collected}일치 누적됨 - 계속 쌓이는 대로 자동 활성화됩니다."),
        }

    xs = list(range(days_collected))
    series = {}
    for m in TREND_METRICS:
        ys = [r.get(m, 0) or 0 for r in rows]
        trend = _linear_trend(xs, ys)
        if trend is None:
            continue
        slope, intercept = trend
        forecast_x = days_collected - 1 + forecast_days
        projected = max(0, round(slope * forecast_x + intercept))
        series[m] = {"현재": ys[-1], f"{forecast_days}일후_예상": projected, "일평균증가": round(slope, 2)}

    return {
        "status": "활성", "days_collected": days_collected, "min_days": min_days,
        "forecast_days": forecast_days, "series": series,
        "note": BETA_NOTE_TREND_FORECAST.format(min_days=min_days),
    }


BETA_NOTE_LOCKIN = (
    "베타 · 공개 나라장터 낙찰 데이터에서 같은 경쟁사가 같은 발주기관과 2회 이상 계약을 "
    "맺은 쌍만 모았습니다. 수의/경쟁 등 계약 방식이나 실제 재계약 사유는 반영하지 않은 "
    "단순 빈도 집계이며, 조회 기간이 짧아 우연히 겹쳤을 가능성도 있습니다."
)


def competitor_lockin_patterns(win_items, min_repeat=2, top_n=20):
    """같은 (낙찰업체, 발주기관) 쌍이 반복되면 '이 기관은 이미 특정 업체와 관계가
    굳어졌다(락인)'는 신호로 본다. 반대로 자사가 아직 안 들어간 기관이면서 이 목록에
    없는 곳은 상대적으로 열려 있다는 뜻이라 영업 우선순위 판단에 참고할 수 있다."""
    pairs = {}
    for it in win_items:
        co = (it.get("낙찰업체") or "").strip()
        org = (it.get("발주기관") or "").strip()
        if not co or not org or co == "-" or org == "-":
            continue
        key = (co, org)
        p = pairs.setdefault(key, {
            "낙찰업체": co, "발주기관": org, "건수": 0, "총낙찰금액": 0, "최근개찰일": "",
        })
        p["건수"] += 1
        p["총낙찰금액"] += it.get("낙찰금액", 0) or 0
        d = it.get("개찰일", "") or ""
        if d > p["최근개찰일"]:
            p["최근개찰일"] = d

    result = [p for p in pairs.values() if p["건수"] >= min_repeat]
    result.sort(key=lambda p: (-p["건수"], -p["총낙찰금액"]))
    return result[:top_n]


def build_beta(win_items, pipeline_records, open_bids=None, history_path="history/daily_stats.jsonl", today=None):
    return {
        "competitor_trend": competitor_trend(win_items, today=today),
        "trend_note": BETA_NOTE_TREND,
        "pipeline_momentum": pipeline_momentum(pipeline_records, today=today),
        "momentum_note": BETA_NOTE_MOMENTUM,
        "bid_range": bid_amount_estimates(open_bids or [], win_items),
        "trend_forecast": trend_forecast(history_path=history_path),
        "lockin_patterns": competitor_lockin_patterns(win_items),
        "lockin_note": BETA_NOTE_LOCKIN,
    }
