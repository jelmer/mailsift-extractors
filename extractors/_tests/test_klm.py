"""Tests for the KLM booking-confirmation extractor."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"


def run_on_bytes(extractor: str, eml: bytes, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXTRACTORS_DIR / f"{extractor}.py")],
        cwd=cwd,
        input=eml,
        capture_output=True,
        check=False,
    )


def test_two_segment_booking_emits_two_reservations(run_extractor):
    out = run_extractor("klm", "klm-confirmation.eml")
    assert set(out) == {
        "klm-P00000-KL1000.reservation.json",
        "klm-P00000-KL0605.reservation.json",
    }
    leg1 = out["klm-P00000-KL1000.reservation.json"]
    assert leg1["reservationNumber"] == "P00000"
    assert leg1["reservationFor"]["flightNumber"] == "1000"
    assert leg1["reservationFor"]["departureTime"] == "2019-02-19T06:30:00"
    assert leg1["reservationFor"]["arrivalTime"] == "2019-02-19T09:00:00"
    assert leg1["reservationFor"]["departureAirport"] == {
        "@type": "Airport",
        "name": "Heathrow Airport",
        "address": "London",
    }
    assert leg1["reservationFor"]["arrivalAirport"] == {
        "@type": "Airport",
        "name": "Schiphol",
        "address": "Amsterdam",
    }

    assert leg1["reservationFor"]["pending:cabinClass"] == "Business"
    assert leg1["@context"] == {
        "@vocab": "https://schema.org/",
        "pending": "https://pending.schema.org/",
    }

    leg2 = out["klm-P00000-KL0605.reservation.json"]
    assert leg2["reservationFor"]["flightNumber"] == "605"
    assert leg2["reservationFor"]["departureTime"] == "2019-02-19T10:25:00"
    assert leg2["reservationFor"]["arrivalTime"] == "2019-02-19T12:25:00"
    assert leg2["reservationFor"]["arrivalAirport"]["name"] == ("San Francisco Intl.")
    assert leg2["reservationFor"]["pending:cabinClass"] == "World Business Class"


EXPECTED_2014 = {
    "klm-L00000-KL0743.reservation.json": {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "L00000",
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "743",
            "airline": {
                "@type": "Airline",
                "iataCode": "KL",
                "name": "KLM Royal Dutch Airlines",
            },
            "departureAirport": {
                "@type": "Airport",
                "name": "Schiphol",
                "address": "Amsterdam",
            },
            "arrivalAirport": {
                "@type": "Airport",
                "name": "J Chavez International",
                "address": "Lima",
            },
            "departureTime": "2014-12-01T12:25:00",
            "arrivalTime": "2014-12-01T19:15:00",
        },
    },
    "klm-L00000-KL0744.reservation.json": {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "L00000",
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "744",
            "airline": {
                "@type": "Airline",
                "iataCode": "KL",
                "name": "KLM Royal Dutch Airlines",
            },
            "departureAirport": {
                "@type": "Airport",
                "name": "J Chavez International",
                "address": "Lima",
            },
            "arrivalAirport": {
                "@type": "Airport",
                "name": "Schiphol",
                "address": "Amsterdam",
            },
            "departureTime": "2014-12-15T21:15:00",
            "arrivalTime": "2014-12-16T15:30:00",
        },
    },
}


def test_split_time_and_airport_lines(run_extractor):
    # The 2012-2019 templates break the time, city and airport onto
    # separate lines inside one table cell.
    out = run_extractor("klm", "klm-confirmation-2014.eml")
    assert out == EXPECTED_2014


def test_malformed_segment_raises_layout_error(tmp_path):
    # A segment whose departure date is missing must fail loudly
    # rather than be read with the wrong lines in the wrong slots.
    eml = (CORPUS_DIR / "klm-confirmation.eml").read_bytes()
    eml = eml.replace(b"<p>Tue 19 Feb 19</p>\n<p>06:30", b"<p>06:30", 1)
    result = run_on_bytes("klm", eml, tmp_path)
    assert result.returncode != 0
    assert result.stderr.decode().splitlines()[-1] == (
        "LayoutError: expected departure date before 'Flight number: KL 1000', "
        "found 'Departure: London - San Francisco'"
    )
