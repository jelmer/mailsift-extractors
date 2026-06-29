#!/usr/bin/env python3
"""PostNL parcel-tracking emails.

PostNL sends mails throughout a parcel's life from two addresses on the
edm.postnl.nl domain (notificatie@ and noreply@). Subjects encode the
stage in Dutch:

- "Nieuw pakket van <merchant>"           -> incoming, no ETA
- "Verstuurd: je pakket voor <merchant>"  -> shipped, verzendbewijs
- "Onderweg met je pakket van <merchant>" -> out for delivery
- "Afgeleverd: je pakket van <merchant>"  -> delivered

The body always carries the tracking ("Track & trace") code on its own
line. PostNL canonical tracking codes are alphanumeric and start with
3S (e.g. 3SBBBB0000000, 3SCCCC000000000). Most mails are plaintext;
when only HTML is present we strip tags first.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


TRACKING_RE = re.compile(r"\b(3S[A-Z]{2,6}\d{6,12})\b")
SUBJECT_RE = re.compile(
    r"^(?:(Nieuw)\s+pakket\s+van|"
    r"(Verstuurd):\s+je\s+pakket\s+(?:van|voor)|"
    r"(Onderweg)\s+met\s+je\s+pakket\s+van|"
    r"(Afgeleverd):\s+je\s+pakket\s+van)\s+(?P<merchant>.+?)\s*$",
    re.I,
)


STATUS_MAP = {
    "nieuw": "Scheduled",
    "verstuurd": "OnItsWay",
    "onderweg": "OutForDelivery",
    "afgeleverd": "Delivered",
}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    if not subject:
        return 0

    m = SUBJECT_RE.match(subject)
    if not m:
        return 0
    keyword = next(g for g in m.groups()[:4] if g)
    status = STATUS_MAP[keyword.lower()]
    merchant = m.group("merchant").strip()

    body = mail.text
    if not body and mail.html:
        body = strip_html(mail.html)
    if not body:
        return 0

    track_match = TRACKING_RE.search(body)
    if not track_match:
        return 0
    tracking = track_match.group(1)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "deliveryStatus": status,
        "provider": {
            "@type": "Organization",
            "@id": "postnl",
            "name": "PostNL",
        },
        "merchant": {"@type": "Organization", "name": merchant},
    }

    Path(f"postnl-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
