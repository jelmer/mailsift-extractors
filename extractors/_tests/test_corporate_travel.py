"""Tests for the CWT and Concur itinerary extractors."""

from __future__ import annotations

CONFIRMED = "https://schema.org/ReservationConfirmed"
TRAVELLER = {"@type": "Person", "name": "Test User"}


def flight(
    number: str,
    airline: dict,
    origin: str,
    destination: str,
    departs: str,
    arrives: str,
) -> dict:
    return {
        "@type": "Flight",
        "flightNumber": number,
        "airline": {"@type": "Airline", **airline},
        "departureAirport": {"@type": "Airport", "iataCode": origin},
        "arrivalAirport": {"@type": "Airport", "iataCode": destination},
        "departureTime": departs,
        "arrivalTime": arrives,
    }


def reservation(locator: str, broker: str, segment: dict, **extra) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": locator,
        "reservationStatus": CONFIRMED,
        "broker": {"@type": "Organization", "name": broker},
        "reservationFor": segment,
        "underName": TRAVELLER,
        **extra,
    }


def test_cwt_travel_documents_with_hotel(run_extractor):
    out = run_extractor("cwt", "cwt-travel-documents-2040.eml")
    iberia = {"iataCode": "IB", "name": "Iberia"}
    ticket = {"ticketNumber": "0750000000002"}
    assert out == {
        "cwt-CCCCCC-20400815-MAD.reservation.json": reservation(
            "CCCCCC",
            "CWT",
            flight(
                "3170",
                iberia,
                "MAD",
                "LIS",
                "2040-08-15T10:05:00",
                "2040-08-15T11:25:00",
            ),
            **ticket,
        ),
        "cwt-CCCCCC-20400816-LIS.reservation.json": reservation(
            "CCCCCC",
            "CWT",
            flight(
                "3171",
                iberia,
                "LIS",
                "MAD",
                "2040-08-16T18:40:00",
                "2040-08-16T21:00:00",
            ),
            **ticket,
        ),
        "cwt-CCCCCC-HTL0000001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "checkinTime": "2040-08-15",
            "checkoutTime": "2040-08-16",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Hotel Lisbon",
                "address": "1 Example Street Lisbon 1000 Pt",
            },
            "reservationNumber": "HTL0000001",
            "reservationStatus": CONFIRMED,
            "broker": {"@type": "Organization", "name": "CWT"},
            "underName": TRAVELLER,
        },
    }


def test_concur_itinerary(run_extractor):
    out = run_extractor("concur", "concur-itinerary.eml")
    air_canada = {"name": "Air Canada"}
    assert out == {
        "concur-EEEEEE-20460914-MAD.reservation.json": reservation(
            "EEEEEE",
            "Concur",
            flight(
                "837",
                air_canada,
                "MAD",
                "YUL",
                "2046-09-14T11:40:00",
                "2046-09-14T13:50:00",
            ),
        ),
        # "This flight leaves on Sep 27 and arrives on Sep 28."
        "concur-EEEEEE-20460927-YUL.reservation.json": reservation(
            "EEEEEE",
            "Concur",
            flight(
                "836",
                air_canada,
                "YUL",
                "MAD",
                "2046-09-27T18:15:00",
                "2046-09-28T07:40:00",
            ),
        ),
    }
