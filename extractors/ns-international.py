#!/usr/bin/env python3
"""NS International train booking confirmations.

NS International sends booking confirmations from
`no-reply@confirmation.nsinternational.nl`. A booking is almost always
several trains: international trips to France or Germany routinely
chain a Thalys/Eurostar with a local IC, and even domestic-ish
Belgium/Netherlands trips change trains at Antwerpen or Rotterdam.

The mail comes in two shapes:

* **Modern** (Eurostar/ICE/EC on the itinerary). Each train has its own
  block::

      Outward journey
      Sat 19 Jul 2025 Travel time: 08:35
      07:22
      Brest(F)
      Track unknown
      TGV 8606
      11:07
      Paris Montparnasse
      Track unknown
      Transfer 75 min
      12:22
      ...

* **Legacy** (older, or the shorter format still used for domestic-ish
  trips). A summary block gives origin/destination and total travel
  time, followed by a `Routedetails` table with one `V`/`D` (depart)
  and one `A` (arrive) row per stop::

      Outward
      Gent St Pieters - Utrecht Centraal
      Departure: Mon 02 Feb 2026 om 18:27
      Arrival: Mon 02 Feb 2026 om 21:14
      Changes: 2
      Class: Standard Class
      Routedetails
      V | 18:27 | Gent St Pieters
      A | 19:23 | Antwerpen Centraal
      Transfer (12 min.)
      D | 19:35 | Antwerpen Centraal
      A | 20:17 | Rotterdam Centraal
      ...

  Older Dutch mails use `Heenreis`/`Terugreis` and `Overstap` instead
  of the English labels.

Either way we emit one `TrainReservation` per train segment: the
modern format gives us a `trainNumber` and track; the legacy format
gives station names and times only. Downstream sinks key events off
`reservationNumber`, so per-train uniqueness has to be baked in there:
the reservation number is `<booking>-<direction>-<train>` where
`<train>` is the train number (`TGV8606`) when present or the leg
index (`1`, `2`, `3`) when the mail didn't carry one.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_REF_RE = re.compile(r"booking reference:\s*([A-Z0-9]{5,12})", re.IGNORECASE)
# Dutch subjects: `boekingscode: XXXXXXX`.
SUBJECT_REF_NL_RE = re.compile(r"boekingscode:\s*([A-Z0-9]{5,12})", re.IGNORECASE)

# Direction headings. Modern mails use "Outward journey" / "Return
# journey", legacy English mails "Outward" / "Return", Dutch mails
# "Heenreis" / "Terugreis". Match the longer variants first so
# "Outward journey" doesn't get swallowed by the "Outward" prefix.
DIRECTION_RE = re.compile(
    r"^(?P<label>Outward\s+journey|Return\s+journey|Outward|Return|Heenreis|Terugreis)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Modern format: the block opens with a weekday/date line, optionally
# followed by `Travel time: HH:MM` on the same line.
MODERN_DATE_RE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<year>\d{4})"
    r"(?:\s+Travel\s+time:\s*\d{1,2}:\d{2})?\s*$",
    re.MULTILINE,
)

# Modern format: a plain `HH:MM` line.
HHMM_RE = re.compile(r"^(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*$", re.MULTILINE)

# Modern format: `<TYPE> <NUMBER>` — e.g. `TGV 8606`, `EST 9339`,
# `IC 2855`, `ECD 9563`, `ICE 123`. The type is 2-4 uppercase letters;
# the number is 1-5 digits. Track lines (`Track 13`, `Track unknown`)
# start with `Track ` which never matches this shape.
TRAIN_NUMBER_RE = re.compile(r"^(?P<type>[A-Z]{2,4})\s+(?P<num>\d{1,5})\s*$")

# Modern format: `Track 12`, `Track unknown`, or track missing entirely.
TRACK_RE = re.compile(r"^Track\s+(?P<track>.+?)\s*$")

# Modern format: separator between two trains.
TRANSFER_RE = re.compile(r"^Transfer\s+\d+\s+min\s*$", re.IGNORECASE)

# Legacy format: summary lines.
LEGACY_ORIGIN_DEST_RE = re.compile(r"^(?P<origin>.+?)\s+-\s+(?P<dest>.+?)\s*$")
# The summary lines the HTML stripper leaves may collapse the label
# and the date onto one line (`Departure: | Mon 02 Feb 2026 om 18:27`)
# or split them across two (`Departure:\nMon 02 Feb 2026 om 18:27`);
# `\s+` here spans both.
LEGACY_DEP_RE = re.compile(
    r"Departure:\s*\|?\s+"
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|ma|di|wo|do|vr|za|zo)\s+"
    r"(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<year>\d{4})\s+"
    r"(?:om|at)\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})",
    re.IGNORECASE,
)
LEGACY_ARR_RE = re.compile(
    r"Arrival:\s*\|?\s+"
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|ma|di|wo|do|vr|za|zo)\s+"
    r"(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<year>\d{4})\s+"
    r"(?:om|at)\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})",
    re.IGNORECASE,
)
# Dutch: `Vertrek:` and `Aankomst:` with `zo 30 dec 2018 om 09:39`.
LEGACY_DEP_NL_RE = re.compile(
    r"Vertrek:\s*\|?\s+"
    r"(?:ma|di|wo|do|vr|za|zo)\s+"
    r"(?P<day>\d{1,2})\s+(?P<mon>[a-z]{3})\s+(?P<year>\d{4})\s+"
    r"om\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})",
    re.IGNORECASE,
)
LEGACY_ARR_NL_RE = re.compile(
    r"Aankomst:\s*\|?\s+"
    r"(?:ma|di|wo|do|vr|za|zo)\s+"
    r"(?P<day>\d{1,2})\s+(?P<mon>[a-z]{3})\s+(?P<year>\d{4})\s+"
    r"om\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})",
    re.IGNORECASE,
)

CLASS_RE = re.compile(
    r"(?:Class|Comfortklasse):\s*\|?\s*([A-Za-z][A-Za-z ]+?)\s*(?:\||\n|$)",
    re.IGNORECASE,
)

# Legacy Routedetails table. Each stop is a `V`/`D`/`A` marker
# followed by `HH:MM` and a station name. The three cells sometimes
# collapse onto one line separated by pipes (`V | 18:27 | Gent`), and
# sometimes land on three consecutive lines after HTML stripping. The
# parser accepts either shape.
ROUTEDETAILS_HEADER_RE = re.compile(r"^Routedetails\s*$", re.IGNORECASE | re.MULTILINE)
LEGACY_STOP_INLINE_RE = re.compile(
    r"^(?P<kind>[VDA])\s*\|+\s*(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*\|+\s*(?P<station>.+?)\s*(?:\|.*)?$"
)
LEGACY_STOP_MARKER_RE = re.compile(r"^(?P<kind>[VDA])\s*$")
LEGACY_TIME_RE = re.compile(r"^(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*$")
LEGACY_TRANSFER_RE = re.compile(
    r"^(?:Transfer|Overstap)\s*\((?P<mins>\d+)\s*min\.?\)\s*$",
    re.IGNORECASE,
)

# Total price. Rendered as `€ 224,70`, `€60 60` (two adjacent tags
# with a space between them after stripping), or `€6060` (adjacent
# tags with no separator). Each form is a separate alternative with
# its own eur/cent groups; the punctuated form is listed first so it
# wins on ambiguous input.
TOTAL_RE = re.compile(
    r"(?:Total\s+price|Totaalprijs)[:\s|]*"
    r"€\s*"
    r"(?:"
    r"(?P<eur_sep>\d{1,5})[,.](?P<cent_sep>\d{2})(?!\d)"
    r"|(?P<eur_space>\d{1,5})\s+(?P<cent_space>\d{2})(?!\d)"
    r"|(?P<eur_run>\d{1,3})(?P<cent_run>\d{2})(?!\d)"
    r")",
    re.IGNORECASE,
)

# The English months come from strftime %b; the Dutch ones don't align
# with any locale strftime spells reliably, so map them by hand.
DUTCH_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mrt": 3,
    "apr": 4,
    "mei": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "okt": 10,
    "nov": 11,
    "dec": 12,
}


def parse_month(name: str) -> int | None:
    key = name.lower().rstrip(".")
    if key in DUTCH_MONTHS:
        return DUTCH_MONTHS[key]
    for fmt in ("%b", "%B"):
        try:
            return datetime.strptime(key.capitalize(), fmt).month
        except ValueError:
            continue
    return None


def parse_naive_dt(day: str, mon: str, year: str, hh: str, mm: str) -> datetime | None:
    month = parse_month(mon)
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), int(hh), int(mm))
    except ValueError:
        return None


@dataclass
class Segment:
    """One train ride: station-to-station, on one train.

    `train_number` may be missing (the legacy format never carries it);
    downstream falls back to a leg index when composing filenames and
    UIDs.
    """

    origin: str
    destination: str
    departs: datetime
    arrives: datetime
    train_number: str | None = None
    departure_track: str | None = None
    arrival_track: str | None = None


@dataclass
class Direction:
    label: str  # "outward" / "return"
    segments: list[Segment] = field(default_factory=list)
    cabin_class: str | None = None


def normalize_direction(label: str) -> str:
    key = label.lower()
    if key.startswith("outward") or key == "heenreis":
        return "outward"
    if key.startswith("return") or key == "terugreis":
        return "return"
    return key


def split_direction_blocks(text: str) -> list[tuple[str, str]]:
    """Return `(direction, block_text)` pairs in mail order."""
    headers = list(DIRECTION_RE.finditer(text))
    out = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[header.end() : end]
        out.append((normalize_direction(header.group("label")), block))
    return out


def parse_modern_segments(block: str) -> list[Segment]:
    """Parse the per-train modern layout inside one direction block.

    Returns an empty list when the block clearly isn't modern (no
    top-of-block date line); the caller then tries the legacy parser.
    """
    date_match = MODERN_DATE_RE.search(block)
    if not date_match:
        return []
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    # Skip everything up to and including the date line; the segments
    # start on the first `HH:MM` after it.
    start_idx = None
    for idx, line in enumerate(lines):
        if MODERN_DATE_RE.match(line):
            start_idx = idx + 1
            break
    if start_idx is None:
        return []

    day = int(date_match.group("day"))
    year = int(date_match.group("year"))
    month = parse_month(date_match.group("mon"))
    if month is None:
        return []
    base_day = datetime(year, month, day)

    segments: list[Segment] = []
    idx = start_idx
    prev_time: datetime | None = None
    while idx < len(lines):
        line = lines[idx]
        # A `Passengers and seats` / `Tariff` / similar header ends the
        # direction block for practical purposes; anything after is
        # bookkeeping we don't need.
        if line in {"Passengers and seats", "Passengers", "Tariff", "Tariffs"}:
            break
        if TRANSFER_RE.match(line):
            idx += 1
            continue
        # Expect: HH:MM (dep) / station / Track ? / TYPE NUMBER /
        #         HH:MM (arr) / station / Track ?
        dep_match = HHMM_RE.match(line)
        if not dep_match:
            idx += 1
            continue
        if idx + 1 >= len(lines):
            break
        dep_time = _combine_day_and_time(
            base_day, prev_time, int(dep_match.group("hh")), int(dep_match.group("mm"))
        )
        origin = lines[idx + 1]
        cursor = idx + 2
        # Optional `Track X` after the station.
        dep_track = None
        if cursor < len(lines) and (t := TRACK_RE.match(lines[cursor])):
            dep_track = t.group("track")
            cursor += 1
        # Optional train number on its own line.
        train_number = None
        if cursor < len(lines) and (tn := TRAIN_NUMBER_RE.match(lines[cursor])):
            train_number = f"{tn.group('type')}{tn.group('num')}"
            cursor += 1
        # Arrival: another HH:MM line.
        if cursor >= len(lines):
            break
        arr_match = HHMM_RE.match(lines[cursor])
        if not arr_match:
            # Malformed block; skip past this depart line and keep
            # trying.
            idx += 1
            continue
        arr_time = _combine_day_and_time(
            base_day, dep_time, int(arr_match.group("hh")), int(arr_match.group("mm"))
        )
        cursor += 1
        if cursor >= len(lines):
            break
        destination = lines[cursor]
        cursor += 1
        arr_track = None
        if cursor < len(lines) and (t := TRACK_RE.match(lines[cursor])):
            arr_track = t.group("track")
            cursor += 1

        segments.append(
            Segment(
                origin=origin,
                destination=destination,
                departs=dep_time,
                arrives=arr_time,
                train_number=train_number,
                departure_track=_clean_track(dep_track),
                arrival_track=_clean_track(arr_track),
            )
        )
        prev_time = arr_time
        idx = cursor
    return segments


def _combine_day_and_time(
    base_day: datetime,
    prev_time: datetime | None,
    hour: int,
    minute: int,
) -> datetime:
    """Attach `HH:MM` to the running day. Roll over to the next day if
    the running time went backwards (a train that crosses midnight).
    """
    candidate = base_day.replace(hour=hour, minute=minute)
    if prev_time is not None and candidate < prev_time:
        candidate += timedelta(days=1)
    return candidate


def _clean_track(track: str | None) -> str | None:
    if track is None:
        return None
    track = track.strip()
    if not track or track.lower() == "unknown":
        return None
    return track


def parse_legacy_segments(block: str) -> tuple[list[Segment], str | None]:
    """Parse a legacy-format block.

    Legacy mails carry a summary (`Departure:`/`Arrival:` for the whole
    direction) and a `Routedetails` table with per-stop rows. If the
    Routedetails table is present it names each transfer, so we can
    reconstruct segments from it. Without it, we fall back to a single
    segment from the summary.
    """
    origin, destination, summary_dep, summary_arr = _parse_legacy_summary(block)
    cabin = None
    if (m := CLASS_RE.search(block)) is not None:
        cabin = m.group(1).strip()

    # Look for the Routedetails table.
    stops = _parse_routedetails(block, summary_dep or summary_arr)
    if stops:
        return _stops_to_segments(stops), cabin

    # No Routedetails: emit one summary segment.
    if summary_dep and summary_arr and origin and destination:
        return [
            Segment(
                origin=origin,
                destination=destination,
                departs=summary_dep,
                arrives=summary_arr,
            )
        ], cabin
    return [], cabin


def _parse_legacy_summary(
    block: str,
) -> tuple[str | None, str | None, datetime | None, datetime | None]:
    """Extract origin, destination, summary depart+arrive times from a
    legacy direction block. Any of them may come back `None` on a
    partial match; the caller decides whether to fall back to the
    Routedetails table.
    """
    origin: str | None = None
    destination: str | None = None
    for line in [line.strip() for line in block.split("\n") if line.strip()]:
        if LEGACY_ORIGIN_DEST_RE.match(line) and "-" in line:
            # Only accept a station-pair line; skip label lines like
            # `Departure: ...` (they contain a `-` but not as a route
            # separator).
            if ":" in line or "|" in line:
                continue
            m = LEGACY_ORIGIN_DEST_RE.match(line)
            if m:
                origin = m.group("origin").strip()
                destination = m.group("dest").strip()
                break

    dep = _match_date_time([LEGACY_DEP_RE, LEGACY_DEP_NL_RE], block)
    arr = _match_date_time([LEGACY_ARR_RE, LEGACY_ARR_NL_RE], block)
    return origin, destination, dep, arr


def _match_date_time(patterns: list[re.Pattern[str]], block: str) -> datetime | None:
    for pattern in patterns:
        m = pattern.search(block)
        if m:
            return parse_naive_dt(
                m.group("day"),
                m.group("mon"),
                m.group("year"),
                m.group("hh"),
                m.group("mm"),
            )
    return None


def _parse_routedetails(
    block: str, anchor_dt: datetime | None
) -> list[tuple[str, str, datetime]]:
    """Read the `Routedetails` table into `(kind, station, when)` triples.

    `kind` is `V`/`D` for departure or `A` for arrival. `when` carries
    the wall-clock time anchored to the summary's departure date; if
    that anchor is missing the whole table is discarded because we
    can't date the times.

    Accepts either the pipe-separated form (`V | 18:27 | Gent`) or the
    three-line form the HTML stripper leaves when each table cell wraps
    to its own line.
    """
    if anchor_dt is None:
        return []
    header = ROUTEDETAILS_HEADER_RE.search(block)
    if not header:
        return []
    tail = block[header.end() :]
    triples: list[tuple[str, str, datetime]] = []
    running = anchor_dt
    lines = [line.strip() for line in tail.split("\n") if line.strip()]
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stop_match = LEGACY_STOP_INLINE_RE.match(line)
        if stop_match:
            kind = stop_match.group("kind")
            hh = int(stop_match.group("hh"))
            mm = int(stop_match.group("mm"))
            station = stop_match.group("station").strip()
            when = _running_step(running, hh, mm)
            running = when
            triples.append((kind.upper(), station, when))
            idx += 1
            continue
        marker = LEGACY_STOP_MARKER_RE.match(line)
        if marker and idx + 2 < len(lines):
            time_match = LEGACY_TIME_RE.match(lines[idx + 1])
            if time_match:
                station = lines[idx + 2]
                # Discard a follow-up that turned out to be another
                # marker or a transfer: the split-line form always has
                # a real station name in the third slot.
                if not LEGACY_STOP_MARKER_RE.match(
                    station
                ) and not LEGACY_TRANSFER_RE.match(station):
                    hh = int(time_match.group("hh"))
                    mm = int(time_match.group("mm"))
                    when = _running_step(running, hh, mm)
                    running = when
                    triples.append((marker.group("kind").upper(), station, when))
                    idx += 3
                    continue
        if LEGACY_TRANSFER_RE.match(line):
            idx += 1
            continue
        # First non-stop, non-transfer line ends the table.
        if triples:
            break
        idx += 1
    return triples


def _running_step(running: datetime, hour: int, minute: int) -> datetime:
    candidate = running.replace(hour=hour, minute=minute)
    if candidate < running:
        candidate += timedelta(days=1)
    return candidate


def _stops_to_segments(
    stops: list[tuple[str, str, datetime]],
) -> list[Segment]:
    """A well-formed Routedetails table alternates depart/arrive:

        V (or D) ... first depart
        A         ... first arrive
        [transfer skipped]
        D         ... second depart
        A         ... second arrive
        ...

    Walk the list pairing each `V`/`D` row with the next `A` row.
    """
    segments: list[Segment] = []
    idx = 0
    while idx + 1 < len(stops):
        dep_kind, dep_station, dep_when = stops[idx]
        arr_kind, arr_station, arr_when = stops[idx + 1]
        if dep_kind in {"V", "D"} and arr_kind == "A":
            segments.append(
                Segment(
                    origin=dep_station,
                    destination=arr_station,
                    departs=dep_when,
                    arrives=arr_when,
                )
            )
            idx += 2
        else:
            idx += 1
    return segments


def _parse_total(text: str) -> float | None:
    m = TOTAL_RE.search(text)
    if not m:
        return None
    eur = m.group("eur_sep") or m.group("eur_space") or m.group("eur_run")
    cents = m.group("cent_sep") or m.group("cent_space") or m.group("cent_run")
    try:
        return float(f"{eur}.{cents}")
    except ValueError:
        return None


def _leg_key(segment: Segment, index: int) -> str:
    return segment.train_number or str(index + 1)


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    ref_match = SUBJECT_REF_RE.search(mail.subject) or SUBJECT_REF_NL_RE.search(
        mail.subject
    )
    if not ref_match:
        return 0
    booking = ref_match.group(1)

    text = strip_html(mail.html, block_tags=True)
    total_price = _parse_total(text)

    blocks = split_direction_blocks(text)
    if not blocks:
        return 0

    directions: list[Direction] = []
    for label, block in blocks:
        segments = parse_modern_segments(block)
        cabin: str | None = None
        if not segments:
            segments, cabin = parse_legacy_segments(block)
        if segments:
            directions.append(
                Direction(label=label, segments=segments, cabin_class=cabin)
            )

    if not directions:
        return 0

    first_written = True
    for direction in directions:
        for index, segment in enumerate(direction.segments):
            leg_key = _leg_key(segment, index)
            reservation_number = f"{booking}-{direction.label}-{leg_key}"
            trip: dict = {
                "@type": "TrainTrip",
                "provider": {
                    "@type": "Organization",
                    "name": "NS International",
                },
                "departureStation": {
                    "@type": "TrainStation",
                    "name": segment.origin,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": segment.destination,
                },
                "departureTime": segment.departs.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": segment.arrives.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if segment.train_number:
                trip["trainNumber"] = segment.train_number
            if segment.departure_track:
                trip["departurePlatform"] = segment.departure_track
            if segment.arrival_track:
                trip["arrivalPlatform"] = segment.arrival_track
            if direction.cabin_class:
                trip["trainName"] = direction.cabin_class
            reservation: dict = {
                "@context": "https://schema.org",
                "@type": "TrainReservation",
                "reservationNumber": reservation_number,
                "reservationFor": trip,
            }
            # Total price covers the whole booking; attach it to the
            # first train we write so the archive keeps it without
            # double-counting on every leg.
            if total_price is not None and first_written:
                reservation["totalPrice"] = {
                    "@type": "PriceSpecification",
                    "price": total_price,
                    "priceCurrency": "EUR",
                }
                first_written = False
            Path(f"ns-intl-{reservation_number}.reservation.json").write_text(
                json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
