#!/usr/bin/env python3
"""Forward any iCalendar attachment as an `event` artifact.

We match either `text/calendar` (correct) or any attachment whose
filename ends in `.ics`. Some senders (Deutsche Bahn, notably)
mislabel their `.ics` files as `text/plain`; treating the extension
as authoritative still keeps the contract - `ics-passthrough` only
emits what was already a calendar body to the downstream sink, and
the sink is robust to non-VCALENDAR input.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


SAFE_SLUG = re.compile(r"[^A-Za-z0-9_.+-]+")


def slugify(name: str, fallback: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    cleaned = SAFE_SLUG.sub("-", stem).strip("-")
    return cleaned or fallback


def looks_like_calendar(attachment) -> bool:
    if attachment.mime_type == "text/calendar":
        return True
    name = (attachment.filename or "").lower()
    return name.endswith(".ics")


def main() -> int:
    mail = read_message()
    index = 0
    for attachment in mail.attachments:
        if not looks_like_calendar(attachment):
            continue
        slug = slugify(attachment.filename or f"event-{index}", f"event-{index}")
        out = Path(f"{slug}.event.ics")
        # Avoid clobbering if two attachments slug to the same name.
        suffix = 0
        while out.exists():
            suffix += 1
            out = Path(f"{slug}-{suffix}.event.ics")
        out.write_bytes(attachment.bytes)
        index += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
