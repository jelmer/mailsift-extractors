"""Shared helper for mailsift extractor scripts.

Extractor protocol recap:

- stdin: raw RFC822 message
- cwd: empty per-extractor tempdir
- output: write files into cwd named `<slug>.<kind>.<ext>` where kind is
  one of event, reservation, ticket, parcel, receipt, bill
- exit 0 for normal completion (empty cwd is fine), non-zero for failure

`read_message()` parses stdin and returns a `Mail` object with attribute
access to common fields plus pre-parsed text/html bodies and ld+json
blocks. Extractors in other languages just parse the RFC822 themselves.
"""

from __future__ import annotations

import email
import email.message
import email.policy
import email.utils
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, cast


@dataclass
class Attachment:
    filename: str | None
    mime_type: str
    bytes: bytes
    content_id: str | None


@dataclass
class Mail:
    raw: bytes
    message: email.message.EmailMessage
    from_address: str | None
    from_domain: str | None
    to: list[str]
    subject: str | None
    date: datetime | None
    text: str | None
    html: str | None
    ld_json: list[Any] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def headers(self) -> Mapping[str, str]:
        return cast("Mapping[str, str]", self.message)


def read_message(stream=None) -> Mail:
    """Parse an RFC822 message from the given stream (default sys.stdin.buffer)."""
    if stream is None:
        stream = sys.stdin.buffer
    raw = stream.read()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(msg, email.message.EmailMessage)

    from_address = _parse_address(msg.get("From"))
    from_domain = (
        from_address.split("@", 1)[1].lower()
        if from_address and "@" in from_address
        else None
    )
    to = _parse_address_list(msg.get_all("To") or [])
    subject = msg.get("Subject")
    date = _parse_date(msg.get("Date"))

    text, html, attachments = _walk_parts(msg)
    ld_json = _extract_ld_json(html) if html else []

    return Mail(
        raw=raw,
        message=msg,
        from_address=from_address,
        from_domain=from_domain,
        to=to,
        subject=subject,
        date=date,
        text=text,
        html=html,
        ld_json=ld_json,
        attachments=attachments,
    )


def _parse_address(value: str | None) -> str | None:
    if not value:
        return None
    _, addr = email.utils.parseaddr(value)
    return addr or None


def _parse_address_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for raw in values:
        for _, addr in email.utils.getaddresses([raw]):
            if addr:
                out.append(addr)
    return out


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _walk_parts(
    msg: email.message.EmailMessage,
) -> tuple[str | None, str | None, list[Attachment]]:
    text: str | None = None
    html: str | None = None
    attachments: list[Attachment] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disposition = (part.get_content_disposition() or "").lower()

        if disposition == "attachment":
            attachments.append(_attachment_from(part))
            continue

        if ctype == "text/plain" and text is None:
            text = _decoded_text(part)
        elif ctype == "text/html" and html is None:
            html = _decoded_text(part)
        else:
            # Treat anything else (inline images, calendar parts, etc.)
            # as an attachment so the extractor can see it.
            attachments.append(_attachment_from(part))

    return text, html, attachments


def _decoded_text(part: email.message.EmailMessage) -> str | None:
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return None
        return payload.decode("utf-8", errors="replace")
    if isinstance(content, str):
        return content
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return None


def _attachment_from(part: email.message.EmailMessage) -> Attachment:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        payload = b""
    content_id = part.get("Content-ID")
    if content_id:
        content_id = content_id.strip("<>")
    return Attachment(
        filename=part.get_filename(),
        mime_type=part.get_content_type(),
        bytes=payload,
        content_id=content_id,
    )


def _extract_ld_json(html: str) -> list[Any]:
    """Pull <script type="application/ld+json"> blocks out of an HTML body.

    Uses extruct if available for robustness; falls back to a very small
    regex-based extractor so extractors without extruct still work.
    """
    try:
        import extruct  # type: ignore

        data = extruct.extract(html, syntaxes=["json-ld"])
        return data.get("json-ld", [])
    except ImportError:
        pass

    import re

    blocks: list[Any] = []
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        body = match.group(1).strip()
        if not body:
            continue
        try:
            blocks.append(json.loads(body))
        except json.JSONDecodeError:
            continue
    return blocks
