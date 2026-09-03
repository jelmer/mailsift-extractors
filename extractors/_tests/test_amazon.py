"""Tests for the Amazon orders / shipments extractor."""

from __future__ import annotations


def test_uk_ordered_emits_receipt_and_parcel(run_extractor):
    out = run_extractor("amazon", "amazon-uk-ordered.eml")
    assert set(out) == {
        "amazon-uk-111-1111111-1111111.parcel.json",
        "amazon-uk-111-1111111-1111111.receipt.json",
    }

    parcel = out["amazon-uk-111-1111111-1111111.parcel.json"]
    assert parcel["trackingNumber"] == "111-1111111-1111111"
    assert parcel["provider"]["@id"] == "amazon-uk"
    assert parcel["deliveryStatus"] == "OrderProcessing"
    # itemShipped mirrors what's on the receipt so the parcel dashboard
    # can name the contents without cross-referencing.
    assert "Example Gadget X1" in parcel["itemShipped"]["name"]

    receipt = out["amazon-uk-111-1111111-1111111.receipt.json"]
    assert receipt["merchant"] == "Amazon"
    assert receipt["orderNumber"] == "111-1111111-1111111"
    assert receipt["orderDate"] == "2026-06-24"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 26.93,
        "priceCurrency": "GBP",
    }
    assert len(receipt["orderedItem"]) == 1
    item = receipt["orderedItem"][0]
    assert item["orderQuantity"] == 1
    assert "Example Gadget X1" in item["orderedItem"]["name"]


def test_uk_dispatched_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-uk-dispatched.eml")
    assert set(out) == {"amazon-uk-111-1111111-1111111.parcel.json"}
    parcel = out["amazon-uk-111-1111111-1111111.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderInTransit"
    # The dispatched mail names the item on a bullet; the extractor
    # stamps it on the parcel so the dashboard can show what's in the
    # box without cross-referencing the earlier receipt.
    assert parcel["itemShipped"]["@type"] == "Product"
    assert "Example Gadget X1" in parcel["itemShipped"]["name"]


def test_uk_delivered_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-uk-delivered.eml")
    assert set(out) == {"amazon-uk-333-3333333-3333333.parcel.json"}
    parcel = out["amazon-uk-333-3333333-3333333.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderDelivered"
    assert parcel["itemShipped"]["name"] == "Example Connector Adapter Panel Mount"


def test_uk_dispatched_with_multiple_items(run_extractor):
    # A multi-item shipment: itemShipped becomes an array of Products
    # rather than a single Product. Modelled after a real dispatched
    # mail; sensitive fields scrubbed.
    out = run_extractor("amazon", "amazon-uk-dispatched-multiple.eml")
    assert set(out) == {"amazon-uk-444-4444444-4444444.parcel.json"}
    parcel = out["amazon-uk-444-4444444-4444444.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderInTransit"
    items = parcel["itemShipped"]
    assert isinstance(items, list)
    assert [i["name"] for i in items] == [
        "Example Gadget X1",
        "Example HDMI 2.1 Cable 2M, 8K@60Hz, Supports eARC HDR10 HDCP 2.2/2.3, "
        "Compatible with all HDMI devices",
    ]
    assert all(i["@type"] == "Product" for i in items)


def test_de_ordered_emits_receipt_and_parcel(run_extractor):
    out = run_extractor("amazon", "amazon-de-ordered.eml")
    assert set(out) == {
        "amazon-de-222-2222222-2222222.parcel.json",
        "amazon-de-222-2222222-2222222.receipt.json",
    }

    parcel = out["amazon-de-222-2222222-2222222.parcel.json"]
    assert parcel["trackingNumber"] == "222-2222222-2222222"
    assert parcel["provider"]["@id"] == "amazon-de"
    assert parcel["deliveryStatus"] == "OrderProcessing"

    receipt = out["amazon-de-222-2222222-2222222.receipt.json"]
    assert receipt["orderNumber"] == "222-2222222-2222222"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 31.05,
        "priceCurrency": "EUR",
    }


def test_de_dispatched_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-de-dispatched.eml")
    assert set(out) == {"amazon-de-222-2222222-2222222.parcel.json"}
    parcel = out["amazon-de-222-2222222-2222222.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderInTransit"
    assert parcel["provider"]["@id"] == "amazon-de"


def test_nl_localised_dispatched(run_extractor):
    # Amazon.nl mails may carry a Dutch-localised subject
    # ("Je bestelling bij Amazon.nl ... is verzonden") rather than
    # the English `Dispatched:` prefix. The status keyword lives
    # somewhere in the middle of the subject.
    out = run_extractor("amazon", "amazon-nl-dispatched.eml")
    assert set(out) == {"amazon-nl-408-9999999-9999999.parcel.json"}
    parcel = out["amazon-nl-408-9999999-9999999.parcel.json"]
    assert parcel["provider"]["@id"] == "amazon-nl"
    assert parcel["deliveryStatus"] == "OrderInTransit"
    # The NL localised mail lists the bullet but not a Quantity line,
    # so the strict ITEM_RE deliberately misses it -- better an empty
    # itemShipped than the wrong one.
    assert "itemShipped" not in parcel


def test_de_localised_dispatched(run_extractor):
    # Amazon.de mails may carry a German-localised subject
    # ("Ihre Amazon.de Bestellung von X wurde versandt!"). The
    # extractor recognises "wurde versandt" anywhere in the subject.
    out = run_extractor("amazon", "amazon-de-localised-dispatched.eml")
    assert set(out) == {"amazon-de-028-9999999-9999999.parcel.json"}
    parcel = out["amazon-de-028-9999999-9999999.parcel.json"]
    assert parcel["provider"]["@id"] == "amazon-de"
    assert parcel["deliveryStatus"] == "OrderInTransit"
