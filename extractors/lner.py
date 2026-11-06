#!/usr/bin/env python3
"""LNER rail booking confirmations.

`noreply@lner.co.uk` sends an HTML mail with the subject `Your
reservation from <from> to <to> is confirmed!` once a booking is
paid. The body contains:

- a `Transaction Reference` (10-char alphanumeric, used as the
  booking reference everywhere else in LNER's system);
- one or more `Journey N - <Outward|Return>` blocks, each with a
  `DD/MM/YYYY` date and a pair of `<station>` / `HH:MM` lines
  (departure then arrival);
- a round-trip ticket is two journeys in one mail.

LNER also ships one or more `eTicket-<ref>-*-STD-*-*.pdf`
attachments - the barcode-bearing paper ticket. We file each as a
`.ticket.pdf`, and emit one `TrainReservation` per journey.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"Transaction Reference\s*-\s*([A-Z0-9]{8,12})")
JOURNEY_RE = re.compile(r"Journey\s+(\d+)\s*-\s*(Outward|Return)", re.IGNORECASE)
DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    text = strip_html(mail.html, block_tags=True)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    ref_match = REFERENCE_RE.search(text)
    if not ref_match:
        return 0
    reference = ref_match.group(1)

    # Split the lines into per-journey blocks so we can parse each
    # independently. The first journey starts at the first "Journey N -"
    # header; subsequent ones at every following header; the first
    # block gets anything before the first header dropped (headers,
    # greeting etc.).
    headers = [i for i, ln in enumerate(lines) if JOURNEY_RE.match(ln)]
    if not headers:
        return 0
    headers.append(len(lines))

    for idx in range(len(headers) - 1):
        start, end = headers[idx], headers[idx + 1]
        header_match = JOURNEY_RE.match(lines[start])
        if header_match is None:
            continue
        direction = header_match.group(2).lower()
        block = lines[start + 1 : end]

        # Find the journey date and the two station/time pairs. The
        # station line is non-numeric; the time line immediately
        # after it is HH:MM. The first of each is departure, the
        # second is arrival.
        journey_date: datetime | None = None
        stops: list[tuple[str, str]] = []  # (station, time)
        for i, line in enumerate(block):
            dm = DATE_RE.match(line)
            if dm and journey_date is None:
                day, month, year = dm.groups()
                try:
                    journey_date = datetime(int(year), int(month), int(day))
                except ValueError:
                    pass
                continue
            if TIME_RE.match(line) and i > 0 and not TIME_RE.match(block[i - 1]):
                prev = block[i - 1]
                if not DATE_RE.match(prev) and prev[:1].isalpha():
                    stops.append((prev, line))

        if journey_date is None or len(stops) < 2:
            continue

        dep_station, dep_time = stops[0]
        arr_station, arr_time = stops[1]

        def combine(d: datetime, hhmm: str) -> str:
            hh, mm = TIME_RE.match(hhmm).groups()  # type: ignore[union-attr]
            return d.replace(hour=int(hh), minute=int(mm)).strftime("%Y-%m-%dT%H:%M:%S")

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": reference,
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "LNER"},
                "departureStation": {
                    "@type": "TrainStation",
                    "name": dep_station,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": arr_station,
                },
                "departureTime": combine(journey_date, dep_time),
                "arrivalTime": combine(journey_date, arr_time),
            },
        }
        slug = f"lner-{reference.lower()}-{direction}"
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False)
        )

    # File every eTicket PDF. LNER names them
    # `eTicket-<ref>-<journey>-STD-<passenger>-<ticket>.pdf`; dedup is
    # by the whole filename so we don't need to be clever here.
    for attachment in mail.attachments:
        if not attachment.looks_like_pdf():
            continue
        filename = attachment.filename or ""
        base = filename.rsplit("/", 1)[-1].removesuffix(".pdf")
        if not base:
            base = f"lner-{reference.lower()}-ticket"
        Path(f"{base.lower()}.ticket.pdf").write_bytes(attachment.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
