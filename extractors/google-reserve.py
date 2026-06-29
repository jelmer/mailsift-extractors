#!/usr/bin/env python3
"""Reserve with Google restaurant confirmation emails.

Sent from `reserve-noreply@google.com` for bookings made through Google
Maps / Search. The HTML body opens with a schema.org microdata block:

    <div itemscope itemtype=http://schema.org/FoodEstablishmentReservation>
      <meta itemprop=reservationNumber content=0000-0000-0000-0000>
      <meta itemprop=startTime content=2026-04-17T19:45:00+01:00>
      <meta itemprop=endTime content=2026-04-17T21:15:00+01:00>
      <meta itemprop=partySize content=2>
      <div itemprop=reservationFor itemscope itemtype=http://schema.org/FoodEstablishment>
        <meta itemprop=name content="The Example Bistro">
        <div itemprop=address itemscope itemtype=http://schema.org/PostalAddress>
          <meta itemprop=streetAddress content="1 Example Lane">
          <meta itemprop=addressRegion content=England>
          <meta itemprop=postalCode content="EC1A 1AA">
          <meta itemprop=addressCountry content=GB>
        </div>
      </div>

The HTML is mostly well-formed but unquoted attributes and stray control
bytes are common, so we use targeted regex extraction rather than a
full microdata parser.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


META_RE = re.compile(
    # content="..." | content='...' | content=bareword
    r"<meta\s+itemprop=[\"']?(?P<prop>[A-Za-z]+)[\"']?\s+content="
    r"(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))",
    re.I,
)
SCOPE_OPEN_RE = re.compile(
    r"<div\s+[^>]*itemtype=[\"']?http://schema\.org/(?P<type>[A-Za-z]+)",
    re.I,
)


def parse_microdata(body: str) -> dict | None:
    """Pull the first FoodEstablishmentReservation microdata block.

    Walks the body collecting `<meta itemprop=... content=...>` pairs,
    tracking whether we're currently inside `reservationFor` (the
    FoodEstablishment) or its nested `address` (PostalAddress) scope.
    """
    reservation: dict = {}
    venue: dict = {}
    address: dict = {}

    state = "root"  # root | venue | address
    pos = 0
    in_reservation = False

    while pos < len(body):
        scope = SCOPE_OPEN_RE.search(body, pos)
        meta = META_RE.search(body, pos)

        # Whichever comes first.
        if scope and (not meta or scope.start() < meta.start()):
            t = scope.group("type")
            if t == "FoodEstablishmentReservation":
                in_reservation = True
                state = "root"
            elif t == "FoodEstablishment" and in_reservation:
                state = "venue"
            elif t == "PostalAddress" and state == "venue":
                state = "address"
            pos = scope.end()
            continue

        if not meta:
            break

        if in_reservation:
            prop = meta.group("prop")
            raw = meta.group("dq") or meta.group("sq") or meta.group("bare") or ""
            val = html.unescape(raw).strip()
            if state == "root":
                reservation[prop] = val
            elif state == "venue":
                venue[prop] = val
            elif state == "address":
                address[prop] = val
        pos = meta.end()

    if not reservation:
        return None
    if address:
        venue["address"] = address
    if venue:
        reservation["reservationFor"] = venue
    return reservation


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    micro = parse_microdata(mail.html)
    if not micro:
        return 0

    start = micro.get("startTime")
    if not start:
        return 0

    venue = micro.get("reservationFor", {}) or {}
    name = venue.get("name")
    if not name:
        return 0

    addr = venue.get("address") or {}
    address_str = None
    if isinstance(addr, dict):
        parts = [
            addr.get(k)
            for k in (
                "streetAddress",
                "addressLocality",
                "postalCode",
                "addressCountry",
            )
        ]
        address_str = ", ".join(p for p in parts if p) or None

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "FoodEstablishmentReservation",
        "startTime": start,
        "reservationFor": {
            "@type": "FoodEstablishment",
            "name": name,
        },
    }
    if end := micro.get("endTime"):
        reservation["endTime"] = end
    if address_str:
        reservation["reservationFor"]["address"] = address_str
    if party := micro.get("partySize"):
        try:
            reservation["partySize"] = int(party)
        except ValueError:
            pass

    res_id = micro.get("reservationNumber") or micro.get("reservationId")
    if res_id:
        reservation["reservationNumber"] = f"google-reserve-{res_id}"

    slug = (
        re.sub(r"[^A-Za-z0-9_.+-]+", "-", res_id or name).strip("-") or "google-reserve"
    )
    Path(f"google-reserve-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
