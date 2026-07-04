"""Tests for the British Airways e-ticket extractor."""

from __future__ import annotations


def test_eticket_emits_one_reservation_per_segment(run_extractor):
    out = run_extractor("british-airways", "british-airways-eticket.eml")
    assert set(out) == {
        "ba-BBBBBB-BA0440.reservation.json",
        "ba-BBBBBB-BA0443.reservation.json",
    }

    outbound = out["ba-BBBBBB-BA0440.reservation.json"]
    assert outbound == {
        "@context": "https://schema.org",
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
