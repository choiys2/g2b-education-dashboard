#!/usr/bin/env python3
"""
시도교육청 AIEP(AI 맞춤형 교수학습 플랫폼) 조달 시장 수집 -> history/aiep_market.json (공개 조달 정보)

  - 나라장터 입찰공고(용역·물품)·낙찰·개찰 참가업체를 공고명 키워드(AIEP·교수학습 플랫폼·각 시도 플랫폼 이름)로 조회
  - 발주처가 교육청·교육(연구)정보원·KERIS 인 건만 남기고, 플랫폼 구축·운영과 연수(활용)로 나눈다
  - 개찰 참가업체 전체를 붙여 폭스커넥트 등 AIEP 개발사의 참여·낙찰 이력을 본다
  python aiep_market.py [--days 1095]
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_g2b_listings import call_api, guess_region, load_config

OUT = Path(__file__).parent / "history" / "aiep_market.json"
BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
SCS = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
KINDS = {"용역": "Servc", "물품": "Thng"}
THNG_KW = {"AIEP", "교수학습 플랫폼", "하이러닝", "다채움", "아이모두"}  # 물품(사용권·구독 구매)은 이 키워드만 - 호출 수 절약
KEYWORDS = ["AIEP", "교수학습 플랫폼", "교수학습플랫폼", "교수·학습 플랫폼", "교수학습지원 플랫폼", "AI 맞춤형", "AI맞춤형",
            "AI 교육플랫폼", "AI교육플랫폼", "AI 교육 플랫폼", "하이러닝", "다채움", "마주온", "에듀아이", "아이로", "SEN스쿨",
            "바당", "아이온", "아이든", "아이모두", "AI배움터", "우리아이", "AI드림"]
ORG_RE = re.compile(r"교육청|교육지원청|교육연구정보원|교육정보원|교육과학연구원|교육연구원|미래교육원|AI융합교육원|교육원|한국교육학술정보원")
TOPIC_RE = re.compile(r"AIEP|플랫폼|AI|인공지능|맞춤형|디지털|하이러닝|다채움|마주온|에듀아이|아이로|바당|아이온|아이든|아이모두|배움터|우리아이|AI드림|SEN")
VENDORS = {"폭스커넥트": ["폭스커넥트"], "비상교육": ["비상교육"], "천재교육": ["천재교육", "천재교과서"], "아이스크림": ["아이스크림"],
           "웅진씽크빅": ["웅진씽크빅"], "YBM": ["와이비엠"], "클래스팅": ["클래스팅"], "티처빌": ["테크빌"], "미래엔": ["미래엔"],
           "동아출판": ["동아출판"], "대교": ["대교"], "LG CNS": ["엘지씨엔에스", "LG CNS", "엘지 씨엔에스"], "삼성SDS": ["삼성에스디에스"],
           "KT": ["주식회사 케이티", "(주)케이티"], "SK": ["에스케이"], "아이스크림미디어": []}
PLAT = [("서울", "SEN스쿨"), ("인천", "에듀아이"), ("강원", "아이로"), ("대전", "AI드림"), ("세종", "세종 AI"), ("전북", "아이든"),
        ("광주", "아이온"), ("전남", "아이모두"), ("경북", "AI배움터"), ("울산", "우리아이"), ("제주", "바당"), ("경기", "하이러닝"),
        ("충북", "다채움"), ("충남", "마주온")]


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


def vendor_of(name):
    for k, als in VENDORS.items():
        if any(a and a in (name or "") for a in als):
            return k
    return ""


def kind_of(t):
    if re.search(r"연수|교원|교사|역량|활용|선도교사|컨설팅|홍보", t):
        return "연수·활용"
    if re.search(r"구축|개발|고도화|운영|유지|관리|플랫폼|시스템|클라우드|SW|소프트웨어|서비스|라이선스|구독|구매", t):
        return "구축·운영"
    return "기타"


def chunks(days):
    end, cur = datetime.now(), datetime.now() - timedelta(days=days)
    while cur < end:
        nxt = min(cur + timedelta(days=28), end)
        yield cur, nxt
        cur = nxt


def safe(e):
    return re.sub(r"serviceKey=[^&\s]+", "serviceKey=***", str(e))[:140]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--budget", type=int, default=1500, help="초 - 넘기면 모은 만큼 저장")
    a = ap.parse_args()
    cfg = load_config()
    if not cfg.get("service_key") or "YOUR_" in cfg.get("service_key", ""):
        print("G2B_SERVICE_KEY 없음 - 건너뜀")
        return 0
    t0 = time.time()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    bids, awards, parts = prev.get("bids", {}), prev.get("awards", {}), prev.get("participants", {})
    diag, iv = [], cfg.get("request_interval_sec", 0.15)
    done = set((prev.get("status") or {}).get("done3", []))  # done3: 날짜 형식 수정 후 다시 백필  # 3년 백필을 끝낸 키워드 - 이후엔 최근 120일만 다시
    days = a.days
    over = lambda: time.time() - t0 > a.budget

    def save(note):
        OUT.write_text(json.dumps({"updated": date.today().isoformat(), "bids": bids, "awards": awards, "participants": parts,
                                   "status": {"days": days, "done3": sorted(done), "diag": sorted(set(diag))[:40], "note": note, "sec": round(time.time() - t0)}},
                                  ensure_ascii=False, indent=1), encoding="utf-8")

    for kw in KEYWORDS:
        if over():
            break
        for kind, sfx in KINDS.items():
            if kind == "물품" and kw not in THNG_KW:
                continue
            for begin, end in chunks(120 if kw in done else days):
                if over():
                    break
                for base, op, store in ((BID, f"getBidPblancListInfo{sfx}PPSSrch", "bid"), (SCS, f"getScsbidListSttus{sfx}PPSSrch", "award")):
                    items, page, total, failed = [], 1, None, False
                    while total is None or (page - 1) * 100 < total:  # 행 수 상한 100(500은 '입력범위값 초과' 07)
                        p = {"serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 100, "inqryDiv": 1, "type": "json",
                             "inqryBgnDt": begin.strftime("%Y%m%d%H%M"), "inqryEndDt": end.strftime("%Y%m%d%H%M"), "bidNtceNm": kw}  # 기존 수집기와 같은 형식(끝 시각 23:59 고정은 미래 시각 -> 07 오류)
                        try:
                            got, total = call_api(base, op, p, timeout=25, retries=1)
                        except Exception as e:
                            diag.append(f"{op} {kw}: {safe(e)}")
                            failed = True
                            break
                        items += got
                        if not got or page >= 5:
                            break
                        page += 1
                    if failed and not items:
                        continue
                    for it in items:
                        t = first(it, "bidNtceNm")
                        org = f"{first(it, 'ntceInsttNm')} {first(it, 'dminsttNm')}"
                        if not ORG_RE.search(org) or not TOPIC_RE.search(t):
                            continue
                        k = f"{first(it, 'bidNtceNo')}-{first(it, 'bidNtceOrd') or '000'}"
                        if store == "bid":
                            dm = first(it, "dminsttNm") or first(it, "ntceInsttNm")
                            bids[k] = {"t": t, "kind": kind, "cat": kind_of(t), "org": dm, "r": guess_region(dm, first(it, "ntceInsttNm")),
                                       "d": str(first(it, "bidNtceDt", "rgstDt"))[:10], "budget": num(first(it, "asignBdgtAmt")) or num(first(it, "presmptPrce")),
                                       "method": first(it, "cntrctCnclsMthdNm"), "kw": kw,
                                       "u": f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={first(it, 'bidNtceNo')}&bidPbancOrd={first(it, 'bidNtceOrd') or '000'}"}
                        else:
                            dm = first(it, "dminsttNm") or first(it, "ntceInsttNm")
                            w = first(it, "bidwinnrNm")
                            awards[k] = {"t": t, "kind": kind, "org": dm, "r": guess_region(dm), "d": str(first(it, "rlOpengDt", "fnlSucsfDate"))[:10],
                                         "winner": w, "v": vendor_of(w), "amt": num(first(it, "sucsfbidAmt")), "n": num(first(it, "prtcptCnum"))}
                    time.sleep(iv)
        if not over() and not any(kw in x for x in diag):
            done.add(kw)
        save(f"키워드 {kw}")
        print(f"  {kw}: 공고 {len(bids)} · 낙찰 {len(awards)} · {round(time.time() - t0)}초", flush=True)
    # 낙찰 건 참가업체 전체(개발사 참여 이력)
    n = 0
    for k, v in sorted(awards.items(), key=lambda x: x[1].get("d") or "", reverse=True):
        if k in parts or over() or n >= 250:
            continue
        no, od = k.rsplit("-", 1)
        n += 1
        try:
            items, _ = call_api(SCS, "getOpengResultListInfoOpengCompt", {"serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 100,
                                                                          "type": "json", "bidNtceNo": no, "bidNtceOrd": od}, timeout=20, retries=1)
            parts[k] = [{"corp": first(i, "prcbdrNm", "bidprcCorpNm"), "rank": num(first(i, "opengRank")), "amt": num(first(i, "bidprcAmt")),
                         "v": vendor_of(first(i, "prcbdrNm", "bidprcCorpNm"))} for i in items]
            time.sleep(iv)
        except Exception as e:
            diag.append(f"OpengCompt: {safe(e)}")
    save("완료")
    fox_w = [v for v in awards.values() if v.get("v") == "폭스커넥트"]
    fox_p = [k for k, ps in parts.items() if any(p.get("v") == "폭스커넥트" for p in ps)]
    print(f"AIEP 조달: 공고 {len(bids)} · 낙찰 {len(awards)} · 참가업체 {len(parts)}건 · 폭스커넥트 낙찰 {len(fox_w)} · 참여 {len(fox_p)} · "
          f"{round(time.time() - t0)}초 · 진단 {len(set(diag))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
