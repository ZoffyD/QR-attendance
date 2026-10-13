import secrets

import segno

PREFIX = "ATT1:"


def new_qr_token() -> str:
    return secrets.token_urlsafe(12)


def qr_svg(token: str, scale: int = 8) -> str:
    return segno.make(PREFIX + token, error="m").svg_inline(scale=scale, border=2, dark="#000")


def token_from_code(code: str) -> str:
    code = (code or "").strip()
    return code[len(PREFIX):] if code.startswith(PREFIX) else code
