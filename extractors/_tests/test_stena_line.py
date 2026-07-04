"""Tests for the Stena Line ferry-booking extractor."""

from __future__ import annotations


def test_eticket_emits_boat_reservation(run_extractor):
    out = run_extractor("stena-line", "stena-line-eticket.eml")
    assert set(out) == {"stena-90000000.reservation.json"}
    res = out["stena-90000000.reservation.json"]
    assert res == {
        "@context": "https://schema.org",
        "@type": "BoatReservation",
        "reservationNumber": "stena-90000000",
        "provider": {"@type": "Organization", "name": "Stena Line"},
        "reservationFor": {
            "@type": "BoatTrip",
            "departureBoatTerminal": {
                "@type": "BoatTerminal",
                "name": "Harwich",
            },
            "arrivalBoatTerminal": {
                "@type": "BoatTerminal",
                "name": "Hook Of Holland",
            },
            "departureTime": "2025-05-10T23:00:00",
            "arrivalTime": "2025-05-11T08:00:00",
            "vehicleName": "Stena Britannica",
        },
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 152.10,
            "priceCurrency": "GBP",
        },
    }
