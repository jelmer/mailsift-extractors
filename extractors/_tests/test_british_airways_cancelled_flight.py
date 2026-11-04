"""Tests for the British Airways cancelled flight extractor."""

from __future__ import annotations

import email
import json
import re
from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = EXTRACTORS_DIR.parent / "tests" / "corpus"

CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}
BA = {"@type": "Airline", "iataCode": "BA", "name": "British Airways"}


def subject_regex() -> re.Pattern[str]:
    manifest = EXTRACTORS_DIR / "british-airways-cancelled-flight.yaml"
    for line in manifest.read_text().splitlines():
        if line.startswith("subject_regex: "):
            return re.compile(json.loads(line.removeprefix("subject_regex: ")))
    raise KeyError("no subject_regex")


def test_manifest_accepts_cancelled_subject():
    with (CORPUS_DIR / "british-airways-flight-cancelled.eml").open("rb") as fh:
        subject = email.message_from_binary_file(fh)["Subject"]
    assert subject_regex().search(subject)


def test_manifest_rejects_disruption_notice():
    # Sent alongside, without any flight details.
    assert not subject_regex().search(
        "A message from British Airways about your flight BA 491 to London Heathrow"
    )


def test_cancelled_flight_and_rebooking(run_extractor):
    out = run_extractor(
        "british-airways-cancelled-flight", "british-airways-flight-cancelled.eml"
    )
    assert out == {
        "ba-CANCEL-BA0491.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "CANCEL",
            "reservationStatus": "ReservationCancelled",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "491",
                "airline": BA,
                "departureAirport": {"@type": "Airport", "name": "Gibraltar"},
                "arrivalAirport": {"@type": "Airport", "name": "London Heathrow"},
                "departureTime": "2042-03-31T15:25:00",
                "arrivalTime": "2042-03-31T17:15:00",
                "pending:cabinClass": "Euro Traveller",
            },
        },
        "ba-CANCEL-BA0493.reservation.json": {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": "CANCEL",
            # Waits for the passenger to accept it.
            "reservationStatus": "ReservationPending",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": "493",
                "airline": BA,
                "departureAirport": {"@type": "Airport", "name": "Gibraltar"},
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": "London Heathrow",
                    "alternateName": "Terminal 3",
                },
                "departureTime": "2042-04-01T11:55:00",
                "arrivalTime": "2042-04-01T13:50:00",
                "pending:cabinClass": "Euro Traveller",
            },
        },
    }
