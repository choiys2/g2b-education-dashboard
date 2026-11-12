#!/usr/bin/env python3
"""
나라장터 API 상태 점검(수동 실행, g2b_probe_api.yml) - 서비스별로 1건만 호출해 결과코드만 출력한다.
serviceKey 는 출력하지 않는다(주소에서 가림).
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

KEY = os.environ.get("G2B_SERVICE_KEY", "")
END = datetime.now()
BEG = END - timedelta(days=7)
CHECKS = [
    ("입찰공고(검색)", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch", {"inqryDiv": 1, "bidNtceNm": "연수"}),
    ("입찰공고(전체)", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc", {"inqryDiv": 1}),
    ("낙찰(검색)", "https://apis.data.go.kr/1230000/as/ScsbidInfoService/getScsbidListSttusServcPPSSrch", {"inqryDiv": 1, "bidNtceNm": "연수"}),
    ("사전규격", "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc", {"inqryDiv": 1}),
    ("발주계획", "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServc", {"inqryDiv": 1}),
]


def safe(s):
    return re.sub(r"serviceKey=[^&\s\"']+", "serviceKey=***", str(s))


def one(name, url, q):
    try:
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q), timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
        d = json.loads(raw)
        h = (d.get("response") or {}).get("header") or (d.get("nkoneps.com.response.ResponseError") or {}).get("header") or {}
        tc = ((d.get("response") or {}).get("body") or {}).get("totalCount")
        print(f"  {name}: {h.get('resultCode')} {h.get('resultMsg')} · 건수 {tc}")
    except Exception as e:  # noqa: BLE001
        print(f"  {name}: {type(e).__name__} {safe(str(e))[:100]}")


def variants():
    """입찰공고 조회 조건별 허용 여부(07 입력범위값 초과 원인 찾기)"""
    url = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"
    now = datetime.now()
    base = {"serviceKey": KEY, "pageNo": 1, "type": "json"}
    for label, extra in [
        ("1일·10건", {"numOfRows": 10, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(days=1)).strftime("%Y%m%d%H%M"), "inqryEndDt": now.strftime("%Y%m%d%H%M")}),
        ("1일·100건", {"numOfRows": 100, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(days=1)).strftime("%Y%m%d%H%M"), "inqryEndDt": now.strftime("%Y%m%d%H%M")}),
        ("3일·10건", {"numOfRows": 10, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(days=3)).strftime("%Y%m%d0000"), "inqryEndDt": now.strftime("%Y%m%d2359")}),
        ("어제 하루(00~23:59)", {"numOfRows": 10, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(days=1)).strftime("%Y%m%d0000"), "inqryEndDt": (now - timedelta(days=1)).strftime("%Y%m%d2359")}),
        ("종료=지금(분)", {"numOfRows": 10, "inqryDiv": 1, "inqryBgnDt": (now - timedelta(days=2)).strftime("%Y%m%d%H%M"), "inqryEndDt": now.strftime("%Y%m%d%H%M")}),
        ("inqryDiv 2(개찰일)", {"numOfRows": 10, "inqryDiv": 2, "inqryBgnDt": (now - timedelta(days=2)).strftime("%Y%m%d0000"), "inqryEndDt": now.strftime("%Y%m%d2359")}),
        ("날짜 없이", {"numOfRows": 10, "inqryDiv": 1}),
    ]:
        one(label, url, {**base, **extra})


def main():
    print("키:", "설정됨" if KEY else "미설정")
    for name, url, extra in CHECKS:
        q = {"serviceKey": KEY, "pageNo": 1, "numOfRows": 1, "type": "json",
             "inqryBgnDt": BEG.strftime("%Y%m%d0000"), "inqryEndDt": END.strftime("%Y%m%d2359"), **extra}
        try:
            with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q), timeout=25) as r:
                raw = r.read().decode("utf-8", "replace")
            try:
                d = json.loads(raw)
                h = (d.get("response") or {}).get("header") or (d.get("nkoneps.com.response.ResponseError") or {}).get("header") or {}
                tc = ((d.get("response") or {}).get("body") or {}).get("totalCount")
                print(f"{name}: 결과코드 {h.get('resultCode')} {h.get('resultMsg')} · 건수 {tc}")
            except ValueError:
                print(f"{name}: JSON 아님 - {safe(raw[:160])}")
        except Exception as e:  # noqa: BLE001
            print(f"{name}: {type(e).__name__} {getattr(e, 'code', '')} {safe(str(e))[:120]}")


if __name__ == "__main__":
    main()
    print("입찰공고 조건별:")
    variants()
