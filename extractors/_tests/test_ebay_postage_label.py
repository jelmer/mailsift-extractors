"""Tests for the eBay postage label extractor."""

from __future__ import annotations


def test_label_is_an_outgoing_parcel(run_extractor):
    assert run_extractor("ebay-postage-label", "ebay-postage-label.eml") == {
        "ebay-VU000000005GB.parcel.json": {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": "VU000000005GB",
            "deliveryStatus": "Scheduled",
            "mailsift:direction": "outgoing",
            "orderNumber": "00-00000-00000",
            "provider": {
                "@type": "Organization",
                "@id": "royal-mail",
                "name": "Royal Mail",
            },
            "deliveryAddress": {
                "@type": "PostalAddress",
                "name": "Example Buyer",
                "addressLocality": "Exampleton",
                "postalCode": "EX1 1AA",
            },
            "itemShipped": [{"@type": "Product", "name": "Example Thermostat"}],
        }
    }


def test_carrier_drops_the_parenthesised_note(run_extractor):
    out = run_extractor("ebay-postage-label", "ebay-postage-label-inpost.eml")
    parcel = out["ebay-JJD0000000000000000006.parcel.json"]
    assert parcel["provider"] == {
        "@type": "Organization",
        "@id": "inpost",
        "name": "InPost",
    }
