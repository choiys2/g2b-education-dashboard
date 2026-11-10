#!/usr/bin/env python3
"""
학교단위 발주(학교가 직접 나라장터에 낸 AI·에듀테크 물품·용역) 수집 -> history/school_goods.json (공개 조달 정보)

  - 입찰공고(물품·용역) + 낙찰(물품·용역)을 공고명 키워드로 조회하고, 발주기관이 초·중·고 학교인 건만 남긴다
  - 누적: 키(공고번호-차수|공고/낙찰)로 합치므로 지난 건은 지워지지 않는다
  - 첫 실행(또는 --since 지정)은 올해 1월부터, 이후 주 1회(school_goods.yml) 최근 --days 일만 다시 조회
  - 2천만 원 이하 소액은 학교장터(S2B)로 많이 가므로 나라장터 등록분만 잡힌다(대시보드에 안내)
  python school_goods.py [--days 35] [--since 2026-01-01]
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

OUT = Path(__file__).parent / "history" / "school_goods.json"
BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
SCS = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
KINDS = {"물품": "Thng", "용역": "Servc"}
KEYWORDS = ["AI", "인공지능", "에듀테크", "디지털", "코스웨어", "메타버스", "코딩", "로봇"]
SCHOOL_RE = re.compile(r"(초등학교|중학교|고등학교|학교)$|(초등학교|중학교|고등학교)\s")
TITLE_RE = re.compile(r"AI|인공지능|에듀테크|디지털|코스웨어|메타버스|코딩|로봇|스마트|SW|소프트웨어|VR|AR|피지컬", re.I)
SKIP_RE = re.compile(r"급식|청소|경비|시설공사|공사|석면|도색|방역|통학|운송|수학여행|현장체험|졸업앨범|교복")


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
        return 0


def grade(name):
    if "초등학교" in name or re.search(r"초$", name):
        return "초"
    if "중학교" in name or re.search(r"중$", name):
        return "중"
    if "고등학교" in name or re.search(r"고$", name):
        return "고"
    return "기타"


def chunks(begin, end, days=7):  # 키워드 검색은 28일 구간에서 07(입력범위 초과) - 7일로 나눔(2026-11-10 실측)
    """최신 기간부터 거꾸로(키워드 검색이 오래된 기간에서 07 '입력범위값 초과'를 내면 그 지점에서 멈춘다)."""
    out, cur = [], begin
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        out.append((cur, nxt))
        cur = nxt
    return out[::-1]


def safe(e):
    """API 오류는 resultCode·resultMsg 만 남긴다(본문 앞부분에서 잘려 원인 판정이 안 되던 문제)."""
    s = re.sub(r"serviceKey=[^&\s]+", "serviceKey=***", str(e))
    c, m = re.search(r'resultCode"?\s*:\s*"?(\w+)', s), re.search(r'resultMsg"?\s*:\s*"?([^"\n}]+)', s)
    if c:
        return f"code {c.group(1)} {(m.group(1).strip() if m else '')}"[:80]
    return s[:140]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--since", default="")
    ap.add_argument("--budget", type=int, default=1200, help="초 - 넘기면 모은 만큼 저장하고 끝냄")
    a = ap.parse_args()
    cfg = load_config()
    if not cfg.get("service_key") or "YOUR_" in cfg.get("service_key", ""):
        print("G2B_SERVICE_KEY 없음 - 건너뜀")
        return 0
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = {r["_key"]: r for r in prev.get("rows", []) if r.get("_key")}
    st = prev.get("status") or {}
    end = datetime.now()
    if a.since:
        begin = datetime.fromisoformat(a.since)
    elif not st.get("backfilled"):
        begin = datetime(end.year, 1, 1)  # 첫 자동 수집: 올해 1월부터
    else:
        begin = end - timedelta(days=a.days)
    t0, diag, n_new, iv = time.time(), [], 0, max(0.4, cfg.get("request_interval_sec", 0.15))  # 429 방지
    stop07, done_kw = {}, []

    def save(note):
        out = sorted(rows.values(), key=lambda r: r.get("공고일") or "", reverse=True)
        OUT.write_text(json.dumps({"updated": date.today().isoformat(), "source": prev.get("source") or "나라장터 입찰공고·낙찰(물품·용역) - 학교 직접 발주 AI·에듀테크",
                                   "rows": out, "status": {"backfilled": len(done_kw) == len(KEYWORDS) or bool(st.get("backfilled")),
                                                           "window": f"{begin:%Y-%m-%d}~{end:%Y-%m-%d}", "new": n_new, "done": done_kw,
                                                           "stop07": stop07, "note": note, "sec": round(time.time() - t0), "diag": sorted(set(diag))[:20]}},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        return out

    for kw in KEYWORDS:
        if time.time() - t0 > a.budget:
            break
        for kind, sfx in KINDS.items():
            stop = set()
            kw_begin = max(begin, end - timedelta(days=a.days)) if kw in (st.get("done") or []) and not a.since else begin  # 이미 백필한 키워드는 최근만
            for b, e in chunks(kw_begin, end):
                if time.time() - t0 > a.budget or len(stop) == 2:
                    break
                for base, op, src in ((BID, f"getBidPblancListInfo{sfx}PPSSrch", "입찰공고(진행중/예정)"), (SCS, f"getScsbidListSttus{sfx}PPSSrch", "낙찰완료")):
                    if op in stop:
                        continue
                    page, total = 1, None
                    while total is None or (page - 1) * 100 < total:
                        p = {"serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 100, "inqryDiv": 1, "type": "json",
                             "inqryBgnDt": b.strftime("%Y%m%d%H%M"), "inqryEndDt": e.strftime("%Y%m%d%H%M"), "bidNtceNm": kw}
                        try:
                            items, total = call_api(base, op, p, timeout=25, retries=1)
                        except Exception as ex:
                            if "429" in str(ex):  # 요청 과다 - 쉬었다가 한 번 더
                                time.sleep(30)
                                try:
                                    items, total = call_api(base, op, p, timeout=25, retries=1)
                                except Exception as ex2:
                                    diag.append(f"{op} {kw} {b:%Y-%m}: {safe(ex2)[:60]}")
                                    break
                            else:
                                if '"07"' in str(ex) or "입력범위" in str(ex):
                                    stop.add(op)
                                    stop07[f"{op}|{kw}"] = f"{e:%Y-%m-%d}"
                                diag.append(f"{op} {kw} {b:%m-%d}~{e:%m-%d}: {safe(ex)}")
                                break
                        for it in items:
                            org = first(it, "dminsttNm", "ntceInsttNm")
                            t = first(it, "bidNtceNm")
                            if not SCHOOL_RE.search(org) or not TITLE_RE.search(t) or SKIP_RE.search(t):
                                continue
                            no, od = first(it, "bidNtceNo"), first(it, "bidNtceOrd") or "000"
                            key = f"{no}-{od}|{'낙찰' if src == '낙찰완료' else '공고'}"
                            amt = num(first(it, "sucsfbidAmt")) if src == "낙찰완료" else (num(first(it, "asignBdgtAmt")) or num(first(it, "presmptPrce")))
                            r = {"학교명": org, "학교급": grade(org.split(" ")[-1]), "상품명": t.strip(), "예산": amt,
                                 "공고일": str(first(it, "bidNtceDt", "rlOpengDt", "fnlSucsfDate"))[:10],
                                 "마감일": str(first(it, "bidClseDt"))[:10] if src != "낙찰완료" else "",
                                 "지역": guess_region(org, first(it, "ntceInsttNm")), "구분": kind,
                                 "url": f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={no}&bidPbancOrd={od}",
                                 "_출처": src, "_key": key}
                            if src == "낙찰완료":
                                r["낙찰업체"] = first(it, "bidwinnrNm")
                            if key not in rows:
                                n_new += 1
                            rows[key] = r
                        if not items or page >= 5:
                            break
                        page += 1
                        time.sleep(iv)
                time.sleep(iv)
        if time.time() - t0 <= a.budget:
            done_kw.append(kw)
        save(f"키워드 {kw}")
        print(f"  {kw}: 누적 {len(rows)}건 · 신규 {n_new} · {round(time.time() - t0)}초", flush=True)
    out = save("완료" if len(done_kw) == len(KEYWORDS) else "시간 예산 - 다음 실행에서 이어서")
    print(f"학교단위 발주: 총 {len(out)}건(신규 {n_new}) · 조회 {begin:%Y-%m-%d}~{end:%Y-%m-%d} · {round(time.time() - t0)}초 · 진단 {len(set(diag))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
