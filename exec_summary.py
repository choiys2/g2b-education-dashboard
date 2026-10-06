#!/usr/bin/env python3
"""
'경영 종합' 탭 데이터 - 대시보드 전체 데이터를 한 번 더 모아 2027 경영·판매 방향의 근거 수치를 만든다.

- 수치(시장·경쟁·자사·학교 수요·연계 상태)는 매 배포 자동 갱신, 전략 문장은 템플릿에 고정(분기마다 갱신).
- 내부 목표는 이미 공유된 전략 목표만(2027 B2G 40% : B2C+B2S 60%, 샘몰 2026 H2, 3 Core). 매출 금액 목표는 넣지 않는다.
- 새 API 호출 없음. combine_dashboard.py 가 이미 만든 묶음을 받아 요약만 한다.
"""
import re
from collections import Counter

SELF_KEYS = ("비바샘", "비상")


def _num(v):
    try:
        return int(re.sub(r"[^\d]", "", str(v)) or 0)
    except ValueError:
        return 0


def build(full_live=None, topics=None, contracts=None, banner=None, pipe=None, comms=None,
          b2s_market=None, rfp=None, early=None, leading_n=0, new_courses=None, tour=None, weather=None,
          ai_brief=None, schoolinfo_n=0):
    full_live, topics, contracts, banner = full_live or {}, topics or {}, contracts or {}, banner or {}
    pipe, comms, b2s_market, rfp, early = pipe or {}, comms or {}, b2s_market or {}, rfp or {}, early or {}
    an = full_live.get("analytics", {})
    out = {}

    # 시장(나라장터)
    tps = topics.get("topics", [])
    out["market"] = {
        "open_bids": len(an.get("입찰공고", [])), "wins": len(an.get("낙찰정보", [])), "prespec": len(an.get("사전규격", [])),
        "bids_12m": topics.get("total", 0),
        "generic_n": (topics.get("generic_content") or {}).get("n", 0),
        "generic_amt": (topics.get("generic_content") or {}).get("amount", 0),
        "top_topics": [{"name": t["name"], "score": t.get("score"), "n": t.get("n"), "growth": t.get("growth"),
                        "own": (t.get("coverage") or {}).get("own"), "comp": (t.get("coverage") or {}).get("comp_avg")}
                       for t in tps[:5]],
        "early": len(early.get("items", [])),
    }

    # 경쟁(계약정보: 수의계약 포함)
    comps = contracts.get("competitors", [])
    tot_n = sum(c["n"] for c in comps) or 0
    sui = sum((c.get("methods") or {}).get("수의", 0) for c in comps)
    own = next((c for c in comps if any(k in c["name"] for k in SELF_KEYS)), None)
    rivals = [c for c in comps if c is not own]
    out["contracts"] = {
        "total_n": tot_n, "total_amt": sum(c["amount"] for c in comps), "sui_share": round(sui / tot_n * 100) if tot_n else None,
        "own": {"n": own["n"], "amount": own["amount"], "share": own["share"], "avg": round(own["amount"] / own["n"]) if own and own["n"] else 0} if own else None,
        "rivals": [{"name": c["name"], "n": c["n"], "amount": c["amount"], "share": c["share"],
                    "avg": round(c["amount"] / c["n"]) if c["n"] else 0, "regions": c.get("top_regions", [])} for c in rivals[:4]],
    }

    # 배너(구글시트 26타사DT)
    if banner.get("available"):
        tot = sum(banner.get("totals", {}).values()) or 1
        selfn = banner.get("self")
        lead = max(((k, v) for k, v in banner["totals"].items() if k not in ("기타", selfn)), key=lambda x: x[1], default=("-", 0))
        gaps = [t for t, v in (banner.get("theme") or {}).items() if not v.get(selfn) and sum(v.values()) >= 3]
        out["banner"] = {"rows": banner.get("rows"), "own_share": round(banner["totals"].get(selfn, 0) / tot * 100),
                         "lead": lead[0], "lead_share": round(lead[1] / tot * 100), "gap_themes": gaps[:6]}
    else:
        out["banner"] = None

    # 자사(구글시트 26운영DT + 26영업소통 DT)
    recs = pipe.get("records", [])
    st = Counter((r.get("status") or "미정").strip() for r in recs)
    out["pipeline"] = {"n": len(recs), "target_sum": sum(_num(r.get("targetAmount")) for r in recs),
                       "status": dict(st.most_common(6)),
                       "regions": dict(Counter(r.get("region") or "미정" for r in recs).most_common(5))}
    if comms.get("available"):
        sig = Counter(v.get("signal") for v in (comms.get("per") or {}).values())
        out["comms"] = {"rows": comms.get("rows"), "linked": comms.get("linked"), "signals": dict(sig),
                        "won_rows": comms.get("won_rows", 0), "no_deal_orgs": len(comms.get("no_deal_orgs") or [])}
    else:
        out["comms"] = None

    # 학교 수요(학교알리미)
    if b2s_market.get("available"):
        sido = b2s_market.get("sido", [])
        white = [r["s"] for r in sorted(sido, key=lambda r: -r["teachers"]) if r.get("own_c", 0) == 0][:4]
        out["b2s"] = {"schools": b2s_market.get("n_schools"), "teachers": b2s_market.get("n_teachers"),
                      "large": sum((r.get("tier") or {}).get("대", 0) for r in sido), "white_regions": white}
    else:
        out["b2s"] = None

    fits = Counter((r.get("fit") or {}).get("verdict") for r in rfp.get("items", []))
    out["rfp"] = {"n": rfp.get("total", 0), "fit": dict(fits)}
    out["leading_n"] = leading_n
    out["new_courses_7d"] = len([r for r in (new_courses or []) if r.get("first_seen")])

    # 연계 다이어그램 노드별 상태(건수). 0 이면 '대기'로 표시
    out["sources"] = {
        "g2b": len(an.get("입찰공고", [])) + len(an.get("낙찰정보", [])),
        "contracts": tot_n,
        "neis": schoolinfo_n or (b2s_market.get("n_schools") or 0),
        "schoolinfo": b2s_market.get("n_schools") or 0,
        "catalog": len(new_courses or []),
        "sheet_ops": len(recs),
        "sheet_comms": (comms or {}).get("rows") or 0,
        "sheet_banner": (banner or {}).get("rows") or 0,
        "news": 1,
        "tour": sum(len(v) for v in ((tour or {}).get("regions") or {}).values()),
        "weather": len((weather or {}).get("cities") or []),
        "gemini": rfp.get("total", 0) + (1 if (ai_brief or {}).get("summary") else 0),
    }
    return out
