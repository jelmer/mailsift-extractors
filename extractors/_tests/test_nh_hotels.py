"""Tests for the NH Hotels reservation confirmation extractor."""

from __future__ import annotations


def stay(number: str, checkin: str, checkout: str, street: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": number,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "checkinTime": checkin,
        "checkoutTime": checkout,
        "reservationFor": {
            "@type": "Hotel",
            "name": "NH Example Antwerp",
            "telephone": "+32.30.000001",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": street,
                "addressCountry": "Belgium",
            },
        },
        "underName": {"@type": "Person", "name": "Test User"},
    }


def test_2011_layout(run_extractor):
    # The subject is folded before the reservation number.
    out = run_extractor("nh-hotels", "nh-hotels-2011.eml")
    assert out == {
        "nh-hotels-AAAA000000001.reservation.json": stay(
            "AAAA000000001",
            "2040-02-03",
            "2040-02-05",
            "1 Example Street. 2000 Amberes. Antwerp",
        ),
    }


def test_2015_layout(run_extractor):
    out = run_extractor("nh-hotels", "nh-hotels-2015.eml")
    assert out == {
        "nh-hotels-BBBB000000002.reservation.json": stay(
            "BBBB000000002",
            "2043-01-30",
            "2043-02-01",
            "1 Example Street. 2000 Antwerp",
        ),
    }
