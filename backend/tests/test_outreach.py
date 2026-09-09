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


def test_recipient_from_contacts_when_draft_to_empty():
    from app.api.outreach import _recipient_email
    from app.models.schemas import ProspectRecord

    row = ProspectRecord(
        id="p1",
        business_id="b1",
        company_name="Acme",
        email="",
        contacts=[
            {"type": "phone", "value": "555-0100"},
            {"type": "email", "value": "sales@acme.com", "label": "Email"},
        ],
        outreach_draft={
            "subject": "Hi",
            "body": "Hello",
            "status": "Draft",
            "toEmail": "",
        },
    )
    assert _recipient_email(row) == "sales@acme.com"


def test_resolve_lead_email_fills_serializer_shape():
    from app.tools.contact_finder import resolve_lead_email, email_from_contacts

    assert email_from_contacts([{"type": "Email", "value": "Hi@Brand.COM"}]) == "hi@brand.com"
    assert resolve_lead_email(
        email="",
        contacts=[{"type": "email", "value": "mailto:orders@brand.com?subject=Hi"}],
        to_email="",
    ) == "orders@brand.com"


def test_recipient_prefers_draft_toemail():
    from app.api.outreach import _recipient_email
    from app.models.schemas import ProspectRecord

    row = ProspectRecord(
        id="p1",
        business_id="b1",
        company_name="Acme",
        email="fallback@acme.com",
        contacts=[{"type": "email", "value": "contacts@acme.com"}],
        outreach_draft={"toEmail": "draft@acme.com", "status": "Draft", "subject": "x", "body": "y"},
    )
    assert _recipient_email(row) == "draft@acme.com"


def test_draft_ready_uses_contacts_email():
    from app.api.outreach import _draft_ready_to_send
    from app.models.schemas import ProspectRecord

    row = ProspectRecord(
        id="p1",
        business_id="b1",
        company_name="Acme",
        email="",
        contacts=[{"type": "email", "value": "hello@acme.com"}],
        outreach_draft={
            "subject": "Intro",
            "body": "Body text",
            "status": "Draft",
            "toEmail": "",
        },
    )
    assert _draft_ready_to_send(row) is True
