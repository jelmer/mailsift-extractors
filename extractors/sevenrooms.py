#!/usr/bin/env python3
"""SevenRooms restaurant reservation confirmations.

SevenRooms is a reservation platform behind many independent
restaurants. Every booking email embeds three "add to calendar" links -
Apple, Google, Outlook - that conveniently encode the full reservation
in the query string in UTC. We prefer the Google calendar URL because
its format is the most stable: `dates=YYYYMMDDTHHMMSSZ/YYYYMMDDTHHMMSSZ`.

Subject and human-facing body give us the venue and party size:

    Subject: Your Reservation at <Venue> | <Name> on <DD/MM/YYYY>
    Body:    <Date>\n<N> guests · <HH:MM> - <HH:MM>
             ... Your reservation number is <ID>
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


SUBJECT_VENUE_RE = re.compile(r"Your Reservation at\s+(.+?)\s*\|", re.I)

# google calendar link: encodes UTC dates + venue + description
GOOGLE_CAL_RE = re.compile(
    r"https://calendar\.google\.com/calendar/render\?[^\"'>\s]+",
    re.I,
)

PARTY_RE = re.compile(r"(\d+)\s+guests?\s*[·•|-]\s*(\d{1,2}:\d{2})")
RES_NUMBER_RE = re.compile(r"reservation number is\s+([A-Z0-9]+)", re.I)


def parse_google_cal(url: str) -> dict[str, str]:
    """Pull title/dates/location/details out of a Google calendar URL."""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return {k: v[0] for k, v in q.items()}


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    # We unescape so &amp; in the HTML doesn't break URL parsing.
    body = html.unescape(mail.html)

    cal_match = GOOGLE_CAL_RE.search(body)
    if not cal_match:
        return 0
    params = parse_google_cal(cal_match.group(0))

    dates = params.get("dates", "")
    # Format is "20260417T184500Z/20260417T201500Z".
    if "/" not in dates:
        return 0
    start_s, end_s = dates.split("/", 1)
    try:
        start = datetime.strptime(start_s, "%Y%m%dT%H%M%SZ")
        end = datetime.strptime(end_s, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return 0

    venue = None
    if mail.subject:
        m = SUBJECT_VENUE_RE.search(mail.subject)
        if m:
            venue = m.group(1).strip()
    # Fall back to the "Reservation at <venue>" text the URL puts in the
    # title field.
    if not venue:
        title = params.get("text", "")
        m = re.match(r"Reservation at\s+(.+)", title)
        if m:
            venue = m.group(1).strip()
    if not venue:
        return 0

    location = params.get("location") or None

    # Party size + human reservation id come from the rendered body.
    text_for_extras = re.sub(r"<[^>]+>", " ", body)
    text_for_extras = re.sub(r"\s+", " ", text_for_extras)

    party_size = None
    if (m := PARTY_RE.search(text_for_extras)) is not None:
        party_size = int(m.group(1))

    res_id = None
    if (m := RES_NUMBER_RE.search(text_for_extras)) is not None:
        res_id = m.group(1)

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": venue,
        },
    }
    if location:
        reservation["reservationFor"]["address"] = location
    if party_size is not None:
        reservation["partySize"] = party_size
    if res_id:
        reservation["reservationNumber"] = f"sevenrooms-{res_id}"

    slug_basis = res_id or f"{venue}-{start.strftime('%Y%m%dT%H%M')}"
    slug = re.sub(r"[^A-Za-z0-9_.+-]+", "-", slug_basis).strip("-") or "sevenrooms"
    Path(f"sevenrooms-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
