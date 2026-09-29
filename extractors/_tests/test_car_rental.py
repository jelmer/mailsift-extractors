"""Tests for the car rental extractors (Hertz, Avis, National, Alamo)."""

from __future__ import annotations


def test_hertz_single_branch_hire(run_extractor):
    out = run_extractor("hertz", "hertz-reservation.eml")
    assert set(out) == {"hertz-h0000000000.reservation.json"}
    assert out["hertz-h0000000000.reservation.json"] == {
        "@context": "https://schema.org",
        "@type": "RentalCarReservation",
        "reservationNumber": "H0000000000",
        "provider": {"@type": "Organization", "name": "Hertz"},
        "pickupTime": "2026-03-13T18:00:00",
        "dropoffTime": "2026-03-22T18:00:00",
        "pickupLocation": {
            "@type": "Place",
            "name": "Example City - Airport",
            "address": "1 Example Drive",
        },
        "reservationFor": {"@type": "Car", "name": "Economy"},
        "totalPrice": {
            "@type": "PriceSpecification",
            "price": 100.00,
            "priceCurrency": "USD",
        },
    }


def test_avis_one_way_keeps_both_branches(run_extractor):
    out = run_extractor("avis", "avis-reservation.eml")
    assert set(out) == {"avis-00000000gb0.reservation.json"}
    reservation = out["avis-00000000gb0.reservation.json"]
    assert reservation["reservationNumber"] == "00000000GB0"
    # Avis writes 12-hour times; noon must not become midnight.
    assert reservation["pickupTime"] == "2026-07-10T12:00:00"
    assert reservation["dropoffTime"] == "2026-07-17T12:00:00"
    assert reservation["pickupLocation"] == {
        "@type": "Place",
        "name": "Example Intl Airport,EXA",
    }
    assert reservation["dropoffLocation"] == {
        "@type": "Place",
        "name": "Sample Airport,SMP",
    }
    assert reservation["totalPrice"] == {
        "@type": "PriceSpecification",
        "price": 100.00,
    }


def test_nationalcar_converts_pm_times(run_extractor):
    out = run_extractor("nationalcar", "nationalcar-reservation.eml")
    assert set(out) == {"nationalcar-0000000000.reservation.json"}
    reservation = out["nationalcar-0000000000.reservation.json"]
    assert reservation["reservationNumber"] == "0000000000"
    assert reservation["provider"] == {
        "@type": "Organization",
        "name": "National Car Rental",
    }
    assert reservation["pickupTime"] == "2026-08-29T19:00:00"
    assert reservation["dropoffTime"] == "2026-09-10T23:00:00"
    assert reservation["reservationFor"] == {
        "@type": "Car",
        "name": "Midsize Hyundai Elantra",
    }


def test_alamo_keeps_only_the_booking_specific_pdf(run_extractor):
    # Every Alamo mail also carries generic terms PDFs; those are not
    # about this booking and must not be filed. One receipt JSON is
    # written per booking-specific PDF so mailsift's pair invariant
    # holds (blob must have a same-slug JSON sibling).
    out = run_extractor("alamo", "alamo-confirmation.eml")
    assert set(out) == {
        "alamo-200000000-factuur.receipt.json",
        "alamo-200000000-factuur.receipt.pdf",
    }
    assert out["alamo-200000000-factuur.receipt.json"] == {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Alamo",
        "orderNumber": "200000000-factuur",
        "orderDate": "2026-10-21",
    }
    assert out["alamo-200000000-factuur.receipt.pdf"].startswith(b"%PDF")
