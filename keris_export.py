#!/usr/bin/env python3
"""
한국교육학술정보원(KERIS, 기관코드 B550629) 나라장터 조달 수집 -> history/keris_procurement.json

  - 입찰공고(용역·물품): 공고기관 또는 수요기관이 KERIS 인 건
  - 개찰결과: 참가업체 수, 1순위 업체, 진행 구분(개찰완료·유찰 등)
  - 낙찰: 낙찰업체·낙찰금액·낙찰률
  - 관련 분야(연수·콘텐츠·AI/에듀테크) 건은 개찰 참가업체 전체 목록까지(자사·경쟁사 참여 이력)
처음엔 3년 백필, 이후엔 매일 최근 60일만 다시 조회해 합친다(키: 공고번호-차수).
API 키는 G2B_SERVICE_KEY(입찰공고정보서비스·낙찰정보서비스 활용승인 완료 키). 응답 필드명이 문서마다 달라
여러 후보 이름을 차례로 읽고, 첫 응답의 필드 목록을 status 에 남긴다(키는 기록하지 않음).

  python keris_export.py [--days 60] [--backfill-days 1095]
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_g2b_listings import call_api, load_config

OUT = Path(__file__).parent / "history" / "keris_procurement.json"
INST_CD, INST_NM = "B550629", "한국교육학술정보원"
BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
SCS = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
KINDS = {"용역": "Servc", "물품": "Thng"}
RELEVANT_RE = re.compile(r"연수|교원|교사|역량\s?강화|콘텐츠|교재|강좌|이러닝|원격\s?교육|AI|인공지능|에듀테크|디지털\s?교과서|AIDT|"
                         r"디지털\s?교육|수업|교육과정|SW\s?교육|코딩|컨소시엄|학습")
COMPANIES = {"비상교육(자사)": ["비상교육"], "티처빌": ["테크빌교육"], "아이스크림": ["아이스크림미디어", "아이스크림에듀"],
             "천재교육": ["천재교육", "천재교과서"], "웅진씽크빅": ["웅진씽크빅"], "YBM": ["와이비엠"], "클래스팅": ["클래스팅"]}


def first(it, *keys):
    for k in keys:
        v = it.get(k)
        if v not in (None, ""):
            return v
    return ""


def num(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def is_keris(it):
    return INST_NM in (first(it, "ntceInsttNm") + first(it, "dminsttNm"))


def _unused_months(days):
    end = datetime.now()
    cur = end - timedelta(days=days)
    while cur < end:
        nxt = min(cur + timedelta(days=28), end)
        yield cur, nxt
        cur = nxt


FILTERS = [{"ntceInsttCd": INST_CD}, {"dminsttCd": INST_CD}, {"ntceInsttNm": INST_NM}, {"dminsttNm": INST_NM}]


def probe(cfg, base, op, diag):
    """최근 4주로 필터를 하나씩 시험해 서버에서 실제로 걸러지는 것만 고른다(오류·과다 결과는 제외)."""
    end, begin = datetime.now(), datetime.now() - timedelta(days=28)
    ok = []
    for flt in FILTERS:
        p = {"serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 10, "inqryDiv": 1, "type": "json",
             "inqryBgnDt": begin.strftime("%Y%m%d0000"), "inqryEndDt": end.strftime("%Y%m%d2359"), **flt}
        try:
            _, total = call_api(base, op, p, timeout=20, retries=1)
        except Exception as e:
            msg = re.sub(r"serviceKey=[^&\s]+", "serviceKey=***", str(e))[:160]  # 키는 기록하지 않는다
            diag.append(f"{op}/{list(flt)[0]}: {msg}")
            continue
        if total > 3000:  # 4주에 KERIS 단독 3천 건은 불가능 -> 서버가 필터를 무시
            diag.append(f"{op}/{list(flt)[0]}: 필터 미동작(total {total})")
            continue
        ok.append(flt)
        print(f"  {op}: {list(flt)[0]} 사용(최근 4주 {total}건)", flush=True)
    codes = [f for f in ok if "InsttCd" in list(f)[0]]
    return codes or ok[:2]  # 기관코드 필터가 되면 이름 필터는 생략


def query(cfg, base, op, flts, begin, end, diag):
    out = []
    for flt in flts:
        page, total = 1, None
        while total is None or (page - 1) * 999 < total:
            p = {"serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 999, "inqryDiv": 1, "type": "json",
                 "inqryBgnDt": begin.strftime("%Y%m%d0000"), "inqryEndDt": end.strftime("%Y%m%d2359"), **flt}
            try:
                items, total = call_api(base, op, p, timeout=25, retries=1)
            except Exception as e:
                diag.append(f"{op}/{list(flt)[0]} {begin:%Y-%m}: {re.sub(r'serviceKey=[^&]+', 'serviceKey=***', str(e))[:120]}")
                break
            out.extend(i for i in items if is_keris(i))
            if not items or page >= 5:
                break
            page += 1
            time.sleep(cfg.get("request_interval_sec", 0.15))
    return out


def classify(t):
    for name, rx in (("연수·교육", r"연수|교원|교사|역량\s?강화|교육\s?운영|워크숍"), ("콘텐츠·교재", r"콘텐츠|교재|강좌|영상|제작|교과서"),
                     ("AI·에듀테크", r"AI|인공지능|에듀테크|디지털\s?교육|AIDT|코딩|SW\s?교육"),
                     ("연구·컨설팅", r"연구|조사|분석|평가|컨설팅|정책|진단"), ("시스템·SW", r"구축|고도화|개발|유지\s?보수|유지\s?관리|운영|시스템|플랫폼|클라우드|서버|네트워크|보안|DB|정보화|인프라|증설|나이스|NEIS|에듀파인|RISS|e학습터|SW|소프트웨어"),
                     ("홍보·행사", r"홍보|행사|박람회|세미나|포럼|컨퍼런스|대회|전시"), ("물품·장비", r"구매|임차|장비|라이선스|소모품|PC|노트북")):
        if re.search(rx, t):
            return name
    return "기타"


def company_of(name):
    for k, als in COMPANIES.items():
        if any(a in (name or "") for a in als):
            return k
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--backfill-days", type=int, default=1095)
    a = ap.parse_args()
    cfg = load_config()
    if not cfg.get("service_key") or "YOUR_" in cfg.get("service_key", ""):
        print("G2B_SERVICE_KEY 없음 - 건너뜀")
        return 0
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    bids, opens, awards, parts = (prev.get(k, {}) for k in ("bids", "opening", "awards", "participants"))
    st = prev.get("status", {})
    covered = st.get("covered_days", st.get("days", 0))  # 지금까지 거슬러 올라간 일수(백필 진행도, 첫 버전은 days)
    diag, fields = [], st.get("fields", {})

    def save(note=""):
        OUT.write_text(json.dumps({"updated": date.today().isoformat(), "inst": INST_NM, "bids": bids, "opening": opens,
                                   "awards": awards, "participants": parts,
                                   "status": {"covered_days": covered, "target_days": a.backfill_days, "diag": sorted(set(diag))[:40],
                                              "fields": fields, "note": note}}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 이번 실행 창: 최근 a.days(갱신) + 아직 안 본 과거 1년(백필, 목표 3년까지)
    windows = [(datetime.now() - timedelta(days=a.days), datetime.now())]
    if covered < a.backfill_days:
        back_end = datetime.now() - timedelta(days=max(covered, a.days))
        back_days = min(365, a.backfill_days - max(covered, a.days))
        windows.append((back_end - timedelta(days=back_days), back_end))
    ops = {}
    for kind, sfx in KINDS.items():
        for key, base, op in (("bid", BID, f"getBidPblancListInfo{sfx}PPSSrch"), ("opening", SCS, f"getOpengResultListInfo{sfx}PPSSrch"),
                              ("award", SCS, f"getScsbidListSttus{sfx}PPSSrch")):
            ops[(kind, key)] = (base, op, probe(cfg, base, op, diag))
    for w_begin, w_end in windows:
        chunks = []
        cur = w_begin
        while cur < w_end:
            nxt = min(cur + timedelta(days=28), w_end)
            chunks.append((cur, nxt))
            cur = nxt
        for kind, sfx in KINDS.items():
            base, op, flts = ops[(kind, "bid")]
            for begin, end in chunks if flts else []:
                for it in query(cfg, base, op, flts, begin, end, diag):
                    fields.setdefault("bid", sorted(it))
                    k = f"{first(it, 'bidNtceNo')}-{first(it, 'bidNtceOrd') or '00'}"
                    t = first(it, "bidNtceNm")
                    bids[k] = {"no": first(it, "bidNtceNo"), "ord": first(it, "bidNtceOrd"), "t": t, "kind": kind, "cat": classify(t),
                               "rel": bool(RELEVANT_RE.search(t)), "ntce": first(it, "ntceInsttNm"), "dmnd": first(it, "dminsttNm"),
                               "d": str(first(it, "bidNtceDt", "rgstDt"))[:10], "close": str(first(it, "bidClseDt"))[:16],
                               "open": str(first(it, "opengDt"))[:16], "budget": num(first(it, "asignBdgtAmt")),
                               "est": num(first(it, "presmptPrce")), "method": first(it, "cntrctCnclsMthdNm", "bidMethdNm"),
                               "award": first(it, "sucsfbidMthdNm"), "url": first(it, "bidNtceDtlUrl", "bidNtceUrl")}
            save("공고")
            base, op, flts = ops[(kind, "opening")]
            for begin, end in chunks if flts else []:
                for it in query(cfg, base, op, flts, begin, end, diag):
                    fields.setdefault("opening", sorted(it))
                    k = f"{first(it, 'bidNtceNo')}-{first(it, 'bidNtceOrd') or '00'}"
                    corp = str(first(it, "opengCorpInfo")).split("^")
                    opens[k] = {"t": first(it, "bidNtceNm"), "kind": kind, "d": str(first(it, "opengDt"))[:10],
                                "n": num(first(it, "prtcptCnum")), "status": first(it, "progrsDivCdNm"),
                                "first": corp[0] if corp and corp[0] else "", "first_amt": num(corp[3]) if len(corp) > 3 else None,
                                "first_rate": corp[4] if len(corp) > 4 else ""}
            save("개찰")
            base, op, flts = ops[(kind, "award")]
            for begin, end in chunks if flts else []:
                for it in query(cfg, base, op, flts, begin, end, diag):
                    fields.setdefault("award", sorted(it))
                    k = f"{first(it, 'bidNtceNo')}-{first(it, 'bidNtceOrd') or '00'}"
                    awards[k] = {"t": first(it, "bidNtceNm"), "kind": kind, "d": str(first(it, "rlOpengDt", "fnlSucsfDate"))[:10],
                                 "winner": first(it, "bidwinnrNm"), "amt": num(first(it, "sucsfbidAmt")),
                                 "rate": first(it, "sucsfbidRate"), "n": num(first(it, "prtcptCnum"))}
            save("낙찰")
        print(f"  창 {w_begin:%Y-%m-%d}~{w_end:%Y-%m-%d}: 공고 {len(bids)} · 개찰 {len(opens)} · 낙찰 {len(awards)}", flush=True)
    if len(windows) > 1:
        covered = max(covered, a.days) + (windows[1][1] - windows[1][0]).days
    elif not covered:
        covered = a.days
    # 관련 분야 개찰 건: 참가업체 전체(자사·경쟁사 참여 이력)
    n_calls = 0
    for k, o in sorted(opens.items(), key=lambda x: x[1].get("d") or "", reverse=True):
        b = bids.get(k, {})
        if n_calls >= 150:
            break
        if k in parts or not (b.get("rel") or RELEVANT_RE.search(o.get("t", ""))):
            continue
        no, ord_ = k.rsplit("-", 1)
        n_calls += 1
        try:
            items, _ = call_api(SCS, "getOpengResultListInfoOpengCompt",
                                {"serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 100, "type": "json",
                                 "bidNtceNo": no, "bidNtceOrd": ord_})
            fields.setdefault("participants", sorted(items[0]) if items else [])
            parts[k] = [{"corp": first(i, "prcbdrNm", "bidprcCorpNm"), "rank": num(first(i, "opengRank")),
                         "amt": num(first(i, "bidprcAmt")), "rate": first(i, "bidprcrt"), "co": company_of(first(i, "prcbdrNm", "bidprcCorpNm"))}
                        for i in items]
            time.sleep(cfg.get("request_interval_sec", 0.15))
        except Exception as e:
            diag.append(f"OpengCompt {k}: {str(e)[:120]}")
            if len(diag) > 80:
                break
    for v in awards.values():
        v["co"] = company_of(v.get("winner"))
    save("완료")
    print(f"KERIS 공고 {len(bids)} · 개찰 {len(opens)} · 낙찰 {len(awards)} · 참가목록 {len(parts)} · 진단 {len(set(diag))}건")
    for d in sorted(set(diag))[:15]:
        print("  ", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
