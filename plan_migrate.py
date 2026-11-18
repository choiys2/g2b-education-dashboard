#!/usr/bin/env python3
"""2027 경영계획 1회 이관: 시크릿 PLAN_2027_JSON → 비공개 저장소 파일(없을 때만).
이후 원본은 비공개 파일이며 채팅으로 갱신한다. 값은 절대 출력하지 않고 결과만 남긴다."""
import json
import os
import sys
from pathlib import Path


def main(dst):
    dst = Path(dst)
    if dst.exists():
        print("경영계획: 비공개 파일 있음 - 이관 불필요")
        return 0
    raw = os.environ.get("PLAN_2027_JSON", "").strip()
    if not raw:
        print("경영계획: 시크릿 미설정 - 이관 건너뜀")
        return 0
    try:
        plan = json.loads(raw)
        assert isinstance(plan, dict) and plan.get("sales")
    except Exception:
        print("경영계획: 시크릿 형식 오류 - 이관 건너뜀")
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("경영계획: 비공개 파일로 이관 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_private/strategy_room/plan_2027.json"))
