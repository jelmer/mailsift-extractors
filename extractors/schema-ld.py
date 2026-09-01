#!/usr/bin/env python3
"""Generic schema.org ld+json reservation extractor.

The HTML body of many reservation confirmations carries a
`<script type="application/ld+json">` block describing the booking in
schema.org form. We dump every block we recognise as a reservation -
the Rust side handles the conversion to iCalendar.

Recognised types match the converter in src/targets/reservation.rs:
FlightReservation, TrainReservation, BusReservation,
LodgingReservation, EventReservation, FoodEstablishmentReservation.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

SUPPORTED_TYPES = {
    "FlightReservation",
    "TrainReservation",
    "BusReservation",
    "LodgingReservation",
    "EventReservation",
    "FoodEstablishmentReservation",
}

SLUG_RE = re.compile(r"[^A-Za-z0-9_.+-]+")

# Value looks like a date-time (as opposed to a bare Date) when it
# carries a time component after the day. Bare dates are left untouched
# so a genuinely date-typed field (schema.org Date, e.g. a `birthDate`)
# doesn't get promoted to a spurious midnight timestamp.
_HAS_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def canonical_datetime(value: str) -> str:
    """Return `value` as a canonical ISO-8601 string, or unchanged.

    Handles the non-canonical shapes vendors emit (space separator,
    offset without a colon, trailing `Z`). If `value` isn't a
    recognisable date-time it is returned untouched so genuinely odd
    strings still surface to the converter rather than being swallowed.
    """
    if not _HAS_TIME_RE.match(value):
        return value
    candidate = value
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return value
    return parsed.isoformat()


def normalise_datetimes(obj: Any) -> Any:
    """Recursively canonicalise any string that looks like a date-time.

    Key-driven normalisation (a fixed set of DateTime-typed field names)
    misses vendors that put a full timestamp in a schema.org `Date`
    field like `startDate` or `endDate`. Value-driven normalisation
    catches those without needing a list per vendor: bare Dates fail
    the time-component check in `canonical_datetime` and pass through
    untouched.
    """
    if isinstance(obj, dict):
        return {k: normalise_datetimes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalise_datetimes(v) for v in obj]
    if isinstance(obj, str):
        return canonical_datetime(obj)
    return obj


def walk_objects(obj: Any) -> Iterable[dict[str, Any]]:
    """Yield every dict found anywhere in `obj` (depth-first)."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_objects(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_objects(v)


def slugify(value: str, fallback: str) -> str:
    cleaned = SLUG_RE.sub("-", value).strip("-")
    return cleaned or fallback


def flatten(blocks: Iterable[Any]) -> Iterable[dict[str, Any]]:
    """Yield individual reservation-ish dicts from a list of ld+json blocks.

    ld+json blocks come in a few shapes: a single object, an array of
    objects, or a wrapper with a `@graph` array.
    """
    for block in blocks:
        if isinstance(block, list):
            yield from flatten(block)
        elif isinstance(block, dict):
            if "@graph" in block and isinstance(block["@graph"], list):
                yield from flatten(block["@graph"])
            else:
                yield block


def type_of(obj: dict[str, Any]) -> str | None:
    t = obj.get("@type")
    if isinstance(t, list):
        return t[0] if t else None
    return t


def emit_subscriptions(blocks: Iterable[Any]) -> None:
    """Walk every dict and emit a `.subscription.json` for each one
    carrying a `subscriptionDuration` field.

    Schema.org typically nests this inside `Order.acceptedOffer.Offer`
    (or similar), so walking the whole tree is simpler than chasing
    every container shape.
    """
    seen: set[str] = set()
    index = 0
    for obj in walk_objects(blocks):
        duration = obj.get("subscriptionDuration")
        if not isinstance(duration, str) or not duration:
            continue

        provider = obj.get("provider")
        provider_name = provider.get("name") if isinstance(provider, dict) else provider
        name = obj.get("name") or provider_name or str(index)
        if not isinstance(name, str):
            name = str(name)

        slug = slugify(name, fallback=f"subscription-{index}")
        if slug in seen:
            # Same subscription identified twice in one message - skip
            # the duplicate rather than file two records under the
            # same slug.
            continue
        seen.add(slug)
        out = Path(f"{slug}.subscription.json")
        out.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        index += 1


def main() -> int:
    mail = read_message()
    if not mail.ld_json:
        return 0

    index = 0
    for obj in flatten(mail.ld_json):
        if not isinstance(obj, dict):
            continue
        if type_of(obj) not in SUPPORTED_TYPES:
            continue

        identifier = (
            obj.get("reservationNumber")
            or obj.get("reservationId")
            or obj.get("identifier")
            or str(index)
        )
        slug = slugify(str(identifier), fallback=f"reservation-{index}")
        out = Path(f"{slug}.reservation.json")
        suffix = 0
        while out.exists():
            suffix += 1
            out = Path(f"{slug}-{suffix}.reservation.json")
        out.write_text(
            json.dumps(normalise_datetimes(obj), ensure_ascii=False),
            encoding="utf-8",
        )
        index += 1

    emit_subscriptions(mail.ld_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
