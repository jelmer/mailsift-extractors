"""Tests for the SNCF Connect trip receipt extractor."""

from __future__ import annotations

from pathlib import Path

EXTRACTORS_DIR = Path(__file__).resolve().parent.parent


def manifest_requires(name: str) -> list[str]:
    """Return the `requires:` list from an extractor manifest."""
    lines = (EXTRACTORS_DIR / f"{name}.yaml").read_text().splitlines()
    start = lines.index("requires:") + 1
    requires = []
    for line in lines[start:]:
        if not line.startswith("  - "):
            break
        requires.append(line.removeprefix("  - ").strip())
    return requires


def test_trip_emits_receipt(run_extractor):
    out = run_extractor("sncf-connect", "sncf-connect-trip.eml")
    assert set(out) == {"sncf-connect-TESTPN.receipt.json"}
    receipt = out["sncf-connect-TESTPN.receipt.json"]
    assert receipt["merchant"] == "SNCF Connect"
    assert receipt["orderNumber"] == "TESTPN"
    # Origin - destination taken from the subject (the body has no
    # station labels, only station-referenced payment metadata).
    assert receipt["description"] == "Bordeaux-Saint-Jean - Paris Montparnasse"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 104.00,
        "priceCurrency": "EUR",
    }
    assert receipt["orderDate"] == "2025-08-16"


def test_html_body_also_emits_reservation(run_extractor):
    # When the HTML body carries the `Outbound: <weekday>, <D Month
    # YYYY> at <HH:MM>` line and an `OUTBOUND <PROVIDER> <NUMBER>`
    # header for the leg, emit a TrainReservation alongside the
    # receipt so the trip lands in the archive with a departure
    # time.
    out = run_extractor("sncf-connect", "sncf-connect-trip-html.eml")
    assert "sncf-connect-TESTPN.receipt.json" in out
    assert "sncf-connect-TESTPN-outbound.reservation.json" in out
    reservation = out["sncf-connect-TESTPN-outbound.reservation.json"]
    assert reservation["@type"] == "TrainReservation"
    assert reservation["reservationNumber"] == "sncf-connect-TESTPN-outbound"
    for_ = reservation["reservationFor"]
    assert for_["@type"] == "TrainTrip"
    assert for_["departureStation"]["name"] == "Bordeaux-Saint-Jean"
    assert for_["arrivalStation"]["name"] == "Paris Montparnasse 1 Et 2"
    assert for_["departureTime"] == "2026-08-16T06:58:00"
    assert for_["trainNumber"] == "8534"
    assert for_["provider"]["name"] == "SNCF"


def test_manifest_does_not_require_html():
    # The extractor emits the receipt from the plain-text body alone,
    # and `sncf-connect-trip.eml` is a text/plain-only mail. Every
    # `requires:` entry has to hold for the pipeline to dispatch at
    # all, so listing `html` here would stop those mails reaching the
    # extractor even though it handles them.
    # Read the block by hand rather than with PyYAML: the test suite
    # has no third-party dependencies and CI installs pytest alone.
    assert manifest_requires("sncf-connect") == ["text"]
