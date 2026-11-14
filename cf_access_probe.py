#!/usr/bin/env python3
"""
Cloudflare Access 정책 점검(수동 실행, cf_access_probe.yml) - 읽기만 한다.
공개 저장소 로그에 남으므로 이메일 주소·계정 ID·토큰은 출력하지 않는다(개수·도메인·규칙 종류만).
"""
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter

TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
ACC = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
API = "https://api.cloudflare.com/client/v4/accounts/{}/access/"


def get(path):
    req = urllib.request.Request(API.format(ACC) + path, headers={"Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode())
            msg = "; ".join(x.get("message", "") for x in d.get("errors", []))
        except Exception:  # noqa: BLE001
            msg = ""
        return {"success": False, "http": e.code, "msg": msg[:160]}


def rules(rs):
    out = []
    for r in rs or []:
        for k, v in r.items():
            if k == "email":
                out.append(("email", (v.get("email") or "").split("@")[-1]))
            elif k == "email_domain":
                out.append(("email_domain", v.get("domain", "")))
            elif k == "everyone":
                out.append(("everyone", "모든 사람"))
            elif k == "group":
                out.append(("group", "그룹"))
            else:
                out.append((k, ""))
    return out


def show(label, rs):
    c = Counter(rules(rs))
    if not c:
        return
    print(f"      {label}: " + ", ".join(f"{k}{'(' + d + ')' if d else ''}×{n}" for (k, d), n in c.items()))


def main():
    print("토큰:", "설정됨" if TOKEN else "미설정", "· 계정:", "설정됨" if ACC else "미설정")
    if not (TOKEN and ACC):
        return 0
    d = get("apps")
    if not d.get("success"):
        print(f"Access 앱 조회 불가: HTTP {d.get('http')} {d.get('msg')}")
        print("→ 배포용 토큰에 'Access: Apps and Policies 읽기' 권한이 없으면 이렇게 나온다(배포·보호에는 영향 없음).")
        return 0
    apps = d.get("result") or []
    print(f"Access 앱 {len(apps)}개")
    for a in apps:
        doms = [a.get("domain", "")] + [x.get("uri", x) if isinstance(x, dict) else x for x in (a.get("self_hosted_domains") or a.get("destinations") or [])]
        doms = sorted({re.sub(r"^https?://", "", str(x)) for x in doms if x})
        print(f"- {a.get('name')} · 유형 {a.get('type')} · 세션 {a.get('session_duration')} · 로그인 방식 {len(a.get('allowed_idps') or []) or '기본'}")
        print(f"    보호 주소: {', '.join(doms)}")
        pols = a.get("policies") or []
        if not pols:
            p = get(f"apps/{a.get('id')}/policies")
            pols = p.get("result") or []
        for p in pols:
            print(f"    정책 '{p.get('name')}' · 동작 {p.get('decision')} · 세션 {p.get('session_duration') or '앱 기본'}")
            show("허용(include)", p.get("include"))
            show("필수(require)", p.get("require"))
            show("제외(exclude)", p.get("exclude"))
            if any(k == "everyone" for k, _ in rules(p.get("include"))) and p.get("decision") == "allow":
                print("    ⚠ 모든 사람 허용 규칙이 있다 - 확인 필요")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
