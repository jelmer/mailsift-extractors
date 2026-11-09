"""Tests for the KLM boarding-pass extractor."""

from __future__ import annotations


def test_each_flight_s_pass_names_its_booking(run_extractor):
    out = run_extractor("klm-boarding-pass", "klm-boarding-pass.eml")
    # No reservations: the booking confirmation has the flights. The
    # PDF repeats the PNGs, so it isn't filed.
    assert out == {
        "klm-kl1001-2030-06-03.ticket.png": b"\x89PNG kl1001",
        "klm-kl1001-2030-06-03.ticket.json": {
            "reservationNumber": "QQQQQQ",
            "provider": "KLM",
            "date": "2030-06-03",
        },
        "klm-kl1002-2030-06-03.ticket.png": b"\x89PNG kl1002",
        "klm-kl1002-2030-06-03.ticket.json": {
            "reservationNumber": "QQQQQQ",
            "provider": "KLM",
            "date": "2030-06-03",
        },
    }


def test_without_a_mobile_pass_the_pdf_is_filed(run_extractor):
    out = run_extractor("klm-boarding-pass", "klm-boarding-pass-pdf-only.eml")
    assert out == {
        "klm-ssssss-boarding-passes-2030-03-09.ticket.pdf": b"%PDF-1.4 boarding passes",
        "klm-ssssss-boarding-passes-2030-03-09.ticket.json": {
            "reservationNumber": "SSSSSS",
            "provider": "KLM",
            "date": "2030-03-09",
        },
    }


def test_a_pass_mailed_in_december_can_be_for_january(run_extractor):
    out = run_extractor("klm-boarding-pass", "klm-boarding-pass-new-year.eml")
    assert out["klm-kl1004-2030-01-01.ticket.json"]["date"] == "2030-01-01"
