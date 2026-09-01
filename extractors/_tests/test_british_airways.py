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
