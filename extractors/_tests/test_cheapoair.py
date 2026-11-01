"""Tests for the CheapOair booking receipt extractor."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"

EXPECTED = {
    "@context": "https://schema.org",
    "@type": "FlightReservation",
    "reservationNumber": "ABCDEF",
    "broker": {"@type": "Organization", "name": "CheapOair"},
    "underName": {"@type": "Person", "name": "Test User"},
    "ticketNumber": "1690000000000",
    "reservationFor": {
        "@type": "Flight",
        "flightNumber": "501",
        "airline": {
            "@type": "Airline",
            "iataCode": "Z8",
            "name": "Linea Aerea Amaszonas",
        },
        "departureAirport": {
            "@type": "Airport",
            "iataCode": "CUZ",
            "address": {"@type": "PostalAddress", "addressLocality": "Cuzco"},
        },
        "arrivalAirport": {
            "@type": "Airport",
            "iataCode": "LPB",
            "address": {"@type": "PostalAddress", "addressLocality": "La Paz"},
        },
        "departureTime": "2015-01-03T10:35:00",
        "arrivalTime": "2015-01-03T12:35:00",
    },
}


def test_eticket(run_extractor):
    out = run_extractor("cheapoair", "cheapoair-eticket.eml")
    assert out == {"cheapoair-10000000-Z8501.reservation.json": EXPECTED}


def test_receipt(run_extractor):
    out = run_extractor("cheapoair", "cheapoair-receipt.eml")
    assert out == {"cheapoair-10000000-Z8501.reservation.json": EXPECTED}


def test_refuses_after_cutoff(tmp_path):
    # The mail is unsigned, so a recent message in the old template is
    # treated as a spoof.
    eml = (CORPUS_DIR / "cheapoair-eticket.eml").read_bytes()
    eml = eml.replace(b"Date: 10 Sep 2014", b"Date: 10 Sep 2024")
    subprocess.run(
        [sys.executable, str(EXTRACTORS_DIR / "cheapoair.py")],
        cwd=tmp_path,
        input=eml,
        check=True,
    )
    assert list(tmp_path.iterdir()) == []
