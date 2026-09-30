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
    # The Track package link carries orderId, packageIndex and
    # shipmentId -- all three are needed for Amazon's public tracker
    # to resolve the shipment, so keep the URL verbatim.
    assert parcel["trackingUrl"] == (
        "https://www.amazon.co.uk/progress-tracker/package"
        "?_encoding=UTF8&orderId=111-1111111-1111111"
        "&packageIndex=0&shipmentId=TESTSHIP01"
        "&vt=NOTIFICATIONS&ref_=p_btn_fed_track_package"
    )


def test_uk_delivered_emits_parcel_only(run_extractor):
    out = run_extractor("amazon", "amazon-uk-delivered.eml")
    assert set(out) == {"amazon-uk-333-3333333-3333333.parcel.json"}
    parcel = out["amazon-uk-333-3333333-3333333.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderDelivered"
    assert parcel["itemShipped"]["name"] == "Example Connector Adapter Panel Mount"


def test_delivered_url_orderid_is_not_treated_as_a_second_order(run_extractor):
    # Amazon consolidates shipments: the delivered mail's "Track
    # package" URL can carry an `orderId=` that is a *different*
    # order from the one in the "Order #" heading. Emitting a parcel
    # for the URL's orderId used to write a phantom .parcel.json for
    # an order that this mail wasn't actually about.
    out = run_extractor("amazon", "amazon-uk-delivered-consolidated.eml")
    assert set(out) == {"amazon-uk-999-9999999-9999999.parcel.json"}
    parcel = out["amazon-uk-999-9999999-9999999.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderDelivered"


def test_ordered_mail_has_no_tracking_url(run_extractor):
    # The order-placed mail links to the order summary, not a
    # progress-tracker with a shipmentId. Leaving trackingUrl unset
    # lets mailroom's fallback URL take over.
    out = run_extractor("amazon", "amazon-uk-ordered.eml")
    parcel = out["amazon-uk-111-1111111-1111111.parcel.json"]
    assert "trackingUrl" not in parcel


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
        (
            "Example HDMI 2.1 Cable 2M, 8K@60Hz, Supports eARC HDR10 HDCP 2.2/2.3, "
            "Compatible with all HDMI devices"
        ),
    ]
    assert all(i["@type"] == "Product" for i in items)
    assert "shipmentId=TESTSHIPMU" in parcel["trackingUrl"]


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


def test_uk_out_for_delivery_is_its_own_status(run_extractor):
    # Previously collapsed into OrderInTransit, which lost the one
    # update that says the parcel arrives today.
    out = run_extractor("amazon", "amazon-uk-out-for-delivery.eml")
    parcel = out["amazon-uk-444-4444444-4444444.parcel.json"]
    assert parcel["deliveryStatus"] == "OutForDelivery"
    # "Arriving today 12:45 pm - 4:45 pm" on a mail sent 7 September.
    assert parcel["expectedArrivalFrom"] == "2026-09-07"
    assert parcel["expectedArrivalUntil"] == "2026-09-07"


def test_uk_dispatched_carries_the_arrival_estimate(run_extractor):
    # "Arriving Saturday" on a mail sent Thursday 25 June.
    out = run_extractor("amazon", "amazon-uk-dispatched.eml")
    parcel = out["amazon-uk-111-1111111-1111111.parcel.json"]
    assert parcel["expectedArrivalFrom"] == "2026-06-27"
    assert parcel["expectedArrivalUntil"] == "2026-06-27"


def test_de_dispatched_carries_an_arrival_window(run_extractor):
    # "Arriving 21 August - 27 August", mail sent 14 August 2025.
    out = run_extractor("amazon", "amazon-de-dispatched.eml")
    parcel = out["amazon-de-222-2222222-2222222.parcel.json"]
    assert parcel["expectedArrivalFrom"] == "2025-08-21"
    assert parcel["expectedArrivalUntil"] == "2025-08-27"


def test_delivered_has_no_arrival_estimate(run_extractor):
    # A delivered parcel has a real date, not an estimate.
    out = run_extractor("amazon", "amazon-uk-delivered.eml")
    parcel = out["amazon-uk-333-3333333-3333333.parcel.json"]
    assert "expectedArrivalFrom" not in parcel
    assert "expectedArrivalUntil" not in parcel


def test_lowercase_delivery_attempted_is_a_problem(run_extractor):
    # Amazon lowercases the verb on some of these, which used to fall
    # through status_from_subject and emit no status at all.
    out = run_extractor("amazon", "amazon-uk-delivery-attempted.eml")
    parcel = out["amazon-uk-777-7777777-7777777.parcel.json"]
    assert parcel["deliveryStatus"] == "OrderProblem"
    assert "expectedArrivalFrom" not in parcel


def test_one_mail_can_carry_several_orders(run_extractor):
    # A single "Ordered" mail acknowledges each order in its own block.
    # Only the first was emitted before, and its items and Total were
    # taken from whichever block the regex happened to reach first.
    out = run_extractor("amazon", "amazon-uk-ordered-two-orders.eml")
    assert set(out) == {
        "amazon-uk-555-5555555-5555555.parcel.json",
        "amazon-uk-555-5555555-5555555.receipt.json",
        "amazon-uk-666-6666666-6666666.parcel.json",
        "amazon-uk-666-6666666-6666666.receipt.json",
    }

    first = out["amazon-uk-555-5555555-5555555.parcel.json"]
    assert first["expectedArrivalFrom"] == "2026-09-15"
    assert first["expectedArrivalUntil"] == "2026-09-21"
    second = out["amazon-uk-666-6666666-6666666.parcel.json"]
    assert second["expectedArrivalFrom"] == "2026-09-08"
    assert second["expectedArrivalUntil"] == "2026-09-08"

    # Each receipt keeps its own total and items.
    assert (
        out["amazon-uk-555-5555555-5555555.receipt.json"]["priceSpecification"]["price"]
        == 20.02
    )
    assert len(out["amazon-uk-555-5555555-5555555.receipt.json"]["orderedItem"]) == 1
    assert (
        out["amazon-uk-666-6666666-6666666.receipt.json"]["priceSpecification"]["price"]
        == 47.78
    )
    assert len(out["amazon-uk-666-6666666-6666666.receipt.json"]["orderedItem"]) == 2


def test_arrival_window_can_cross_the_new_year(run_extractor):
    # Amazon never writes a year, so "3 January" in a December mail
    # has to roll forward rather than land eleven months in the past.
    out = run_extractor("amazon", "amazon-uk-dispatched-new-year.eml")
    parcel = out["amazon-uk-888-8888888-8888888.parcel.json"]
    assert parcel["expectedArrivalFrom"] == "2026-12-28"
    assert parcel["expectedArrivalUntil"] == "2027-01-03"
