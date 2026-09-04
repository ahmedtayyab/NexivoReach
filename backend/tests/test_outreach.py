import pytest
from app.providers.fallback import FallbackProvider
from app.integrations.gmail import status_payload, is_connected
from app.models.schemas import User


@pytest.mark.asyncio
async def test_follow_up_after_reply():
    draft = await FallbackProvider().generate_follow_up_outreach(
        company_name="Acme",
        why_prospect="Strong fit for private label.",
        prior_subject="Hoodies for Acme",
        prior_body="Hi team...",
        reply_summary="Please send MOQ and pricing.",
        seller_name="Alwasi",
    )
    assert draft["subject"].lower().startswith("re:")
    assert "MOQ" in draft["body"] or "pricing" in draft["body"].lower() or "reply" in draft["personalizedReason"].lower()


@pytest.mark.asyncio
async def test_follow_up_silence_bump():
    draft = await FallbackProvider().generate_follow_up_outreach(
        company_name="Acme",
        why_prospect="Strong fit.",
        prior_subject="Intro",
        prior_body="Hi",
        reply_summary="",
        seller_name="Alwasi",
    )
    assert "silence" in draft["personalizedReason"].lower() or "bump" in draft["body"].lower()


def test_gmail_status_disconnected():
    user = User(id="u1", google_id="g1", email="a@b.com")
    assert is_connected(user) is False
    assert status_payload(user)["connected"] is False
