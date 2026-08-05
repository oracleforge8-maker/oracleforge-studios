"""Stripe configuration for OracleForge (test mode initially).

This module provides helpers to create Stripe products/prices and to
verify webhook signatures. It is intentionally lightweight — the system
runs in waitlist mode until the first 100 users are onboarded.

Setup:
    1. Set STRIPE_SECRET_KEY / STRIPE_PUBLISHABLE_KEY in .env (test keys).
    2. Run: python -m config.stripe_config --setup
    3. The script creates the Radar Pro ($20/mo) and Forge (custom) products
       and prints their price IDs for .env.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional

from src import config
from src.logger import get_logger

log = get_logger("stripe")


def get_stripe() -> Any:
    """Return a Stripe client using the configured secret key.

    Returns:
        Stripe API client.

    Raises:
        RuntimeError if STRIPE_SECRET_KEY is not set.
    """
    import stripe

    key = config.env("STRIPE_SECRET_KEY")
    if not key or key.startswith("sk_test_xxxx"):
        raise RuntimeError("STRIPE_SECRET_KEY not configured (use test keys)")
    stripe.api_key = key
    return stripe


def setup_products() -> Dict[str, str]:
    """Create (or fetch) the Radar Pro and Forge products/prices.

    Returns:
        Dict: {"radar_pro_price": str, "forge_price": str}
    """
    stripe = get_stripe()

    # --- Radar Pro: $20/month ---
    radar_pro = stripe.Product.create(
        name="The Radar Pro",
        description="5 emerging themes, weekly PDF report, Discord access, priority AI replies.",
    )
    radar_price = stripe.Price.create(
        product=radar_pro.id,
        unit_amount=2000,  # $20.00
        currency="usd",
        recurring={"interval": "month"},
    )

    # --- The Forge: custom (no fixed price; use metered/quote) ---
    forge = stripe.Product.create(
        name="The Forge (B2B)",
        description="White-label meme coin intelligence stack. Custom pricing.",
    )
    forge_price = stripe.Price.create(
        product=forge.id,
        unit_amount=0,
        currency="usd",
        nickname="Custom quote",
    )

    log.info("Stripe products ready: Radar Pro=%s, Forge=%s", radar_price.id, forge_price.id)
    return {
        "radar_pro_price": radar_price.id,
        "forge_price": forge_price.id,
    }


def verify_webhook(payload: bytes, sig_header: str) -> Any:
    """Verify a Stripe webhook signature.

    Args:
        payload: Raw request body.
        sig_header: Stripe-Signature header value.

    Returns:
        The verified event object.

    Raises:
        RuntimeError if verification fails or secret is unset.
    """
    import stripe

    secret = config.env("STRIPE_WEBHOOK_SECRET")
    if not secret or secret.startswith("whsec_xxxx"):
        raise RuntimeError("STRIPE_WEBHOOK_SECRET not configured")

    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as exc:  # noqa: BLE001
        log.error("Stripe webhook verification failed: %s", exc)
        raise


def create_checkout_session(price_id: str, email: str, success_url: str,
                            cancel_url: str) -> str:
    """Create a Stripe Checkout session for a subscriber.

    Args:
        price_id: Stripe Price ID.
        email: Customer email.
        success_url: Redirect on success.
        cancel_url: Redirect on cancel.

    Returns:
        Checkout session URL.
    """
    stripe = get_stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


if __name__ == "__main__":
    if "--setup" in sys.argv:
        result = setup_products()
        print("✅ Stripe products created:")
        print(f"  STRIPE_PRICE_RADAR_PRO={result['radar_pro_price']}")
        print(f"  STRIPE_PRICE_FORGE={result['forge_price']}")
        print("Add these to your .env file.")
    else:
        print("Usage: python -m config.stripe_config --setup")