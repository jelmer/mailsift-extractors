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

`strip_html()` reduces an HTML body to normalised plain text ready for
regex-driven parsing; `normalize_unicode()` applies the same character
cleanups on its own so the same helper is available for extractors that
work off the plain-text body.
"""

from __future__ import annotations

import email
import email.header
import email.message
import email.policy
import email.utils
import json
import re
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, cast


@dataclass
class Attachment:
    filename: str | None
    mime_type: str
    bytes: bytes
    content_id: str | None

    def looks_like_pdf(self) -> bool:
        """True when this attachment's bytes start with `%PDF-` or its
        filename ends in `.pdf`. Vendors sometimes ship PDFs as
        `application/octet-stream`, so a MIME-type check alone is not
        enough.
        """
        name = (self.filename or "").lower()
        return name.endswith(".pdf") or self.bytes.startswith(b"%PDF")


@dataclass
class Mail:
    raw: bytes
    message: email.message.Message
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

    def find_pdf_attachment(self, hint: str | None = None) -> Attachment | None:
        """Return the first PDF attachment, or None.

        When `hint` is given, prefer an attachment whose filename
        contains the hint (case-insensitive) - useful when the mail
        carries several PDFs and only one matches the record we're
        emitting. Falls back to the first PDF regardless.
        """
        pdfs = [a for a in self.attachments if a.looks_like_pdf()]
        if not pdfs:
            return None
        if hint:
            lowered = hint.lower()
            for a in pdfs:
                if lowered in (a.filename or "").lower():
                    return a
        return pdfs[0]


def read_message(stream=None) -> Mail:
    """Parse an RFC822 message from the given stream (default sys.stdin.buffer).

    Uses `compat32` rather than `policy.default` so we get raw header
    strings unconditionally. The strict parser in 3.14 raises on any
    From/To whose display name decodes to CR/LF (a broken encoded-word
    from a real sender), and we only need strings to feed into our own
    address/date parsing anyway.
    """
    if stream is None:
        stream = sys.stdin.buffer
    raw = stream.read()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    from_address = _parse_address(msg.get("From"))
    from_domain = (
        from_address.split("@", 1)[1].lower()
        if from_address and "@" in from_address
        else None
    )
    to = _parse_address_list(msg.get_all("To") or [])
    subject = _decode_header(msg.get("Subject"))
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


def _decode_header(value: str | None) -> str | None:
    """Decode any RFC 2047 encoded-words in a header value to a plain string."""
    if value is None:
        return None
    parts: list[str] = []
    for chunk, encoding in email.header.decode_header(value):
        if isinstance(chunk, bytes):
            # "unknown-8bit" and friends are sentinel labels the parser
            # emits when it can't identify the charset; fall back to utf-8.
            charset = encoding or "utf-8"
            try:
                parts.append(chunk.decode(charset, errors="replace"))
            except LookupError:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


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
    msg: email.message.Message,
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


def _decoded_text(part: email.message.Message) -> str | None:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return None
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _attachment_from(part: email.message.Message) -> Attachment:
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


# HTML block-level tags. When `strip_html(..., block_tags=True)` is
# used, encountering one of these emits a newline so paragraph
# structure survives; the default (collapse-to-spaces) is what the
# regex-driven extractors want.
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)

# Zero-width and formatting-only characters that some senders (Gmail's
# marketing/preheader tricks in particular) sprinkle through prose and
# that then defeat literal regex matches. Stripped unconditionally.
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")

# Characters we replace with an ordinary space so word-boundary regexes
# match. Non-breaking space is the big one; the narrow / hair space
# variants show up in currency formatting.
_SPACE_LIKE = re.compile("[\u00a0\u2009\u200a\u202f\u205f]")

# Soft hyphen is a hint for line-breaking; the display renders as
# nothing, so treat it that way.
_SOFT_HYPHEN = "\u00ad"


def normalize_unicode(text: str) -> str:
    """Apply the character cleanups every extractor wants: NFKC
    canonicalisation, drop zero-width / formatting-only code points,
    replace non-breaking / thin spaces with ordinary space, drop soft
    hyphens.

    Idempotent and cheap; safe to call on already-normalised text.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(_SOFT_HYPHEN, "")
    text = _ZERO_WIDTH.sub("", text)
    text = _SPACE_LIKE.sub(" ", text)
    return text


class _HtmlToText(HTMLParser):
    def __init__(self, *, block_tags: bool) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._block_tags = block_tags

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip_depth += 1
            return
        if self._block_tags and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # `<br/>` and friends: block-level whether or not `block_tags`
        # is set, since a self-closing block always represents a break.
        if self._block_tags and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def result(self) -> str:
        return "".join(self._parts)


def strip_html(html: str, *, block_tags: bool = False) -> str:
    """Reduce an HTML body to plain text ready for regex parsing.

    `<style>` and `<script>` blocks are dropped, HTML entities are
    decoded, and the output is Unicode-normalised via
    [`normalize_unicode`]. Whitespace is collapsed:

    - `block_tags=False` (default): every run of whitespace becomes a
      single space. Right for extractors that grep the body as one
      long string.
    - `block_tags=True`: block-level tags (`<p>`, `<div>`, `<br>`,
      `<tr>`, `<li>`, ...) insert a newline, and blank lines are
      preserved between paragraphs. Right for extractors that walk the
      body line by line.
    """
    parser = _HtmlToText(block_tags=block_tags)
    parser.feed(html)
    text = normalize_unicode(parser.result())
    if block_tags:
        # Collapse runs of spaces/tabs within a line, then collapse
        # runs of blank lines to a single blank so paragraph breaks
        # stay visible.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    return re.sub(r"\s+", " ", text).strip()


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
