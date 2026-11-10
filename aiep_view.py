#!/usr/bin/env python3
"""
'시도 AIEP' 탭 데이터 묶음 (combine_dashboard.py 에서 호출)

  공개: static_data/aiep_platforms.json(17개 시도 플랫폼), history/aiep_market.json(나라장터 AIEP 공고·낙찰·참가업체),
        history/keris_procurement.json(KERIS 입찰 참가업체), history/training_bids.jsonl(AIEP 활용 연수 공고),
        static_data/ai_schools_2026.json(AI 중점·선도학교), static_data/branch_summary.json(지역 총판 수)
  비공개: static_data/aiep_private.enc.json(교육청 AIEP 담당·제휴 검토 메모) - STRATEGY_KEY 로 복호화(로그인 뒤 화면)
"""
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DEV = "폭스커넥트"
NAMES_RE = r"AIEP|교수학습\s?플랫폼|교수·학습\s?플랫폼|AI\s?맞춤형|하이러닝|다채움|마주온|에듀아이|아이로|SEN스쿨|센스쿨|바당|아이온|아이든|아이모두|AI배움터|우리아이|AI드림"


def _j(p, default=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build(key=None):
    P = _j("static_data/aiep_platforms.json")
    if not P:
        return None
    sido = {p["sido"]: {**p, "ai": 0, "dig": 0, "branch": 0, "train": [], "bids": 0, "bid_amt": 0, "awards": 0} for p in P["platforms"]}
    for sc in (_j("static_data/ai_schools_2026.json", {}) or {}).get("schools", []):
        x = sido.get(sc.get("소속지역"))
        if x:
            x["ai"] += "AI 중점" in (sc.get("사업") or [])
            x["dig"] += "디지털 선도" in (sc.get("사업") or [])
    for b in (_j("static_data/branch_summary.json", {}) or {}).get("by_sido", []):
        if b["sido"] in sido:
            sido[b["sido"]]["branch"] = b.get("학판", 0) + b.get("교판", 0)
    rx = re.compile(NAMES_RE)
    p = HERE / "history/training_bids.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(line)
            except ValueError:
                continue
            no = (b.get("k") or "").rsplit("-", 1)[0]
            if no in seen or not rx.search(b.get("t") or "") or b.get("r") not in sido:
                continue
            seen.add(no)
            sido[b["r"]]["train"].append({"t": b.get("t"), "o": b.get("o"), "d": b.get("d"), "a": b.get("a"), "u": b.get("u")})
    # 나라장터 AIEP 조달(수집기 결과가 있으면)
    M = _j("history/aiep_market.json", {}) or {}
    bids, awards, parts = M.get("bids", {}), M.get("awards", {}), M.get("participants", {})
    rows = []
    for k, b in bids.items():
        a = awards.get(k, {})
        ps = parts.get(k, [])
        rows.append({"k": k, "t": b.get("t"), "org": b.get("org"), "r": b.get("r"), "d": b.get("d"), "cat": b.get("cat"), "kind": b.get("kind"),
                     "budget": b.get("budget"), "u": b.get("u"), "winner": a.get("winner", ""), "wv": a.get("v", ""), "amt": a.get("amt"),
                     "n": a.get("n") or len(ps), "dev": any(x.get("v") == DEV for x in ps) or a.get("v") == DEV})
    for k, a in awards.items():  # 공고 수집 창 밖의 낙찰
        if k not in bids:
            ps = parts.get(k, [])
            rows.append({"k": k, "t": a.get("t"), "org": a.get("org"), "r": a.get("r"), "d": a.get("d"), "cat": None, "kind": a.get("kind"),
                         "budget": None, "u": f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={k.split('-')[0]}&bidPbancOrd={k.split('-')[-1]}",
                         "winner": a.get("winner", ""), "wv": a.get("v", ""), "amt": a.get("amt"), "n": a.get("n") or len(ps),
                         "dev": any(x.get("v") == DEV for x in ps) or a.get("v") == DEV})
    for r in rows:
        if r.get("r") in sido:
            sido[r["r"]]["bids"] += 1
            sido[r["r"]]["bid_amt"] += r.get("amt") or r.get("budget") or 0
            sido[r["r"]]["awards"] += bool(r.get("winner"))
    rows.sort(key=lambda r: r.get("d") or "", reverse=True)
    vend = defaultdict(lambda: {"win": 0, "amt": 0, "part": 0})
    for k, ps in parts.items():
        for x in ps:
            nm = x.get("v") or re.sub(r"^(주식회사|\(주\))\s*|\s*(주식회사|\(주\))$", "", x.get("corp") or "")
            if nm:
                vend[nm]["part"] += 1
    for a in awards.values():
        nm = a.get("v") or re.sub(r"^(주식회사|\(주\))\s*|\s*(주식회사|\(주\))$", "", a.get("winner") or "")
        if nm:
            vend[nm]["win"] += 1
            vend[nm]["amt"] += a.get("amt") or 0
    vendors = sorted(({"name": k, **v} for k, v in vend.items()), key=lambda x: (-x["amt"], -x["win"]))[:15]
    # KERIS 입찰 참가 이력(개발사)
    K = _j("history/keris_procurement.json", {}) or {}
    keris = []
    for k, ps in (K.get("participants") or {}).items():
        hit = [x for x in ps if DEV in (x.get("corp") or "")]
        if hit:
            b = (K.get("bids") or {}).get(k, {})
            w = next((x for x in ps if x.get("rank") == 1), {})
            keris.append({"k": k, "t": b.get("t", ""), "d": b.get("d", ""), "budget": b.get("budget"), "n": len(ps),
                          "rank": hit[0].get("rank"), "amt": hit[0].get("amt"), "winner": w.get("corp", ""),
                          "url": b.get("url") or f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={k.split('-')[0]}&bidPbancOrd={k.split('-')[-1]}"})
    out = {"note": P.get("note"), "sido": list(sido.values()), "market": rows[:300], "vendors": vendors, "keris_dev": keris,
           "dev": DEV, "status": {**(M.get("status") or {}), "updated": M.get("updated"), "n_bids": len(bids), "n_awards": len(awards)},
           "dev_rows": [r for r in rows if r["dev"] or r["wv"] == DEV][:40]}
    key = key or os.environ.get("STRATEGY_KEY", "")
    ep = HERE / "static_data/aiep_private.enc.json"
    if key and ep.exists():
        try:
            import strategy_crypto
            out["private"] = strategy_crypto.decrypt(json.loads(ep.read_text(encoding="utf-8")), key)
        except Exception as e:  # 키 불일치 등 - 공개 정보만 표시
            print(f"AIEP 비공개 메모: 복호화 실패({type(e).__name__})")
    return out


if __name__ == "__main__":
    d = build()
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in (d or {}).items() if k != "private"}, ensure_ascii=False)[:600])
