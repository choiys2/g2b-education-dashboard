#!/usr/bin/env python3
"""
협력 후보 스크랩(대학·기업·주제) -> history/partner_news.json (주 1회, partner_news.yml)

static_data/industry_trend_2027.json 의 scrap_targets(초등 교원양성대학 13곳·RISE 검토 대학·협력 기업·독서 인문학 등 주제)로
최근 180일 뉴스 제목을 모은다. 네이버 검색 API(있으면) -> 없으면 구글 뉴스 RSS. 제목·언론사·날짜·링크만 저장(본문 X).
대상은 scrap_targets 에 이름을 추가하면 다음 수집부터 함께 모인다.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from teacher_group_news import google, naver

SRC = Path("static_data/industry_trend_2027.json")
OUT = Path("history/partner_news.json")
DAYS, PER = 180, 6


def main():
    t = json.loads(SRC.read_text(encoding="utf-8")).get("scrap_targets") or {}
    since = (date.today() - timedelta(DAYS)).isoformat()
    res, via, use_naver = {}, {"naver": 0, "google": 0}, True
    for kind, names in t.items():
        for nm in names:
            items = naver(nm) if use_naver else None
            if items is None:
                use_naver = False
                items = google(nm)
                via["google"] += 1
            else:
                via["naver"] += 1
            words = [w for w in re.split(r"\s+", nm) if len(w) >= 2]
            key = nm.replace(" ", "")
            if kind == "topic":  # 주제는 단어가 모두 제목에 있을 때만
                items = [i for i in items if all(w in i["t"] for w in words)]
            else:  # 기관·기업은 이름(앞 4글자 이상)이 제목에 있을 때만
                items = [i for i in items if key[:max(4, min(len(key), 6))] in i["t"].replace(" ", "")]
            seen, keep = set(), []
            for i in sorted((i for i in items if i["d"] >= since), key=lambda i: i["d"], reverse=True):
                k = re.sub(r"\W", "", i["t"])[:24]
                if k not in seen:
                    seen.add(k)
                    keep.append(i)
            if keep:
                res[nm] = {"kind": kind, "n": len(keep), "items": keep[:PER]}
            time.sleep(0.3)
    if not res:
        print("수집된 스크랩 없음 - 기존 파일 유지")
        return 0
    OUT.write_text(json.dumps({"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "since": since, "via": via, "items": res},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT} · 스크랩 있는 대상 {len(res)}곳 / {sum(len(v) for v in t.values())}곳 · {via}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
