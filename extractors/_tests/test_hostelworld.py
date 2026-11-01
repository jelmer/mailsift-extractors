"""Tests for the Hostelworld booking confirmation extractor."""

from __future__ import annotations

LEIPZIG = {
    "@type": "Hostel",
    "name": "Example Hostel Leipzig",
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "Beispielstraße 1",
        "addressLocality": "Leipzig",
        "addressCountry": "Germany",
    },
    "telephone": "+49 341 000 000 40",
}


def stay(reference: str, checkin: str, checkout: str, hostel: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"hostelworld-{reference}",
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "broker": {"@type": "Organization", "name": "Hostelworld"},
        "checkinTime": checkin,
        "checkoutTime": checkout,
        "reservationFor": hostel,
    }


def test_nights_with_a_gap_become_two_stays(run_extractor):
    # 26-29 December, then 31 December: the 30th isn't booked.
    out = run_extractor("hostelworld", "hostelworld-confirmation.eml")
    assert out == {
        "hostelworld-11286-00000001-1.reservation.json": stay(
            "11286-00000001", "2039-12-26", "2039-12-30", LEIPZIG
        ),
        "hostelworld-11286-00000001-2.reservation.json": stay(
            "11286-00000001", "2039-12-31", "2040-01-01", LEIPZIG
        ),
    }


def test_night_without_month_dates_from_the_mail(run_extractor):
    # "Sat 21st" in a mail sent on Saturday 21 May 2039.
    out = run_extractor("hostelworld", "hostelworld-confirmation-no-month.eml")
    assert out == {
        "hostelworld-24455-00000002.reservation.json": stay(
            "24455-00000002",
            "2039-05-21",
            "2039-05-22",
            {
                "@type": "Hostel",
                "name": "Example Hostel Bristol",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "1 Example Square",
                    "addressLocality": "Bristol",
                    "addressCountry": "England",
                },
                "telephone": "+44-117-000-0001",
            },
        ),
    }
