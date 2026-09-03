"""Tests for the easyJet flight-confirmation extractor.

One mail can carry multiple legs; each leg becomes its own
FlightReservation file keyed off booking ref + flight number.
"""

from __future__ import annotations


def test_two_legs_one_per_file(run_extractor):
    out = run_extractor("easyjet", "easyjet-confirmation.eml")
    assert set(out) == {
        "easyjet-abcdefg-ezy2512.reservation.json",
        "easyjet-abcdefg-ezy2521.reservation.json",
    }
    assert out["easyjet-abcdefg-ezy2521.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "easyjet-ABCDEFG-EZY2521",
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "2521",
            "airline": {"@type": "Airline", "iataCode": "EZY"},
            "departureAirport": {"@type": "Airport", "name": "London Luton"},
            "arrivalAirport": {"@type": "Airport", "name": "Amsterdam"},
            "departureTime": "2024-07-12T18:45:00",
            "arrivalTime": "2024-07-12T20:55:00",
        },
    }
    assert (
        out["easyjet-abcdefg-ezy2512.reservation.json"]["reservationFor"][
            "departureAirport"
        ]["name"]
        == "Amsterdam"
    )
    assert (
        out["easyjet-abcdefg-ezy2512.reservation.json"]["reservationFor"][
            "arrivalAirport"
        ]["name"]
        == "London Luton"
    )


def test_legacy_body_extracts_two_legs(run_extractor):
    # Pre-2014 easyJet mail uses `<Origin> to <Destination> / Dep /
    # Arr / Flight <num>` per leg (no `N of M`, no `EZY` prefix on
    # the flight number, dates spelled out). Same extractor
    # recognises the layout by finding each `Dep <date>` marker
    # and reading the origin/destination pair immediately before
    # it.
    out = run_extractor("easyjet", "easyjet-legacy-confirmation.eml")
    assert set(out) == {
        "easyjet-leg2013-ezy2152.reservation.json",
        "easyjet-leg2013-ezy2163.reservation.json",
    }
    outbound = out["easyjet-leg2013-ezy2163.reservation.json"]
    for_ = outbound["reservationFor"]
    assert for_["flightNumber"] == "2163"
    assert for_["departureAirport"]["name"] == "London Luton"
    assert for_["arrivalAirport"]["name"] == "Amsterdam"
    assert for_["departureTime"] == "2013-10-25T18:55:00"
    inbound = out["easyjet-leg2013-ezy2152.reservation.json"]
    # Passenger name above the itinerary must not leak into origin.
    assert inbound["reservationFor"]["departureAirport"]["name"] == "Amsterdam"


def test_legacy_extractor_extracts_pre_cutoff(run_extractor):
    # `easyjet-legacy` reuses the same parser but with no DKIM
    # requirement, gated by a message-date cutoff (2015-01-01).
    # Same fixture that the main extractor accepts.
    out = run_extractor("easyjet-legacy", "easyjet-legacy-confirmation.eml")
    assert "easyjet-leg2013-ezy2163.reservation.json" in out


def test_legacy_extractor_refuses_post_cutoff(run_extractor):
    # Modern fixture is dated 2024; the legacy extractor must
    # reject it even though the parser would otherwise match.
    out = run_extractor("easyjet-legacy", "easyjet-confirmation.eml")
    assert out == {}
