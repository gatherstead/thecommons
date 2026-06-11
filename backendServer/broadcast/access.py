"""Access-code gate.

Codes live in env: BROADCAST_ACCESS_CODES="label1:CODE1,label2:CODE2".
Validated server-side with a constant-time compare. Never log or persist
the code itself — only the resolved label.
"""
import hmac
import os


def _parse_codes(raw: str) -> dict[str, str]:
    codes = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        label, code = pair.split(":", 1)
        if label.strip() and code.strip():
            codes[label.strip()] = code.strip()
    return codes


def resolve_client_label(access_code: str | None) -> str | None:
    """Return the client label for a valid code, else None.

    Compares against every configured code (constant-time per compare) so
    timing does not reveal which labels exist.
    """
    if not access_code or not isinstance(access_code, str):
        return None
    codes = _parse_codes(os.environ.get("BROADCAST_ACCESS_CODES", ""))
    matched = None
    for label, code in codes.items():
        if hmac.compare_digest(code.encode(), access_code.encode()):
            matched = label
    return matched
