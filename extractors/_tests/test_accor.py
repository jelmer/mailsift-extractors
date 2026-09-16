"""Tests for the Accor (ibis, Novotel, Mercure) reservation extractor."""

from __future__ import annotations


def test_reservation_takes_times_from_the_policy_lines(run_extractor):
    # Accor states check-in and check-out only in the policy
    # paragraphs, and the total appears after the nightly rate.
    out = run_extractor("accor", "accor.eml")
    assert set(out) == {"accor-AAAAAAAA.reservation.json"}
    assert out["accor-AAAAAAAA.reservation.json"] == {
        "@context": {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
        },
        "@type": "LodgingReservation",
        "reservationNumber": "accor-AAAAAAAA",
        "checkinTime": "2023-12-01T15:00:00",
        "checkoutTime": "2023-12-03T12:00:00",
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": "ibis budget Alphaville",
        },
        "pending:numAdults": 1,
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 106.20,
            "priceCurrency": "GBP",
        },
    }
