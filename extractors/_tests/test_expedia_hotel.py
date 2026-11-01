"""Tests for the 2011 Expedia.co.uk hotel confirmation extractor."""

from __future__ import annotations


def test_hotel_confirmation(run_extractor):
    out = run_extractor("expedia-hotel", "expedia-hotel-2011.eml")
    assert out == {
        "expedia-hotel-10000000001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "expedia-10000000001",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "Expedia"},
            "checkinTime": "2039-05-22",
            "checkoutTime": "2039-05-23",
            "reservationFor": {
                "@type": "Hotel",
                "name": "Example Luton Hotel",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Road",
                    "addressCountry": "United Kingdom",
                    "addressLocality": "Luton",
                    "addressRegion": "Bedfordshire",
                    "postalCode": "LU2 9AA",
                },
                "telephone": "44 (01) 582000001",
            },
            "underName": {"@type": "Person", "name": "Test User"},
        },
    }
