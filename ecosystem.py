#!/usr/bin/env python3
"""
생태계 연결 층 - 대시보드 곳곳의 데이터를 공통 키(시도·시군·기관·기업·사업·플랫폼)로 묶고,
여러 데이터에 동시에 걸리는 지점을 '연결 인사이트'로 뽑는다 (combine_dashboard.py 에서 호출, '관계망' 탭).

  입력(이미 계산된 묶음): 지역 총판(복호화본) · 교과서 채택(복호화본) · 시도 AIEP · 지역 연계 사업 · 기업·대학 트렌드 · 통합 기회점수
        + history: training_bids.jsonl(교원연수 공고), keris_procurement.json(KERIS 참가·낙찰), competitor_wins.jsonl(경쟁사 낙찰)
  출력: nodes(종류·이름·근거 수) · edges(근거 출처) · insights(규칙 기반, 근거·이동 탭 포함)
  새 데이터가 들어오면(매일 06:00 배포) 연결과 인사이트가 자동으로 다시 계산된다. 규칙은 RULES 에 계속 추가한다.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
CORP_RE = re.compile(r"^(주식회사|\(주\)|㈜|사단법인|\(사\)|재단법인)\s*|\s*(주식회사|\(주\)|㈜)$")


ALIAS = [("테크빌", "티처빌"), ("아이스크림", "아이스크림"), ("비상교육", "비상교육"), ("천재교", "천재교육"), ("웅진씽크빅", "웅진씽크빅"),
         ("엘리스", "엘리스그룹"), ("네패스", "네패스"), ("폭스커넥트", "폭스커넥트"), ("한국교원연수원", "한교원")]
FAMILY = {"KERIS 입찰": "KERIS", "KERIS 낙찰": "KERIS"}


def corp(n):
    n = CORP_RE.sub("", (n or "").strip()).strip()
    return next((v for k, v in ALIAS if k in n), n)


def _jl(p):
    out = []
    f = HERE / p
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def build(branch=None, adoption=None, aiep=None, programs=None, industry=None, opp=None, geo=None):
    nodes, edges = {}, defaultdict(lambda: {"n": 0, "src": set()})

    def node(kind, name, **kw):
        k = f"{kind}:{name}"
        x = nodes.setdefault(k, {"id": k, "kind": kind, "name": name, "facts": [], "w": 0})
        x.update({a: b for a, b in kw.items() if b is not None})
        return k

    def link(a, b, src, fact=None):
        if a == b:
            return
        e = edges[tuple(sorted((a, b)))]
        e["n"] += 1
        e["src"].add(src)
        for k in (a, b):
            nodes[k]["w"] += 1
            if fact and len(nodes[k]["facts"]) < 30:
                nodes[k]["facts"].append({"src": src, "t": fact})

    for sd in SIDO:
        node("시도", sd)
    gname = {f["c"]: (f["sd"], f["n"]) for f in ((geo or {}).get("features") or [])}

    def sgg(code):
        sd, n = gname.get(code, (None, None))
        return node("시군", f"{sd} {n}", sido=sd, code=code) if n else None

    # 1) 교원연수 공고: 발주기관 - 시도
    for b in _jl("history/training_bids.jsonl")[-800:]:
        if b.get("r") in SIDO and b.get("o"):
            o = node("기관", re.sub(r"\s+", " ", b["o"]).split(" ")[-1])
            link(o, f"시도:{b['r']}", "연수 공고", f"{b.get('d', '')} {b.get('t', '')[:50]}")
    # 2) 경쟁사 낙찰: 기업 - 기관 - 시도
    for w in _jl("history/competitor_wins.jsonl"):
        c = node("기업", corp(w.get("competitor")) or "?")
        if w.get("region") in SIDO:
            link(c, f"시도:{w['region']}", "경쟁사 낙찰", f"{w.get('date', '')} {w.get('org', '')} · {(w.get('course') or '').strip()[:40]}")
    # 3) KERIS 참가·낙찰: 기업 - KERIS(기관)
    K = {}
    try:
        K = json.loads((HERE / "history/keris_procurement.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    keris = node("기관", "한국교육학술정보원(KERIS)")
    kbids = K.get("bids") or {}
    for k, ps in (K.get("participants") or {}).items():
        t = (kbids.get(k) or {}).get("t") or (K.get("awards", {}).get(k) or {}).get("t") or ""
        for p in ps:
            if p.get("corp"):
                c = node("기업", corp(p["corp"]))
                link(c, keris, "KERIS 입찰", f"{'1순위' if p.get('rank') == 1 else '참가'} · {t[:46]}")
    # 4) 시도 AIEP: 플랫폼 - 시도, AIEP 조달 낙찰 기업
    for x in (aiep or {}).get("sido") or []:
        p = node("플랫폼", x["name"], group=x.get("group"), sido=x["sido"]) if x.get("name") not in ("확인 필요",) else None
        if p:
            link(p, f"시도:{x['sido']}", "시도 AIEP", f"{x['sido']} {x['name']} ({x.get('group')})")
        for t in x.get("train") or []:
            link(f"시도:{x['sido']}", node("사업", "AIEP 활용 연수"), "연수 공고", f"{t.get('d')} {t.get('t', '')[:46]}")
    for r in (aiep or {}).get("market") or []:
        if r.get("winner") and r.get("r") in SIDO:
            link(node("기업", corp(r["winner"])), f"시도:{r['r']}", "AIEP 조달", f"{r.get('d')} 낙찰 · {r.get('t', '')[:40]}")
    # 5) 지역 연계 사업: 사업 - 시군 - 시도
    for pg in (programs or {}).get("programs") or []:
        pn = node("사업", pg["name"], owner=pg.get("owner"))
        for r in pg.get("regions") or []:
            for c in r.get("codes") or []:
                s = sgg(c)
                if s:
                    link(pn, s, "지역 연계 사업", f"{r['sido']} {r['sgg']} {r.get('type', '')} · {r.get('pitch', '')}")
                    link(s, f"시도:{r['sido']}", "지역 연계 사업")
    # 6) 지역 총판(로그인): 총판 - 시군
    for r in (branch or {}).get("rows") or []:
        b = node("총판", r["name"], sido=r["sido"])
        link(b, f"시도:{r['sido']}", "지역 총판", f"담당 지역 {r.get('area', '')}")
        for c in r.get("sgg") or []:
            s = sgg(c)
            if s:
                link(b, s, "지역 총판")
    # 7) 기업·대학 트렌드: 기업 - 사업(RISE 등)
    if industry:
        rise = node("사업", "RISE(지역혁신중심 대학지원체계)", owner="교육부·광역지자체")
        for u in industry.get("universities") or []:
            link(node("대학", u["name"]), rise, "기업·대학 트렌드", f"{u['field']} → {u['link']}")
        for a in industry.get("keris_ai") or []:
            link(node("기업", corp(a["winner"])), node("사업", "AI 교원연수 위탁(KERIS)"), "KERIS 낙찰", f"{a.get('d')} {a.get('t', '')[:40]} · {round((a.get('amt') or 0) / 1e8, 1)}억")
        for c in ((industry.get("private") or {}).get("companies") or []):
            if c["name"] not in ("대학 RISE", "상품 연계"):
                link(node("기업", c["name"]), node("기관", "비상교육(협력 검토)"), "기업·대학 트렌드", c.get("coop"))

    # ---------------- 연결 인사이트(규칙) ----------------
    ins = []
    # 시군 단위 채택·전환 대상
    by = defaultdict(lambda: {"u": 0, "a": 0, "open": 0})
    for s in (adoption or {}).get("schools") or []:
        if s[3] and s[11]:
            x = by[s[3]]
            x["u"] += 1
            x["a"] += 1 if s[8] else 0
            x["open"] += 1 if (not s[8] and s[5]) else 0
    br_by = defaultdict(set)
    for r in (branch or {}).get("rows") or []:
        for c in r.get("sgg") or []:
            br_by[c].add(r["name"].split("(")[0].strip())
    for pg in (programs or {}).get("programs") or []:
        for r in pg.get("regions") or []:
            cs = r.get("codes") or []
            op = sum(by[c]["open"] for c in cs)
            u = sum(by[c]["u"] for c in cs)
            a = sum(by[c]["a"] for c in cs)
            ai = sum(((geo or {}).get("ai") or {}).get(c, 0) for c in cs)
            if op >= 10 or ai >= 5:
                bs = sorted({b for c in cs for b in br_by[c]})
                ins.append({"score": op * 2 + ai * 3 + 10, "kind": "시군 결합 기회", "tab": "pipeline", "anchor": "rpPanel",
                            "title": f"{r['sido']} {r['sgg']} — {pg['name']} × 전환 대상 {op}교 × AI 중점 {ai}교",
                            "body": f"{pg['name']}({r.get('type', '')}) 시군인데 비바샘 회원은 있고 비상 교과서는 안 쓰는 학교가 {op}곳(채택 {a}/{u}교). "
                                    f"{('관할 총판 ' + ', '.join(bs[:2]) + '와 ') if bs else ''}사업비 연계 연수 + 교과서 전환 제안을 묶을 수 있습니다.",
                            "keys": [f"시군:{gname[c][0]} {gname[c][1]}" for c in cs if c in gname][:1] + [f"시도:{r['sido']}", f"사업:{pg['name']}"]})
    # 시도: AIEP 활용 연수 공고 + 높은 채택률
    sd_ad = defaultdict(lambda: [0, 0])
    for s in (adoption or {}).get("schools") or []:
        if s[11] and s[2]:
            sd_ad[s[2]][0] += 1
            sd_ad[s[2]][1] += 1 if s[8] else 0
    for x in (aiep or {}).get("sido") or []:
        u, a = sd_ad.get(x["sido"], [0, 0])
        rate = a / u if u else 0
        if x.get("train") and rate >= 0.6:
            ins.append({"score": 40 + rate * 20 + len(x["train"]) * 5, "kind": "AIEP 연계 연수", "tab": "aiep", "anchor": "aiepPanel",
                        "title": f"{x['sido']} {x['name']} — AIEP 활용 연수 공고 {len(x['train'])}건 × 비상 채택 {rate * 100:.0f}%",
                        "body": f"교육청이 이미 AIEP 활용 연수를 발주하고 있고 학교의 비상 교과서 채택률이 높습니다. 비바샘 콘텐츠를 쓰는 AIEP 수업 설계 연수로 다음 공고를 준비하세요.",
                        "keys": [f"시도:{x['sido']}", f"플랫폼:{x['name']}"]})
    # 기업: 여러 데이터에 동시에 등장(경쟁·협력 대상)
    for k, nd in nodes.items():
        if nd["kind"] != "기업":
            continue
        srcs = set()
        for (a, b), e in edges.items():
            if k in (a, b):
                srcs |= {FAMILY.get(x, x) for x in e["src"]}
        if len(srcs) >= 2 and nd["name"] not in ("?",):
            ins.append({"score": 20 + len(srcs) * 10 + min(nd["w"], 20), "kind": "기업 다중 등장", "tab": "biz2027", "anchor": "bizPanel",
                        "title": f"{nd['name']} — {len(srcs)}개 데이터에 등장({', '.join(sorted(srcs))})",
                        "body": "여러 사업 영역에 걸쳐 움직이는 기업입니다. 경쟁(같은 공고 응찰)인지 협력(컨소시엄·하도급) 후보인지 함께 판단하세요.",
                        "keys": [k]})
    # 시도: 기회점수 상위 주제 + 지역 연계 사업
    prog_sd = Counter(r["sido"] for pg in (programs or {}).get("programs") or [] for r in pg.get("regions") or [])
    for c in ((opp or {}).get("cells") or [])[:40]:
        if prog_sd.get(c.get("sido")):
            ins.append({"score": 15 + (c.get("score") or 0) / 4, "kind": "기회점수 × 지역 사업", "tab": "pipeline", "anchor": "oppPanel",
                        "title": f"{c['sido']} '{c.get('topic')}' 기회점수 {c.get('score')} × 지역 연계 사업 시군 {prog_sd[c['sido']]}곳",
                        "body": f"교육청 공고 수요가 큰 주제를 지역 사업 시군의 사업비 연수로도 제안할 수 있습니다. {c.get('action', '')}",
                        "keys": [f"시도:{c['sido']}"]})
    seen, out = set(), []
    for x in sorted(ins, key=lambda x: -x["score"]):
        if x["title"] in seen:
            continue
        seen.add(x["title"])
        out.append(x)
    E = [{"a": a, "b": b, "n": e["n"], "src": sorted(e["src"])} for (a, b), e in edges.items()]
    N = [n for n in nodes.values() if n["w"]]
    kinds = Counter(n["kind"] for n in N)
    return {"nodes": N, "edges": E, "insights": out[:30], "kinds": dict(kinds),
            "sources": sorted({s for e in E for s in e["src"]})}
