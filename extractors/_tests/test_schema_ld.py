"""Tests for the generic schema.org ld+json extractor.

The schema-ld extractor doesn't massage the JSON - it dumps each
recognised reservation object as a `.reservation.json` straight from
the HTML body's ld+json blocks. The Rust converter handles iCalendar
rendering from there.
"""

from __future__ import annotations


def test_flight_reservation_passthrough(run_extractor):
    out = run_extractor("schema-ld", "schema-flight.eml")
    assert set(out) == {"FR1234-ABC123.reservation.json"}
    assert out["FR1234-ABC123.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": "FR1234-ABC123",
        "underName": {"@type": "Person", "name": "Test"},
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": "1234",
            "airline": {"@type": "Airline", "name": "Ryanair", "iataCode": "FR"},
            "departureAirport": {
                "@type": "Airport",
                "iataCode": "DUB",
                "name": "Dublin",
            },
            "arrivalAirport": {
                "@type": "Airport",
                "iataCode": "BCN",
                "name": "Barcelona",
            },
            "departureTime": "2026-07-20T18:00:00+00:00",
            "arrivalTime": "2026-07-20T22:00:00+02:00",
        },
    }


def test_trainline_train_reservation_passthrough(run_extractor):
    # The Trainline booking confirmation already carries a
    # `TrainReservation` ld+json block. No vendor extractor needed -
    # the generic schema-ld pass picks it up unchanged.
    out = run_extractor("schema-ld", "trainline-confirmation.eml")
    assert set(out) == {"700000000000.reservation.json"}
    res = out["700000000000.reservation.json"]
    assert res["@type"] == "TrainReservation"
    assert res["reservationNumber"] == "700000000000"
    assert res["reservationFor"]["departureStation"]["name"] == (
        "London St Pancras International"
    )
    assert res["reservationFor"]["arrivalStation"]["name"] == ("Ashford International")
    assert res["reservationFor"]["departureTime"] == "2026-03-15T10:40:00+00:00"
    assert res["reservationFor"]["arrivalTime"] == "2026-03-15T11:19:00+00:00"


def test_subscription_offer_emitted(run_extractor):
    # An `Order` confirmation carrying an `Offer` with a
    # `subscriptionDuration` triggers a `.subscription.json` artifact
    # alongside any reservations.
    out = run_extractor("schema-ld", "schema-subscription.eml")
    assert set(out) == {"StreamingCo-Standard.subscription.json"}
    sub = out["StreamingCo-Standard.subscription.json"]
    assert sub["subscriptionDuration"] == "P1M"
    assert sub["name"] == "StreamingCo Standard"
    assert sub["price"] == "9.99"


def test_renfe_multi_leg_train_reservation_passthrough(run_extractor):
    # Renfe's "Confirmacion de venta" mail carries one
    # `TrainReservation` ld+json per leg, sharing a single
    # `reservationNumber`. schema-ld de-duplicates by appending a
    # suffix when the slug collides.
    out = run_extractor("schema-ld", "renfe-confirmation.eml")
    assert set(out) == {
        "FFFFFF.reservation.json",
        "FFFFFF-1.reservation.json",
    }
    first_leg = out["FFFFFF.reservation.json"]
    second_leg = out["FFFFFF-1.reservation.json"]
    assert first_leg["reservationFor"]["trainNumber"] == "00621"
    assert first_leg["reservationFor"]["departureStation"]["name"] == "VIGO URZAIZ"
    assert second_leg["reservationFor"]["trainNumber"] == "00282"
    assert (
        second_leg["reservationFor"]["arrivalStation"]["name"]
        == "SAN SEBASTIAN-DONOSTIA"
    )
