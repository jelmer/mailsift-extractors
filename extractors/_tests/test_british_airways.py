"""Tests for the British Airways e-ticket extractor."""

from __future__ import annotations

import email
import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"


def manifest_subject_regex(name: str) -> re.Pattern[str]:
    """Return the compiled `subject_regex:` from an extractor manifest."""
    for line in (EXTRACTORS_DIR / f"{name}.yaml").read_text().splitlines():
        if line.startswith("subject_regex: "):
            # The manifests use double-quoted YAML scalars, whose
            # backslash escapes are a superset of JSON's.
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError(f"{name}.yaml has no subject_regex")


def corpus_subject(eml_name: str) -> str:
    with (CORPUS_DIR / eml_name).open("rb") as fh:
        return email.message_from_binary_file(fh)["Subject"]


def test_eticket_emits_one_reservation_per_segment(run_extractor):
    out = run_extractor("british-airways", "british-airways-eticket.eml")
    assert set(out) == {
        "ba-BBBBBB-BA0440.reservation.json",
        "ba-BBBBBB-BA0443.reservation.json",
    }

    outbound = out["ba-BBBBBB-BA0440.reservation.json"]
    assert outbound == {
        "@context": {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        },
        "@type": "FlightReservation",
        "reservationNumber": "BBBBBB",
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "440",
            "airline": {
                "@type": "Airline",
                "iataCode": "BA",
                "name": "British Airways",
            },
            "departureAirport": {
                "@type": "Airport",
                "name": "Heathrow",
                "address": "London",
                "alternateName": "Terminal 5",
            },
            "arrivalAirport": {
                "@type": "Airport",
                "name": "Amsterdam",
            },
            "departureTime": "2024-06-08T16:15:00",
            "arrivalTime": "2024-06-08T18:35:00",
            "pending:cabinClass": "Euro Traveller",
        },
    }

    inbound = out["ba-BBBBBB-BA0443.reservation.json"]
    assert inbound["reservationFor"]["flightNumber"] == "443"
    assert inbound["reservationFor"]["departureTime"] == "2024-06-16T21:10:00"
    assert inbound["reservationFor"]["arrivalTime"] == "2024-06-16T21:25:00"
    assert inbound["reservationFor"]["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Heathrow",
        "address": "London",
        "alternateName": "Terminal 5",
    }


def test_legacy_eticket_format_still_extracts(run_extractor):
    # Older BA e-tickets (~2013) use a `BA e-ticket receipt` subject
    # and a label/value itinerary block ("Flight number:", "From:",
    # "To:", "Depart:", "Arrive:"). The extractor recognises both
    # subject prefixes and both body layouts.
    out = run_extractor("british-airways", "british-airways-eticket-legacy.eml")
    assert set(out) == {
        "ba-LEGACY-BA2762.reservation.json",
        "ba-LEGACY-BA2759.reservation.json",
    }
    outbound = out["ba-LEGACY-BA2762.reservation.json"]
    assert outbound["reservationNumber"] == "LEGACY"
    for_ = outbound["reservationFor"]
    assert for_["flightNumber"] == "2762"
    assert for_["pending:cabinClass"] == "Euro Traveller"
    assert for_["departureAirport"] == {
        "@type": "Airport",
        "name": "Gatwick",
        "address": "London",
        # Legacy inlines the terminal after the parenthesised city.
        "alternateName": "Terminal N",
    }
    assert for_["arrivalAirport"] == {"@type": "Airport", "name": "Amsterdam"}
    assert for_["departureTime"] == "2013-05-16T16:00:00"
    assert for_["arrivalTime"] == "2013-05-16T18:10:00"

    inbound = out["ba-LEGACY-BA2759.reservation.json"]
    assert inbound["reservationFor"]["flightNumber"] == "2759"
    assert inbound["reservationFor"]["departureAirport"] == {
        "@type": "Airport",
        "name": "Amsterdam",
    }


def test_columnar_eticket_format_extracts(run_extractor):
    # Mid-2010s BA e-tickets carry the itinerary as free-standing
    # `date / time / place / [terminal]` blocks under a bare
    # `BAnnnn` header line, rather than the modern inline
    # `BAnnnn: British Airways | ...` shape. Same booking-reference
    # phrasing, same output.
    out = run_extractor("british-airways", "british-airways-eticket-columnar.eml")
    assert set(out) == {
        "ba-COLUMN-BA0444.reservation.json",
        "ba-COLUMN-BA0443.reservation.json",
    }
    outbound = out["ba-COLUMN-BA0444.reservation.json"]
    for_ = outbound["reservationFor"]
    assert for_["flightNumber"] == "444"
    assert for_["departureAirport"] == {
        "@type": "Airport",
        "name": "Heathrow",
        "address": "London",
        "alternateName": "Terminal 5",
    }
    assert for_["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Amsterdam",
    }
    assert for_["departureTime"] == "2016-06-23T20:05:00"
    assert for_["arrivalTime"] == "2016-06-23T22:20:00"


def test_manifest_accepts_2015_subject():
    # Unsigned 2015 mail already used the `Your e-ticket receipt`
    # subject.
    subject = corpus_subject("british-airways-eticket-2015.eml")
    assert manifest_subject_regex("british-airways").search(subject)


def test_unsigned_2015_mail_extracts(run_extractor):
    out = run_extractor("british-airways", "british-airways-eticket-2015.eml")
    context = {
        "@vocab": "https://schema.org/",
        "pending": "https://pending.schema.org/",
    }
    airline = {"@type": "Airline", "iataCode": "BA", "name": "British Airways"}
    assert out == {
        "ba-YOURTK-BA0632.reservation.json": {
            "@context": context,
            "@type": "FlightReservation",
            "reservationNumber": "YOURTK",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "632",
                "airline": airline,
                "departureAirport": {
                    "@type": "Airport",
                    "name": "Heathrow",
                    "address": "London",
                    # TODO: the text part carries a literal `&nbsp;`
                    # entity that the parser doesn't decode.
                    "alternateName": "&nbsp;- Terminal 5",
                },
                "arrivalAirport": {"@type": "Airport", "name": "Athens"},
                "departureTime": "2015-11-29T11:55:00",
                "arrivalTime": "2015-11-29T17:35:00",
                "pending:cabinClass": "Euro Traveller",
            },
        },
        "ba-YOURTK-BA0633.reservation.json": {
            "@context": context,
            "@type": "FlightReservation",
            "reservationNumber": "YOURTK",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "633",
                "airline": airline,
                "departureAirport": {"@type": "Airport", "name": "Athens"},
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "Heathrow",
                    "address": "London",
                    "alternateName": "Terminal 5",
                },
                "departureTime": "2015-12-06T18:35:00",
                "arrivalTime": "2015-12-06T20:25:00",
                "pending:cabinClass": "Euro Traveller",
            },
        },
    }
