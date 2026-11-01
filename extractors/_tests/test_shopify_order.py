"""Tests for the generic Shopify-templated order/shipment extractor."""

from __future__ import annotations


def test_confirmation_emits_receipt(run_extractor):
    out = run_extractor("shopify-order", "shopify-pihut-confirmed.eml")
    assert set(out) == {"thepihut-100002.receipt.json"}
    receipt = out["thepihut-100002.receipt.json"]
    # Merchant name comes from the sender's domain, not a hardcoded
    # vendor list - any Shopify-templated shop works.
    assert receipt["merchant"] == "Thepihut"
    assert receipt["orderNumber"] == "100002"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 42.30,
        "priceCurrency": "GBP",
    }
    assert len(receipt["orderedItem"]) == 1
    item = receipt["orderedItem"][0]
    assert item["orderQuantity"] == 1
    assert "Example Gadget" in item["orderedItem"]["name"]
    assert item["orderItemSubtotal"]["price"] == 38.40


def test_shipment_emits_parcel(run_extractor):
    out = run_extractor("shopify-order", "shopify-patch-shipped.eml")
    assert set(out) == {"patchplants-15000000000000.parcel.json"}
    parcel = out["patchplants-15000000000000.parcel.json"]
    assert parcel["trackingNumber"] == "15000000000000"
    # Carrier name is parsed out of the body, not assumed.
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "dpd",
        "name": "DPD",
    }
    assert parcel["orderNumber"] == "100001"
    assert parcel["merchant"] == "Patchplants"


def test_shopifyemail_sender_uses_display_name_as_merchant(run_extractor):
    # Shops on Shopify Email send through relays like `t.shopifyemail.com`
    # which don't carry the shop's identity in the sender domain. The
    # merchant name has to come from the `From:` display name, and the
    # order number is emitted without a `#` prefix (BikeParts uses
    # opaque alphanumeric IDs). The resulting filename is slugified so
    # dots in `BikeParts.co.uk` don't leak through.
    out = run_extractor("shopify-order", "shopify-shopifyemail-shipped.eml")
    assert set(out) == {"bikeparts-co-uk-VF649847141GB.parcel.json"}
    parcel = out["bikeparts-co-uk-VF649847141GB.parcel.json"]
    assert parcel["merchant"] == "BikeParts.co.uk"
    assert parcel["orderNumber"] == "BP427930"
    assert parcel["trackingNumber"] == "VF649847141GB"
    assert parcel["provider"]["@id"] == "royal-mail"


def test_own_domain_shop_confirmation_with_variant_lines(run_extractor):
    # A shop on its own domain: signed by that domain (the manifest's
    # `@from`), sent through Shopify's mailer (Shopify's Message-ID and
    # Feedback-ID). The first item has a variant line before its price.
    out = run_extractor("shopify-order", "shopify-own-domain-confirmed.eml")
    assert set(out) == {"shop-100123.receipt.json"}
    receipt = out["shop-100123.receipt.json"]
    assert receipt["orderNumber"] == "100123"
    assert receipt["priceSpecification"]["price"] == 30.0
    assert receipt["priceSpecification"]["priceCurrency"] == "USD"
    assert [
        (i["orderedItem"]["name"], i["orderQuantity"], i["orderItemSubtotal"]["price"])
        for i in receipt["orderedItem"]
    ] == [("Example Widget", 1, 20.0), ("Plain Thing", 2, 5.0)]


def test_own_subdomain_shop_shipment_with_usps_tracking(run_extractor):
    # Signed by a subdomain of the From domain, as Shopify's mailer does
    # for some custom-domain shops.
    out = run_extractor("shopify-order", "shopify-own-subdomain-shipped.eml")
    assert set(out) == {"goods-9400100000000000000001.parcel.json"}
    parcel = out["goods-9400100000000000000001.parcel.json"]
    assert parcel["trackingNumber"] == "9400100000000000000001"
    assert parcel["provider"]["@id"] == "usps"
    assert parcel["orderNumber"] == "100456"


def test_own_domain_mail_without_shopify_fingerprint_is_ignored(run_extractor):
    # `@from` lets any self-signed sender reach the script; without
    # Shopify's Message-ID or Feedback-ID it must produce nothing.
    assert run_extractor("shopify-order", "shopify-own-domain-not-shopify.eml") == {}
