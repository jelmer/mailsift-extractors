"""Tests for the pre-JSON-LD Airbnb reservation extractor."""

from __future__ import annotations


def test_reservation_confirmed(run_extractor):
    out = run_extractor("airbnb-legacy", "airbnb-legacy-confirmed.eml")
    assert out == {
        "airbnb-TESTAB.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "TESTAB",
            "checkinTime": "2013-03-06",
            "checkoutTime": "2013-03-14",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example room - Battersea",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Road",
                    "addressLocality": "London",
                    "postalCode": "SW11 0AA",
                    "addressCountry": "United Kingdom",
                },
            },
            "underName": {"@type": "Person", "name": "Test"},
        }
    }


def test_shared_itinerary(run_extractor):
    # The address comes from the text part, in full-width digits.
    out = run_extractor("airbnb-legacy", "airbnb-legacy-itinerary.eml")
    assert out == {
        "airbnb-TESTCD.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "TESTCD",
            "checkinTime": "2015-08-08",
            "checkoutTime": "2015-08-12",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example guest room",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 サンプル 101, Kyoto-shi Example-ku",
                    "addressLocality": "Kyoto Prefecture",
                    "postalCode": "605-0000",
                    "addressCountry": "Japan",
                },
            },
            "underName": {"@type": "Person", "name": "Test Friend"},
        }
    }


def test_shared_itinerary_with_hours(run_extractor):
    # The 2017 HTML gives check-in and check-out hours; the address,
    # missing from the HTML, still comes from the text part.
    out = run_extractor("airbnb-legacy", "airbnb-legacy-itinerary-hours.eml")
    assert out == {
        "airbnb-HMTESTCODE.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "HMTESTCODE",
            "checkinTime": "2018-01-14T15:00:00",
            "checkoutTime": "2018-01-26T10:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example family home",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Place",
                    "addressLocality": "Forest Lodge",
                    "addressRegion": "NSW",
                    "postalCode": "2037",
                    "addressCountry": "Australia",
                },
            },
            "underName": {"@type": "Person", "name": "Test Friend"},
        }
    }


def test_billing_receipt(run_extractor):
    out = run_extractor("airbnb-legacy", "airbnb-legacy-billing-receipt.eml")
    assert out == {
        "airbnb-1000000001.receipt.json": {
            "@context": "https://schema.org",
            "@type": "Order",
            "merchant": "Airbnb",
            "orderNumber": "1000000001",
            "priceSpecification": {
                "@type": "PriceSpecification",
                "price": 450.0,
                "priceCurrency": "EUR",
            },
            "confirmationNumber": "TESTAB",
            "orderDate": "2013-03-04",
        }
    }


def test_leaves_json_ld_mail_to_schema_ld(run_extractor):
    out = run_extractor("airbnb-legacy", "airbnb-legacy-ld-json.eml")
    assert out == {}
