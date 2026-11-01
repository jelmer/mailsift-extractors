"""Tests for the pre-JSON-LD Booking.com confirmation extractor."""

from __future__ import annotations


def test_2015_layout(run_extractor):
    # Hotel details first, check-in and check-out as hour windows.
    out = run_extractor("booking-com-legacy", "booking-com-legacy-2015.eml")
    assert out == {
        "booking-com-100000001.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "booking-com-100000001",
            "checkinTime": "2015-01-05T12:00:00",
            "checkoutTime": "2015-01-06T09:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Hostal Puno",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Jr. Ejemplo, 100",
                    "addressLocality": "Puno",
                    "postalCode": "051",
                    "addressCountry": "Peru",
                },
                "telephone": "+51000000000",
            },
            "underName": {
                "@type": "Person",
                "name": "Test User",
                "email": "test@example.org",
            },
        }
    }


def test_2014_layout(run_extractor):
    out = run_extractor("booking-com-legacy", "booking-com-legacy-2014.eml")
    assert out == {
        "booking-com-100000002.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "booking-com-100000002",
            "checkinTime": "2014-03-14T14:00:00",
            "checkoutTime": "2014-03-15T11:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Hotel Kensington",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Street, Kensington and Chelsea",
                    "addressLocality": "London",
                    "postalCode": "SW7 0AA",
                    "addressCountry": "United Kingdom",
                },
                "telephone": "+440000000000",
            },
            "underName": {
                "@type": "Person",
                "name": "Test User",
                "email": "test@example.org",
            },
        }
    }


def test_2013_layout(run_extractor):
    # The guest's email has its own label rather than riding along
    # with "Booked by", and the hours read "after" / "before".
    out = run_extractor("booking-com-legacy", "booking-com-legacy-2013.eml")
    assert out == {
        "booking-com-100000003.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "booking-com-100000003",
            "checkinTime": "2013-01-09T15:00:00",
            "checkoutTime": "2013-01-10T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Guesthouse",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Esimerkkitie 1",
                    "addressLocality": "Kittilä",
                    "postalCode": "99100",
                    "addressCountry": "Finland",
                },
                "telephone": "+358000000000",
            },
            "underName": {
                "@type": "Person",
                "name": "Test User",
                "email": "test@example.org",
            },
        }
    }


def test_region_in_locality(run_extractor):
    out = run_extractor("booking-com-legacy", "booking-com-legacy-region.eml")
    assert out == {
        "booking-com-100000004.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "booking-com-100000004",
            "checkinTime": "2013-10-14T15:00:00",
            "checkoutTime": "2013-10-17T11:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example Inn & Suites",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Road",
                    "addressLocality": "Mountain View",
                    "addressRegion": "California",
                    "postalCode": "CA 94040",
                    "addressCountry": "United States of America",
                },
                "telephone": "+10000000000",
            },
            "underName": {
                "@type": "Person",
                "name": "Test User",
                "email": "test@example.org",
            },
        }
    }


def test_unwrapped_forward_with_local_script_address(run_extractor):
    # What mailsift hands over after unwrapping a Gmail inline forward:
    # the quoted HTML and pseudo-headers. The address is repeated in
    # Thai after the country line.
    out = run_extractor("booking-com-legacy", "booking-com-legacy-forwarded.eml")
    assert out == {
        "booking-com-100000005.reservation.json": {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": "booking-com-100000005",
            "checkinTime": "2013-12-22T14:00:00",
            "checkoutTime": "2013-12-24T12:00:00",
            "reservationFor": {
                "@type": "LodgingBusiness",
                "name": "Example House",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Road, Chanasongkram",
                    "addressLocality": "Bangkok",
                    "postalCode": "10200",
                    "addressCountry": "Thailand",
                },
                "telephone": "+66000000000",
            },
            "underName": {
                "@type": "Person",
                "name": "Test Friend",
                "email": "friend@example.org",
            },
        }
    }


def test_leaves_json_ld_mail_to_schema_ld(run_extractor):
    out = run_extractor("booking-com-legacy", "booking-com-legacy-ld-json.eml")
    assert out == {}
