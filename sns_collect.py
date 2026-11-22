#!/usr/bin/env python3
"""
SNS 핵심 계정 주간 지표 -> history/sns_metrics.enc.json (공개키 암호화). teacher_group_news.yml 에서 주 1회.

- Meta 공식 Graph API 'Business Discovery' 만 쓴다(무료, 크롤 없음): 우리 인스타그램 비즈니스 계정으로
  다른 비즈니스·크리에이터 계정의 팔로워·게시물 수·최근 게시물 반응을 조회한다. 개인(일반) 계정은 조회되지 않는다.
- 필요한 시크릿: META_IG_TOKEN(장기 토큰), META_IG_USER_ID(우리 IG 비즈니스 계정 id), STRATEGY_KEY(목록 복호화).
  없으면 '미설정'만 출력하고 끝낸다. 로그에는 계정 이름을 남기지 않고 건수만 남긴다.
- 게시물 본문(캡션)은 저장하지 않고 주제 유형 수만 센다. 호출은 계정당 1회, 시간당 한도(200) 안.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path("history/sns_metrics.enc.json")
VER = "v21.0"
TAGS = [("AI·디지털", r"AI|인공지능|디지털|에듀테크|챗GPT|코딩"), ("연수·행사", r"연수|세미나|포럼|대회|캠프|박람회|모집|신청"),
        ("성명·입장", r"성명|촉구|반대|규탄|입장|기자회견"), ("교권·처우", r"교권|처우|수당|민원|업무"), ("수업·자료", r"수업|자료|활동지|학급|교실"),
        ("이벤트·굿즈", r"이벤트|증정|굿즈|추첨|할인")]


def main():
    tok, uid, key = os.environ.get("META_IG_TOKEN", ""), os.environ.get("META_IG_USER_ID", ""), os.environ.get("STRATEGY_KEY", "")
    print("META_IG_TOKEN:", "설정됨" if tok else "미설정", "· META_IG_USER_ID:", "설정됨" if uid else "미설정", "· STRATEGY_KEY:", "설정됨" if key else "미설정")
    if not (tok and uid and key):
        return 0
    import strategy_crypto
    lst = strategy_crypto.decrypt(json.loads(Path("static_data/sns_watch.enc.json").read_text(encoding="utf-8")), key)
    prev = {}
    if OUT.exists():
        try:
            prev = strategy_crypto.decrypt(json.loads(OUT.read_text(encoding="utf-8")), key).get("accounts") or {}
        except Exception:  # noqa: BLE001
            prev = {}
    names = [a["ig"] for a in lst.get("accounts") or [] if re.match(r"^[A-Za-z0-9._]{1,30}$", a.get("ig") or "")]
    since = datetime.now(timezone.utc) - timedelta(days=30)
    res, ok, fail = {}, 0, 0
    for u in dict.fromkeys(names):
        f = f"business_discovery.username({u}){{followers_count,media_count,media.limit(20){{timestamp,like_count,comments_count,caption}}}}"
        url = f"https://graph.facebook.com/{VER}/{uid}?" + urllib.parse.urlencode({"fields": f, "access_token": tok})
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
                bd = json.loads(r.read()).get("business_discovery") or {}
        except Exception as e:  # noqa: BLE001  - 토큰이 담긴 주소를 로그에 남기지 않는다
            fail += 1
            print(f"  조회 실패 1건({type(e).__name__})")
            continue
        media = (bd.get("media") or {}).get("data") or []
        recent = [m for m in media if m.get("timestamp") and datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) >= since]
        tc = {}
        for m in media:
            for k, rx in TAGS:
                if re.search(rx, m.get("caption") or ""):
                    tc[k] = tc.get(k, 0) + 1
        eng = round(sum((m.get("like_count") or 0) + (m.get("comments_count") or 0) for m in media) / len(media), 1) if media else None
        fo = bd.get("followers_count")
        p = (prev.get(u) or {}).get("followers")
        res[u] = {"followers": fo, "media": bd.get("media_count"), "posts30": len(recent), "eng": eng, "tags": tc,
                  "dF": (fo - p) if isinstance(fo, int) and isinstance(p, int) else None}
        ok += 1
        time.sleep(1)
    if not res:
        print(f"수집 0건 · 실패 {fail}건 - 기존 파일 유지")
        return 0
    out = {"generated": datetime.now().strftime("%Y-%m-%d"), "accounts": {**prev, **res}}
    OUT.write_text(json.dumps(strategy_crypto.encrypt(out)), encoding="utf-8")
    print(f"저장(암호화): 성공 {ok} · 실패 {fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
