#!/usr/bin/env python3
"""
발주 조기 경보: 정식 입찰공고가 뜨기 전 단계(사전규격 공개, 발주계획 등록)에서 우리가 할 수 있는
연수 사업을 골라낸다.

- 사전규격: 일일 파이프라인(full_live.json analytics.사전규격)이 이미 받는다. 의견등록 마감 전이면 '진행중'.
- 발주계획: 조달청 발주계획 서비스는 '오늘 등록·갱신된 건'만 주는 롤링 스냅샷이라, 매일 받은 것을
  history/order_plans.jsonl 에 누적해야 연간 계획이 쌓인다(git 추적).
- 매칭: training_topics 의 연수 판정(is_training_bid)과 주제 분류를 그대로 쓴다. 주제마다 자사 보유
  강좌 수를 붙여 '바로 제안 가능한지'를 보여준다.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import training_topics as tt

HERE = Path(__file__).parent
PLAN_PATH = HERE / "history" / "order_plans.jsonl"
KEEP_DAYS = 400


def _load_plans():
    out = {}
    if PLAN_PATH.exists():
        for line in PLAN_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    out[r["k"]] = r
                except (json.JSONDecodeError, KeyError):
                    pass
    return out


def accumulate_plans(full_live, today=None):
    """오늘 발주계획 스냅샷을 누적 파일에 합친다. 반환: 누적 전체(dict)."""
    today = today or date.today()
    plans = _load_plans()
    for it in (full_live or {}).get("발주계획_오늘스냅샷", []) or []:
        title, org = (it.get("공고명") or "").strip(), it.get("발주기관") or ""
        if not title:
            continue
        k = f"{org}|{title}|{it.get('발주예정월', '')}"
        prev = plans.get(k, {})
        plans[k] = {"k": k, "t": title, "o": org, "r": it.get("지역") or "", "a": tt._to_int(it.get("예산")),
                    "m": str(it.get("발주예정월") or ""), "how": it.get("계약방법") or "",
                    "d": prev.get("d") or it.get("등록일") or today.isoformat()}
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    kept = {k: v for k, v in plans.items() if (v.get("d") or "") >= cutoff}
    if (full_live or {}).get("발주계획_오늘스냅샷") is not None:
        PLAN_PATH.parent.mkdir(exist_ok=True)
        PLAN_PATH.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n"
                                     for v in sorted(kept.values(), key=lambda v: (v["d"], v["k"]))), encoding="utf-8")
    return kept


def _month_key(m):
    """발주예정월 표기(예: '10', '2026.10', '202610')를 YYYY-MM 로. 모르면 ''."""
    digits = "".join(ch for ch in str(m) if ch.isdigit())
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    if 1 <= len(digits) <= 2 and 1 <= int(digits) <= 12:
        return f"{date.today().year}-{int(digits):02d}"
    return ""


def build(full_live, coverage=None, today=None):
    today = today or date.today()
    coverage = coverage or {}
    names = {t[0]: t[1] for t in tt.TOPICS}
    items = []

    def add(stage, title, org, region, amount, due, posted, url, extra=""):
        title = (title or "").replace("[사전규격]", "").strip()
        if not tt.is_training_bid(title, org) or tt.classify_audience(title) == "학생":
            return
        tids = tt.classify_topics(title)
        own = max([coverage.get(t, {}).get("own", 0) for t in tids] or [0])
        items.append({"stage": stage, "t": title, "o": org, "r": region or "", "a": amount or 0,
                      "due": due or "", "posted": posted or "", "url": url or "",
                      "topics": [names[t] for t in tids], "own": own,
                      "ready": "자사 강좌 보유" if own else ("주제 미분류" if not tids else "신규 개발 필요"),
                      "extra": extra})

    for it in (full_live or {}).get("analytics", {}).get("사전규격", []) or []:
        due = it.get("마감일") or ""
        if due and due < today.isoformat():
            continue  # 의견등록 마감이 지난 사전규격은 곧 입찰공고로 넘어가므로 경보에서 뺀다
        add("사전규격", it.get("공고명"), it.get("발주기관"), it.get("지역"), tt._to_int(it.get("예산")),
            due, it.get("공고일"), it.get("url"))

    this_month = today.strftime("%Y-%m")
    for p in accumulate_plans(full_live, today).values():
        mk = _month_key(p.get("m"))
        if mk and mk < this_month:
            continue  # 발주 예정월이 지난 계획(이미 공고됐거나 취소)
        add("발주계획", p["t"], p["o"], p.get("r"), p.get("a"), mk, p.get("d"), "https://www.g2b.go.kr/",
            extra=p.get("how") or "")

    stage_rank = {"사전규격": 0, "발주계획": 1}
    items.sort(key=lambda x: (stage_rank[x["stage"]], x["due"] or "9999", -x["a"]))
    return {"generated": today.isoformat(), "items": items,
            "counts": {s: sum(1 for x in items if x["stage"] == s) for s in stage_rank},
            "ready": sum(1 for x in items if x["own"])}
