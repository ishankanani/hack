"""Deep links for sharing and invites.

  solution link  https://t.me/<bot>?start=s_<id>_<sig>   QR code on the image + Share button
  invite link    https://t.me/<bot>?start=ref_<user_id>  /invite

The solution link is signed (HMAC) so people can't walk through other students' solutions by
changing the number. Telegram allows up to 64 characters of [A-Za-z0-9_-] after ?start=.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import quote

_SOLUTION = re.compile(r"^s_(\d{1,12})_([0-9a-f]{10})$")
_INVITE = re.compile(r"^ref_(\d{1,15})$")


def _sig(solution_id: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"s{solution_id}".encode(), hashlib.sha256).hexdigest()[:10]


def solution_payload(solution_id: int, secret: str) -> str:
    return f"s_{solution_id}_{_sig(solution_id, secret)}"


def parse_solution(payload: str, secret: str) -> int | None:
    m = _SOLUTION.match(payload or "")
    if not m:
        return None
    sid = int(m.group(1))
    return sid if hmac.compare_digest(m.group(2), _sig(sid, secret)) else None


def parse_invite(payload: str) -> int | None:
    m = _INVITE.match(payload or "")
    return int(m.group(1)) if m else None


def bot_link(bot_username: str, payload: str = "") -> str:
    return f"https://t.me/{bot_username}" + (f"?start={payload}" if payload else "")


def solution_link(bot_username: str, solution_id: int, secret: str) -> str:
    return bot_link(bot_username, solution_payload(solution_id, secret))


def invite_link(bot_username: str, user_id: int) -> str:
    return bot_link(bot_username, f"ref_{user_id}")


def telegram_share_url(link: str, text: str) -> str:
    """Opens Telegram's 'share to a chat' picker."""
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"
