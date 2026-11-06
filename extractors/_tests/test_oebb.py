"""Tests for the OEBB (Austrian Rail) booking-confirmation extractor."""

from __future__ import annotations


def test_booking_emits_bill_and_ticket(run_extractor):
    out = run_extractor("oebb", "oebb-booking.eml")
    assert set(out) == {
        "oebb-536000000000000000.bill.json",
        "oebb-536000000000000000.bill.pdf",
        "oebb-0990000000000000.ticket.pdf",
    }

    bill = out["oebb-536000000000000000.bill.json"]
    assert bill["payee"] == "ÖBB"
    assert bill["accountId"] == "0990000000000000"
    assert bill["invoiceNumber"] == "536000000000000000"
    assert bill["issueDate"] == "2023-08-01"

    assert out["oebb-536000000000000000.bill.pdf"].startswith(b"%PDF")
    # The ticket PDF is a copy of the same blob; mailsift dedups by
    # content hash so storing it twice is cheap.
    assert out["oebb-0990000000000000.ticket.pdf"] == out[
        "oebb-536000000000000000.bill.pdf"
    ]
