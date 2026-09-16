"""Tests for the Google Play receipt extractor."""

from __future__ import annotations


def test_subscription_renewal(run_extractor):
    out = run_extractor("google-play", "google-play-receipt.eml")
    assert set(out) == {
        "google-play-GPA-0000-0000-0000-00000-3.receipt.json",
        "Example-App-Premium-Example-App-by-Example-Ltd.subscription.json",
    }
    receipt = out["google-play-GPA-0000-0000-0000-00000-3.receipt.json"]
    assert receipt["merchant"] == "Google Play"
    assert receipt["orderNumber"] == "GPA.0000-0000-0000-00000..3"
    assert receipt["orderDate"] == "2026-06-19"
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 1.59,
        "priceCurrency": "GBP",
    }
    # The receipt body lists one item; the extractor now surfaces it
    # in `orderedItem` alongside the top-level total.
    assert receipt["orderedItem"] == [
        {
            "@type": "OrderItem",
            "orderedItem": {
                "@type": "Product",
                "name": "Example App Premium (Example App) (by Example Ltd)",
            },
            "orderQuantity": 1,
            "orderItemSubtotal": {
                "@type": "PriceSpecification",
                "price": 1.59,
                "priceCurrency": "GBP",
            },
        }
    ]

    # The body says `Auto-renewing subscription` and prices the item
    # `/month`, so the renewal is tracked as a subscription too.
    sub = out["Example-App-Premium-Example-App-by-Example-Ltd.subscription.json"]
    assert sub == {
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": "Example App Premium (Example App) (by Example Ltd)",
        "provider": "Google Play",
        "subscriptionDuration": "P1M",
        "price": 1.59,
        "priceCurrency": "GBP",
        "orderDate": "2026-06-19",
    }


def test_legacy_google_play_music_order_extracts(run_extractor):
    # Pre-2014 Google Play Music receipts use a bare `<digits>.<digits>`
    # order number (no `GPA.` prefix) and inline the total on the same
    # line as the tax: `Tax: $0.00Total: $0.00`. Both are recognised
    # so the older half of the mailbox files receipts too.
    out = run_extractor("google-play", "google-play-legacy-receipt.eml")
    assert set(out) == {
        "google-play-12345678901234567890-9999999999999999.receipt.json",
        "Google-Play-Music-All-Access.subscription.json",
    }
    receipt = out["google-play-12345678901234567890-9999999999999999.receipt.json"]
    assert receipt["orderNumber"] == ("12345678901234567890.9999999999999999")
    assert receipt["priceSpecification"] == {
        "@type": "PriceSpecification",
        "price": 0.0,
        "priceCurrency": "USD",
    }
    # The 2013 wording is `Monthly Subscription`, and the item name is
    # asterisk-delimited rather than on its own line.
    sub = out["Google-Play-Music-All-Access.subscription.json"]
    assert sub == {
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": "Google Play Music All Access",
        "provider": "Google Play",
        "subscriptionDuration": "P1M",
        "price": 0.0,
        "priceCurrency": "USD",
        "orderDate": "2013-06-17",
        "renewalDate": "2013-07-17",
    }


def test_one_off_purchase_emits_no_subscription(run_extractor):
    # A plain purchase has no `/month` suffix and no auto-renewal
    # wording, so only the receipt is filed.
    out = run_extractor("google-play", "google-play-one-off.eml")
    assert set(out) == {"google-play-GPA-1111-2222-3333-44444.receipt.json"}
