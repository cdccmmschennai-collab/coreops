"""Last-resort redaction for anything that reaches a log line or a console.

The connector holds three secrets: the EasyTime password, the EasyTime JWT and
the CoreOps connector token. None of them is ever passed to a logger on purpose
- but "on purpose" is not a guarantee that survives future edits, and this
connector writes its logs to a directory an operator will happily attach to an
email. So every handler installed by ``logging_setup`` runs its output through
``sanitize_text`` first.

This is the SECOND line of defence, exactly like ``run_probe.ps1``'s regex pass
sits behind ``probe.py``'s own refusal to print secrets. The first line is that
the code never logs the values at all.

Deliberately regex-based and dependency-free: it has to work on a Windows admin
PC with three pip packages installed.
"""
from __future__ import annotations

import re
from typing import Any

# Keys whose VALUE is a secret, in any of the shapes a value gets written in:
#   token=abc   "token": "abc"   token: abc   TOKEN = abc
# [^\S\r\n] is horizontal whitespace only - plain \s would let a match run past
# a line break and swallow the following line (the same bug run_probe.ps1
# guards against).
_KEY_VALUE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|jwt|api[_-]?key|access[_-]?token"
    r"|refresh[_-]?token|authorization|credential)\b"
    r"([\"']?[^\S\r\n]*[:=][^\S\r\n]*[\"']?)"
    r"([^\s\"',;}\]]+)"
)

# "Authorization: JWT eyJ..." / "Bearer abc..." style header values.
_SCHEME_VALUE = re.compile(r"(?i)\b(JWT|Bearer|Token)[^\S\r\n]+([A-Za-z0-9\-._~+/]{12,}=*)")

# A bare JWT anywhere in the text, even without a label in front of it.
_BARE_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*")

# The dedicated CoreOps header name, in case a header dict is ever formatted.
_CONNECTOR_HEADER = re.compile(
    r"(?i)(X-CoreOps-Connector-Token[\"']?[^\S\r\n]*[:=][^\S\r\n]*[\"']?)([^\s\"',;}\]]+)"
)

REDACTED = "<redacted>"

MAX_EXCERPT_CHARS = 500


def sanitize_text(text: str) -> str:
    """Return ``text`` with anything secret-shaped replaced by ``<redacted>``.

    Order matters: the header rule runs first because its key would otherwise
    be matched by the generic `token` rule with a worse capture boundary.
    """
    if not text:
        return text
    text = _CONNECTOR_HEADER.sub(rf"\1{REDACTED}", text)
    text = _KEY_VALUE.sub(rf"\1\2{REDACTED}", text)
    text = _SCHEME_VALUE.sub(rf"\1 {REDACTED}", text)
    text = _BARE_JWT.sub(REDACTED, text)
    return text


def excerpt(value: Any, *, limit: int = MAX_EXCERPT_CHARS) -> str:
    """A short, sanitized, single-paragraph rendering of a response body.

    Used for the evidence kept on a 422: the operator needs to see WHICH field
    CoreOps objected to, without the connector re-printing whatever the server
    chose to echo back.
    """
    text = value if isinstance(value, str) else repr(value)
    text = sanitize_text(text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def contains_secret(text: str, secret: str) -> bool:
    """True when ``secret`` appears verbatim in ``text``.

    Only used by the tests, which assert the negative against real log files.
    A short or empty secret would make the assertion meaningless, so it is
    rejected rather than answered.
    """
    if not secret or len(secret) < 8:
        raise ValueError("contains_secret needs a secret of at least 8 characters.")
    return secret in text
