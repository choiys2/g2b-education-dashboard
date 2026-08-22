#!/usr/bin/env python3
"""
루틴 비서 7인의 얼굴을 SVG로 그린다.

사진 대신 벡터 초상을 쓰는 이유: 초상권 문제가 없고, 파일 하나에 인라인으로
들어가며(외부 요청 0), 원형 마스크 안에서 어느 크기로 키워도 뭉개지지 않는다.

spec 키:
  skin / hair / top / bg  : 색
  style                   : 헤어스타일 (HAIR 딕셔너리 키)
  glasses                 : "none" | "round" | "rect"
  beard                   : bool
"""

HEAD_CY = 45.0


def _clamp(v):
    return max(0, min(255, int(round(v))))


def shade(hex_color, pct):
    """pct > 0 이면 밝게, < 0 이면 어둡게."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if pct >= 0:
        r, g, b = (c + (255 - c) * pct for c in (r, g, b))
    else:
        r, g, b = (c * (1 + pct) for c in (r, g, b))
    return "#%02X%02X%02X" % (_clamp(r), _clamp(g), _clamp(b))


# 머리 모양. 각 값은 head(cx=50, cy=45, rx=19, ry=22) 위에 얹히는 path 묶음.
HAIR = {
    # 가르마 있는 짧은 머리
    "sidepart": (
        '<path d="M31 44c-1-14 7-22 19-22s20 8 19 22c0-9-4-13-9-14'
        '-5-1-9 2-14 1-6-1-9 3-9 9-2 1-4 2-6 4z"/>'
        '<path d="M62 24c5 3 8 8 8 15-3-6-8-9-14-10z"/>'
    ),
    # 단발
    "bob": (
        '<path d="M29 48c-2-17 8-27 21-27s23 10 21 27c-1-4-2-8-3-11'
        '-3 4-9 6-18 6-8 0-14-2-17-6-2 3-3 7-4 11z"/>'
        '<path d="M29 44c-1 8-1 14 0 20 2 1 4 1 5-1-2-6-3-12-2-19z"/>'
        '<path d="M71 44c1 8 1 14 0 20-2 1-4 1-5-1 2-6 3-12 2-19z"/>'
    ),
    # 아주 짧은 스포츠컷
    "crop": (
        '<path d="M31 45c-1-15 8-23 19-23s20 8 19 23c-2-4-3-7-5-9'
        '-4-3-9-4-14-4s-10 1-14 4c-2 2-3 5-5 9z"/>'
    ),
    # 하나로 묶은 머리
    "ponytail": (
        '<path d="M30 47c-2-16 8-26 20-26s22 10 20 26c-2-5-3-9-5-12'
        '-4-4-9-5-15-5s-11 1-15 5c-2 3-3 7-5 12z"/>'
        '<path d="M70 38c5 1 9 6 9 13 0 6-2 11-6 14-2 1-4-1-3-3 3-3 4-7 4-12 0-5-2-9-5-10z"/>'
    ),
    # 긴 생머리
    "long": (
        '<path d="M29 48c-2-17 8-27 21-27s23 10 21 27c-1-5-2-9-4-12'
        '-4-4-10-6-17-6s-13 2-17 6c-2 3-3 7-4 12z"/>'
        '<path d="M29 45c-2 12-2 22 0 33 2 2 6 2 7 0-3-11-4-21-2-33z"/>'
        '<path d="M71 45c2 12 2 22 0 33-2 2-6 2-7 0 3-11 4-21 2-33z"/>'
    ),
    # 짧은 곱슬
    "curly": (
        '<circle cx="38" cy="29" r="7"/><circle cx="50" cy="25" r="8"/>'
        '<circle cx="62" cy="29" r="7"/><circle cx="32" cy="38" r="6"/>'
        '<circle cx="68" cy="38" r="6"/>'
        '<path d="M31 44c-1-13 8-21 19-21s20 8 19 21c-3-7-9-11-19-11s-16 4-19 11z"/>'
    ),
    # 웨이브
    "wavy": (
        '<path d="M31 46c-2-15 7-24 19-24s21 9 19 24c-2-5-3-9-5-11'
        '-3 3-7 2-10-1-3 4-8 5-12 3-4 1-8 4-11 9z"/>'
    ),
}


def _glasses(kind, color="#2E2A26"):
    if kind == "round":
        return (
            f'<g fill="none" stroke="{color}" stroke-width="1.5" opacity=".85">'
            '<circle cx="42.5" cy="45" r="6"/><circle cx="57.5" cy="45" r="6"/>'
            '<path d="M48.5 45h3"/><path d="M36.5 44l-4-1"/><path d="M63.5 44l4-1"/></g>'
        )
    if kind == "rect":
        return (
            f'<g fill="none" stroke="{color}" stroke-width="1.5" opacity=".85">'
            '<rect x="36" y="40.5" width="13" height="9" rx="2.5"/>'
            '<rect x="51" y="40.5" width="13" height="9" rx="2.5"/>'
            '<path d="M49 44.5h2"/><path d="M36 43l-3.5-1"/><path d="M64 43l3.5-1"/></g>'
        )
    return ""


def avatar_svg(spec, size=None):
    """spec 하나를 정사각 SVG 문자열로 만든다. 원형 마스킹은 감싸는 요소의
    border-radius 가 담당한다(문서 안에 SVG가 여러 개 들어가므로 clipPath id
    충돌을 피한다). size=None 이면 부모 크기를 채운다."""
    skin = spec.get("skin", "#F0C7A2")
    hair = spec.get("hair", "#2B2118")
    top = spec.get("top", "#28405C")
    bg = spec.get("bg", "#E6EEF7")
    style = spec.get("style", "sidepart")

    dim = f'width="{size}" height="{size}" ' if size else 'width="100%" height="100%" '
    shadow = shade(skin, -0.16)
    collar = shade(top, 0.35)
    lip = shade(skin, -0.42)

    parts = [
        f'<svg {dim}viewBox="0 0 100 100" role="img" aria-hidden="true" '
        'xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100" height="100" fill="{bg}"/>',
        # 어깨 / 옷깃
        f'<path d="M50 66c-16 0-28 9-31 22-1 5-1 9-1 12h64c0-3 0-7-1-12-3-13-15-22-31-22z" fill="{top}"/>',
        f'<path d="M42 68l8 9 8-9c-2-1-5-2-8-2s-6 1-8 2z" fill="{collar}"/>',
        # 목
        f'<path d="M43 56h14v10c0 4-3 6-7 6s-7-2-7-6z" fill="{shadow}"/>',
        # 귀
        f'<ellipse cx="31.5" cy="47" rx="3" ry="4" fill="{skin}"/>',
        f'<ellipse cx="68.5" cy="47" rx="3" ry="4" fill="{skin}"/>',
        # 얼굴
        f'<ellipse cx="50" cy="{HEAD_CY}" rx="19" ry="22" fill="{skin}"/>',
        # 머리
        f'<g fill="{hair}">{HAIR.get(style, HAIR["sidepart"])}</g>',
        # 눈썹
        '<g stroke="%s" stroke-width="1.6" stroke-linecap="round" opacity=".8">'
        '<path d="M38 39.5c2-1.4 5-1.4 7 0"/><path d="M55 39.5c2-1.4 5-1.4 7 0"/></g>'
        % shade(hair, 0.08),
        # 눈
        '<g fill="#2B2118"><ellipse cx="42.5" cy="45" rx="1.9" ry="2.5"/>'
        '<ellipse cx="57.5" cy="45" rx="1.9" ry="2.5"/></g>',
        '<g fill="#FFFFFF" opacity=".85"><circle cx="43.2" cy="44.2" r=".7"/>'
        '<circle cx="58.2" cy="44.2" r=".7"/></g>',
        # 코 / 입
        f'<path d="M50 47.5v3.5c0 .8-.7 1.3-1.6 1.3" fill="none" '
        f'stroke="{shadow}" stroke-width="1.2" stroke-linecap="round"/>',
        f'<path d="M46 55.5c2.4 2 5.6 2 8 0" fill="none" stroke="{lip}" '
        'stroke-width="1.7" stroke-linecap="round"/>',
    ]

    if spec.get("beard"):
        parts.append(
            f'<path d="M34.5 52c1 8 7 15 15.5 15s14.5-7 15.5-15'
            f'c.5 7-1.5 12-5 15.5-6 5-15 5-21 0-3.5-3.5-5.5-8.5-5-15.5z" '
            f'fill="{hair}" opacity=".38"/>'
        )

    parts.append(_glasses(spec.get("glasses", "none")))
    parts.append("</svg>")
    return "".join(parts)
