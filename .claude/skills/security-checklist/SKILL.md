---
name: security-checklist
description: 새 수집기·워크플로·외부 링크·외부 데이터 표시·배포 변경을 추가하거나 수정할 때 사용하는 보안 점검 체크리스트(CLAUDE.md 규칙 1~9의 실행판).
---

# 보안 체크리스트 (변경 전 → 후)

## 변경 전
- [ ] 비밀값(키·토큰·비밀번호)을 코드·커밋·로그·채팅에 쓰지 않는가? 로그는 "설정됨/미설정"만. (규칙 1)
- [ ] 공개 저장소에 내부 주소·개인 실명·휴대폰·계좌·이메일이 들어가지 않는가? 필요하면 `config/links.json`·시크릿·`strategy_crypto` 사용. (규칙 2)
- [ ] 바깥 링크는 https + 허용 도메인뿐이고 새 창에 `rel="noopener noreferrer"` 가 있는가? (규칙 3)
- [ ] 화면에 넣는 외부 데이터는 `h()` 로 이스케이프했는가(`<strong>`만 예외)? innerHTML 직접 삽입 금지. (규칙 4)
- [ ] 새 워크플로: 최소 `permissions`, 공식 액션(`actions/*`)만, `pull_request_target` 금지, 오류 메시지의 serviceKey 가림(`safe()`). (규칙 5)

## 변경 후 (실행)
```bash
python3 security_check.py repo          # 추적 파일의 비밀값·휴대폰 번호 점검(값은 출력하지 않음)
python3 security_check.py site _site    # 배포 직전 산출물 점검(빌드 후 사용 가능할 때)
```
- 차단 0 · 경고 0 이어야 한다. 하나라도 있으면 원인을 고치고 다시 실행(점검 우회 금지). (규칙 6)
- 대시보드는 GitHub Pages 공개본에 두지 않는다(`gh_public_site.py`), 배포 미리보기 주소를 공개 로그에 남기지 않는다. (규칙 7)

## 보고 (규칙 9)
새 연결을 붙였으면 사용자에게 한 줄로: **무엇이 어디에 노출되는지**(공개 / 로그인 뒤 / 암호화).
