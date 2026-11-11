#!/usr/bin/env python3
"""
학원·교습소 시군구 집계 -> history/academy_stats.json (나이스 교육정보 개방포털 '학원교습소정보', 공개 데이터)

  - 개별 학원 이름·연락처·대표자는 저장하지 않는다. 시군구 × 분야/계열 개수와 정원 합계만 남긴다.
  - 주 1회(academy.yml). 키: NEIS_KEY(나라장터 호출 한도와 무관)
  python academy_stats.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "history" / "academy_stats.json"
KEY = os.environ.get("NEIS_KEY", "")
OFC = {"B10": "서울", "C10": "부산", "D10": "대구", "E10": "인천", "F10": "광주", "G10": "대전", "H10": "울산", "I10": "세종",
       "J10": "경기", "K10": "강원", "M10": "충북", "N10": "충남", "P10": "전북", "Q10": "전남", "R10": "경북", "S10": "경남", "T10": "제주"}


def call(params, retries=3):
    url = "https://open.neis.go.kr/hub/acaInsTiInfo?" + urllib.parse.urlencode(params)
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise RuntimeError(re.sub(r"KEY=[^&]+", "KEY=***", str(e))[:120])
            time.sleep(3 * (i + 1))


def main():
    if not KEY:
        print("NEIS_KEY 없음 - 건너뜀")
        return 0
    sys.path.insert(0, str(HERE))
    import branch_network as bn
    agg = defaultdict(lambda: {"n": 0, "cap": 0, "realm": Counter(), "ord": Counter()})
    total, diag, t0 = 0, [], time.time()
    for code, sd in OFC.items():
        page = 1
        while True:
            try:
                d = call({"KEY": KEY, "Type": "json", "pIndex": page, "pSize": 1000, "ATPT_OFCDC_SC_CODE": code})
            except RuntimeError as e:
                diag.append(f"{sd} p{page}: {e}")
                break
            blk = d.get("acaInsTiInfo")
            if not blk:
                res = (d.get("RESULT") or {}).get("CODE", "")
                if res and res != "INFO-200":
                    diag.append(f"{sd}: {res}")
                break
            rows = blk[1].get("row", []) if len(blk) > 1 else []
            for r in rows:
                if "개원" not in (r.get("REG_STTUS_NM") or "개원"):
                    continue
                gu = (r.get("ADMST_ZONE_NM") or "").strip()
                a = agg[(sd, gu)]
                a["n"] += 1
                try:
                    a["cap"] += int(float(r.get("TOFOR_SMTOT") or 0))
                except ValueError:
                    pass
                a["realm"][(r.get("REALM_SC_NM") or "기타").strip()] += 1
                a["ord"][(r.get("LE_ORD_NM") or "기타").strip()] += 1
                total += 1
            if len(rows) < 1000:
                break
            page += 1
            time.sleep(0.3)
        print(f"  {sd}: 누적 {total}", flush=True)
    out = []
    for (sd, gu), a in sorted(agg.items()):
        codes = bn.sgg_codes(sd, gu) if gu else []
        out.append({"sd": sd, "gu": gu, "sgg": codes, "n": a["n"], "cap": a["cap"],
                    "realm": a["realm"].most_common(6), "ord": a["ord"].most_common(6)})
    if not out and OUT.exists():
        print("수집 0건 - 이전 파일 유지")
        return 0
    OUT.write_text(json.dumps({"generated": date.today().isoformat(), "source": "나이스 교육정보 개방포털 학원교습소정보(개원)",
                               "total": total, "rows": out, "diag": diag[:20], "sec": round(time.time() - t0)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"학원·교습소 {total}곳 · 시군구 {len(out)} · 진단 {len(diag)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
