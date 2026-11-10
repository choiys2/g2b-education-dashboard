#!/usr/bin/env python3
"""
비상교육 지사(총판) 주소록 -> B2G(교육청 영업)와 B2S(학교 영업)를 잇는 '지역 총판 연계' 데이터

  1) 변환(로컬, 주소록이 바뀔 때만):  python branch_network.py convert <주소록.xls>
     - 공개 저장소에는 static_data/branch_summary.json(시도별 총판 수·교육지원청 연결률 집계)만 저장
     - 총판 상호·비상 담당자·사무실 전화·주소·담당 지역은 static_data/branch_network.enc.json 으로 암호화
       (STRATEGY_KEY 로 배포 때만 복호화 -> 로그인 뒤 화면). 휴대폰·계좌·대표자 이름은 암호문에도 넣지 않는다.
  2) 연결(배포 때 combine_dashboard.py):  build(decrypted) -> 총판별 관할 교육지원청·최근 연수 공고·
     AI 중점·선도학교·B2S 발송 기한 학교 수, 시도별 통합 기회점수 상위 주제
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
# 학교 명단이 비공개인 시도(강원·충남)의 교육지원청과 관할 시군 - 공개 기관 정보
STATIC_OFFICES = {
    "강원": {"춘천": ["춘천시"], "원주": ["원주시"], "강릉": ["강릉시"], "동해": ["동해시"], "태백": ["태백시"], "속초양양": ["속초시", "양양군"],
             "삼척": ["삼척시"], "홍천": ["홍천군"], "횡성": ["횡성군"], "영월": ["영월군"], "평창": ["평창군"], "정선": ["정선군"],
             "철원": ["철원군"], "화천": ["화천군"], "양구": ["양구군"], "인제": ["인제군"], "고성": ["고성군"]},
    "충남": {"천안": ["천안시"], "공주": ["공주시"], "보령": ["보령시"], "아산": ["아산시"], "서산": ["서산시"], "논산계룡": ["논산시", "계룡시"],
             "당진": ["당진시"], "금산": ["금산군"], "부여": ["부여군"], "서천": ["서천군"], "청양": ["청양군"], "홍성": ["홍성군"],
             "예산": ["예산군"], "태안": ["태안군"]},
    "경남": {"거창": ["거창군"], "함양": ["함양군"], "합천": ["합천군"]},
}
ALIAS = {"일산": "고양", "대천": "보령", "중원구": "성남", "수정구": "성남", "분당": "성남", "마산": "창원", "진해": "창원", "검단": "서구"}
NEIGHBOR = {"광주": {"전남"}, "전남": {"광주"}, "대전": {"충남", "세종"}, "세종": {"충남", "충북"}, "대구": {"경북"},
            "울산": {"경남"}, "부산": {"경남"}, "인천": {"경기"}, "경기": {"인천"}}  # 광역시 총판이 인접 도 시군을 함께 담당하는 경우
WHOLE = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주"}
SUFFIX = re.compile(r"(특별자치시|특별자치도|광역시|특별시|시|군|구)$")


def _toks(area):
    a = re.sub(r"[0-9\-~]+", " ", area or "")
    parts = re.split(r"[,{}<>()\[\]·/\s]+", a)
    out = []
    for p in parts:
        p = p.strip()
        for sd in ("충남", "충북", "전남", "전북", "경남", "경북", "경기", "강원"):
            if p.startswith(sd) and len(p) > len(sd) + 1:
                p = p[len(sd):]
        if len(p) >= 2 and p not in ("전체", "일부", "지역", "외", "검단제외"):
            out.append(p)
    return out


def _stem(t):
    s = SUFFIX.sub("", t)
    return s if len(s) >= 2 else t


def convert(xls):
    import xlrd
    s = xlrd.open_workbook(xls).sheet_by_index(0)
    rows, sec, reg = [], "", ""
    for r in range(s.nrows):
        v = [str(c.value).strip() for c in s.row(r)]
        if "지사명" in v[0]:
            sec = "교판" if "교판" in v[0] else "학판"
            reg = ""
            continue
        if not re.match(r"^[A-Z]\d{4,6}$", v[1]):
            continue
        if v[2]:
            reg = v[2]
        name, area, addr = v[3], v[5], v[12]
        sido = reg if reg in SIDO else ""
        if not sido:  # '광역' 권역: 상호·담당 지역·주소에서 광역시 이름을 찾는다
            blob = f"{name} {area} {addr}"
            sido = next((x for x in ("부산", "대구", "울산", "인천", "광주", "대전", "세종") if x in blob), "")
        rows.append({"type": sec, "code": v[1], "region": reg, "sido": sido, "name": name, "staff": v[4],
                     "area": re.sub(r"\s*0\d{1,2}-\d{3,4}-\d{4}", "", area).strip(), "tokens": _toks(area),
                     "tel": v[8], "fax": v[9], "addr": addr})
    offices = _offices()
    for r in rows:
        r["sido"] = _infer_sido(r, offices)
    return rows


def _offices():
    """(시도, 교육지원청) -> 시군구 집합. AI 중점·선도학교 명단 + 연수 입찰 발주기관 이름."""
    m = defaultdict(set)
    try:
        for sc in json.loads((HERE / "static_data/ai_schools_2026.json").read_text(encoding="utf-8"))["schools"]:
            if sc.get("교육지원청") and sc["교육지원청"] != "교육청 직속":
                m[(sc["소속지역"], sc["교육지원청"])].add(sc.get("시군구") or "")
    except (OSError, ValueError, KeyError):
        pass
    for sd, offs in STATIC_OFFICES.items():
        for o, sgg in offs.items():
            m[(sd, o + "교육지원청")].update(sgg)
    p = HERE / "history/training_bids.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(line)
            except ValueError:
                continue
            mm = re.search(r"([가-힣]+교육지원청)", b.get("o") or "")
            if mm and b.get("r") in SIDO:
                nm = re.sub(r"^.*?(특별자치도|특별자치시|광역시|특별시|도)(?=[가-힣]+교육지원청)", "", mm.group(1))
                m.setdefault((b["r"], nm), set())
    # 개편 전 구 이름도 함께(주소록은 옛 이름: 인천 서구·남구·중구) - 지도 보정표 GEO_ALIAS 재사용
    for (sd, off), sgg in m.items():
        for g in list(sgg):
            for s2, old in GEO_ALIAS.get((sd, g), []):
                if s2 == sd:
                    sgg.add(old)
    return m


def _stems(row):
    return {ALIAS.get(t, _stem(ALIAS.get(t, t))) for t in row["tokens"]}


def _infer_sido(row, offices):
    """권역 표기와 담당 지역이 다른 행(예: '경기' 권역의 인천·강원 담당)은 담당 지역 기준으로 시도를 다시 정한다."""
    stems = _stems(row)
    if row["tokens"] and row["tokens"][0] in WHOLE:  # '인천(부평,…)'처럼 시도명이 맨 앞이면 그 시도
        return row["tokens"][0]
    votes = Counter()
    for (sd, off), sgg in offices.items():
        on = off.replace("교육지원청", "")
        for st in stems:
            if st in on or any(g.startswith(st) for g in sgg if g):
                votes[sd] += 1
    if votes:
        best, n = votes.most_common(1)[0]
        if row["sido"] not in votes or votes[row["sido"]] < n:
            return best
    return row["sido"]


def _match(row, offices, pairs=False):
    stems = _stems({**row, "tokens": [t for t in row["tokens"] if t != row["sido"]]})
    # '인천(부평,계양,서구)'처럼 시도명 뒤 소괄호면 그 안의 구만, '광주{화순,장성}'처럼 중괄호·쉼표면 시도 전역 + 추가 지역
    restricted = bool(re.match(rf"^\s*{row['sido']}\s*\(", row.get("area") or ""))
    whole = row["sido"] in WHOLE and row["sido"] in row["tokens"]
    hits = []
    named = {t for t in row["tokens"] if t in SIDO and not (t == "광주" and row["sido"] == "경기")}  # 경기 광주시 ≠ 광주광역시
    scope = {row["sido"]} | ({row.get("region")} & set(SIDO)) | named | NEIGHBOR.get(row["sido"], set())
    if row["sido"] == "경기":
        scope.discard("광주")  # '김포{인천 강화}'처럼 두 시도에 걸친 담당
    for (sd, off), sgg in offices.items():
        if row["sido"] and sd not in scope:
            continue
        on = off.replace("교육지원청", "")
        if any(st in on or any(g == st or g.startswith(st) for g in sgg if g) for st in stems):
            hits.append((sd, off))
    if whole and (not hits or not restricted):
        hits += [(sd, off) for (sd, off) in offices if sd == row["sido"]]
    if not hits and row["sido"] in row["tokens"]:
        hits = [(row["sido"], f"{row['sido']} 전역(교육청 직속)")]  # 세종처럼 교육지원청 없이 교육청이 직접 관할
    return sorted(set(hits)) if pairs else sorted({o for _, o in hits})


# ---------------- 지도(시군구) 연결: static_data/sigungu_geo.json ----------------
SIDO_FULL = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
             "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
             "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
             "제주특별자치도": "제주", "제주도": "제주"}
_GEO = None
# 지도(2018 경계) 이후 바뀐 행정구역: 인천 2026 개편(제물포·영종·검단·서해구), 미추홀구(옛 남구), 군위군(2023 경북 -> 대구)
GEO_ALIAS = {("인천", "제물포구"): [("인천", "중구"), ("인천", "동구")], ("인천", "영종구"): [("인천", "중구")],
             ("인천", "미추홀구"): [("인천", "남구")], ("인천", "검단구"): [("인천", "서구")], ("인천", "서해구"): [("인천", "서구")],
             ("대구", "군위군"): [("경북", "군위군")]}


def _geo():
    global _GEO
    if _GEO is None:
        try:
            _GEO = json.loads((HERE / "static_data/sigungu_geo.json").read_text(encoding="utf-8"))["features"]
        except (OSError, ValueError, KeyError):
            _GEO = []
    return _GEO


def sgg_codes(sd, name):
    """(시도, 시군구 이름) -> 지도 시군구 코드들. '수원시'는 4개 구, '세종'은 세종시 전체."""
    nm = re.sub(r"\s", "", name or "")
    if not nm:
        return []
    if (sd, nm) in GEO_ALIAS:
        return [f["c"] for s2, n2 in GEO_ALIAS[(sd, nm)] for f in _geo() if f["sd"] == s2 and f["n"] == n2]
    fs = [f for f in _geo() if f["sd"] == sd]
    hit = [f["c"] for f in fs if f["n"] == nm]
    return hit or [f["c"] for f in fs if f["n"].startswith(nm) or (len(nm) >= 2 and f["n"].startswith(_stem(nm)) and len(_stem(nm)) >= 2)]


def addr_code(addr):
    """주소 -> 시군구 코드 1개(사무실·학교 위치). '경기도 수원시 팔달구 …' -> 수원시팔달구. 시도 생략·옛 시 이름(마산)도 처리."""
    t = (addr or "").split()
    i = next((k for k, w in enumerate(t[:4]) if SIDO_FULL.get(w) or w[:2] in SIDO), None)
    sd = None
    if i is not None:
        sd = SIDO_FULL.get(t[i]) or t[i][:2]
        t = t[i + 1:]
    if sd == "세종":
        c = sgg_codes("세종", "세종시")
        return c[0] if c else None
    if not t:
        return None
    if sd and (sd, t[0]) in GEO_ALIAS:  # 인천 2026 개편 구·대구 군위군 -> 지도(2018) 경계
        c = sgg_codes(sd, t[0])
        return c[0] if c else None
    fs = [f for f in _geo() if not sd or f["sd"] == sd]
    w0 = ALIAS.get(_stem(t[0]), t[0])
    for key in ([t[0] + t[1]] if len(t) >= 2 else []) + [t[0], w0]:
        hit = [f["c"] for f in fs if f["n"] == key]
        if len(hit) == 1:
            return hit[0]
    hit = [f["c"] for f in fs if len(_stem(w0)) >= 2 and f["n"].startswith(_stem(w0))]
    return hit[0] if hit else None  # 구가 여러 개인 시(안산·천안)는 첫 구


def office_codes(sd, off, sgg_names):
    """교육지원청 -> 관할 시군구 코드. 시군구 목록이 없으면 이름(예: 화성오산·강남서초)을 2글자씩 나눠 맞춘다."""
    if off.endswith("전역(교육청 직속)"):
        return [f["c"] for f in _geo() if f["sd"] == sd]
    out = set()
    for g in sgg_names or []:
        out.update(sgg_codes(sd, g))
    # 교육지원청 이름에 든 시군 이름(구리남양주·군포의왕·광주하남) - 학교 명단에 빠진 시군 보강
    stem = re.sub(r"^.*?(특별자치도|특별자치시|광역시|특별시|도)(?=[가-힣])", "", off.replace("교육지원청", ""))
    for f in _geo():
        fs = _stem(re.sub(r"(시|군)[가-힣]+구$", r"\1", f["n"]))
        if f["sd"] == sd and len(fs) >= 2 and fs != f["n"] and fs in stem:
            out.add(f["c"])
    return sorted(out)


def geo_pack():
    """공개 지도 데이터: 시군구 경계 + 시군구별 AI 중점·디지털 선도학교 수(공개 명단, 학교 주소 기준)."""
    feats = _geo()
    if not feats:
        return None
    ai, dig = Counter(), Counter()
    try:
        for sc in json.loads((HERE / "static_data/ai_schools_2026.json").read_text(encoding="utf-8"))["schools"]:
            c = addr_code(sc.get("addr")) or next(iter(sgg_codes(sc.get("소속지역"), sc.get("시군구"))), None)
            if c:
                ai[c] += "AI 중점" in (sc.get("사업") or [])
                dig[c] += "디지털 선도" in (sc.get("사업") or [])
    except (OSError, ValueError, KeyError):
        pass
    return {"features": feats, "ai": dict(ai), "dig": dict(dig)}


def build(data, opp=None, today=None):
    """복호화된 총판 목록 -> 화면용 연결 데이터(관할 교육지원청·공고·학교·기회)."""
    if not data:
        return None
    today = today or date.today()
    rows, offices = data.get("rows", []), _offices()
    y1, d90 = (today - timedelta(365)).isoformat(), (today - timedelta(90)).isoformat()
    bids, seen = [], set()
    p = HERE / "history/training_bids.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(line)
            except ValueError:
                continue
            no = (b.get("k") or "").rsplit("-", 1)[0]
            if (b.get("d") or "") >= y1 and no not in seen:
                seen.add(no)
                bids.append(b)
    try:
        schools = json.loads((HERE / "static_data/ai_schools_2026.json").read_text(encoding="utf-8"))["schools"]
    except (OSError, ValueError, KeyError):
        schools = []
    sched = {}
    try:
        for r in json.loads((HERE / "history/neis_schedule.json").read_text(encoding="utf-8"))["regions"]:
            sched[r["region"]] = r.get("levels", {})
    except (OSError, ValueError, KeyError):
        pass
    out = []
    for r in rows:
        pairs = _match(r, offices, pairs=True)
        offs = sorted({o for _, o in pairs})
        stems = _stems(r)
        # 지도: 관할 교육지원청의 시군구 중 담당 지역 이름과 맞는 것만(교육지원청 일부만 맡는 총판), 없으면 교육지원청 전체
        sgg, names = set(), {f["c"]: f["n"] for f in _geo()}
        for sd_o, o in pairs:
            cs = office_codes(sd_o, o, offices.get((sd_o, o)))
            narrow = [c for c in cs if any(names.get(c, "").startswith(st) for st in stems if len(st) >= 2)]
            sgg.update(narrow or cs)
        my_bids = [b for b in bids if b.get("r") == r["sido"] and any(o.replace("교육지원청", "") in (b.get("o") or "") for o in offs)]
        my_sch = [s for s in schools if s.get("소속지역") == r["sido"] and (s.get("교육지원청") in offs or any((s.get("시군구") or "").startswith(st) for st in stems))]
        due = 0
        for s in my_sch:
            v = (sched.get(s["소속지역"], {}).get(s.get("학교급")) or {}).get("겨울방학")
            if v:
                dd = (date.fromisoformat(v) - timedelta(21) - today).days
                due += -7 <= dd <= 45
        out.append({**{k: r[k] for k in ("type", "code", "sido", "name", "staff", "area", "tel", "fax", "addr")},
                    "offices": offs, "bids12": len(my_bids), "bids90": sum(1 for b in my_bids if b["d"] >= d90),
                    "bid_amt": sum(b.get("a") or 0 for b in my_bids),
                    "recent": [{"t": b.get("t"), "o": b.get("o"), "d": b.get("d"), "u": b.get("u")} for b in sorted(my_bids, key=lambda b: b["d"], reverse=True)[:3]],
                    "ai": sum(1 for s in my_sch if "AI 중점" in (s.get("사업") or [])), "dig": sum(1 for s in my_sch if "디지털 선도" in (s.get("사업") or [])),
                    "due45": due, "sgg": sorted(sgg), "loc": addr_code(r.get("addr"))})
    # 시도 단위: 교육청 본청 공고(교육지원청 아닌 발주), 기회점수 상위 주제
    sido = {}
    for sd in SIDO:
        rs = [x for x in out if x["sido"] == sd]
        hq = [b for b in bids if b.get("r") == sd and "교육지원청" not in (b.get("o") or "")]
        top = [c for c in ((opp or {}).get("cells") or []) if c.get("sido") == sd][:3]
        offs_all = {o for (s2, o) in offices if s2 == sd}
        covered = {o for x in out for o in x["offices"]}  # 다른 시도 총판이 함께 맡는 교육지원청 포함
        sido[sd] = {"n": len(rs), "hak": sum(1 for x in rs if x["type"] == "학판"), "gyo": sum(1 for x in rs if x["type"] == "교판"),
                    "hq_bids": len(hq), "offices": len(offs_all), "covered": len(covered & offs_all),
                    "uncovered": sorted(offs_all - covered)[:12],
                    "top": [{"topic": c["topic"], "score": c["score"], "action": c["action"]} for c in top]}
    return {"as_of": data.get("as_of", ""), "rows": out, "sido": sido, "generated": today.isoformat()}


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "convert":
        import strategy_crypto
        rows = convert(sys.argv[2])
        bad = [r for r in rows if not r["sido"]]
        offices = _offices()
        cnt = Counter((r["sido"], r["type"]) for r in rows)
        summ = {"as_of": "2014-11-03", "source": "비상교육 지사 주소록(학판·교판) - 상세는 암호문(로그인 뒤 화면)",
                "total": len(rows), "by_sido": [{"sido": sd, "학판": cnt[(sd, "학판")], "교판": cnt[(sd, "교판")]} for sd in SIDO],
                "matched_rows": sum(1 for r in rows if _match(r, offices)), "unknown_sido": len(bad)}
        (HERE / "static_data/branch_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        blob = {"as_of": "2014-11-03", "rows": rows}
        txt = json.dumps(blob, ensure_ascii=False)
        assert not re.search(r"01[016789]-\d{3,4}-\d{4}", txt), "휴대폰 번호가 섞였습니다"
        (HERE / "static_data/branch_network.enc.json").write_text(json.dumps(strategy_crypto.encrypt(blob)), encoding="utf-8")
        print(f"총판 {len(rows)}곳(학판 {sum(r['type'] == '학판' for r in rows)}·교판 {sum(r['type'] == '교판' for r in rows)}) · "
              f"시도 미상 {len(bad)} · 교육지원청 연결 {summ['matched_rows']}곳 -> 암호문·요약 저장")
        for r in bad[:10]:
            print("  시도 미상:", r["code"], r["region"])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
