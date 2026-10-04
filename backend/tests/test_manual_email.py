from app.api.prospects import apply_manual_lead_email, normalize_manual_email
from app.models.schemas import ProspectRecord


def test_manual_email_replaces_the_address_used_for_the_lead():
    record = ProspectRecord(
        company_name="Acme",
        website="https://acme.example",
        location="Ohio",
        industry="sporting",
        company_size="",
        fit_score=1,
        why_this_prospect="",
        recommended_approach="",
        discovered_at="",
        email="old@acme.example",
        contacts=[
            {"type": "email", "value": "old@acme.example"},
            {"type": "phone", "value": "555-0100"},
        ],
        outreach_draft={"toEmail": "old@acme.example", "subject": "Hello", "body": "Hi"},
    )
    apply_manual_lead_email(record, normalize_manual_email("mailto:buyer@acme.example?subject=Hi"))
    assert record.email == "buyer@acme.example"
    assert record.contacts[0]["value"] == "buyer@acme.example"
    assert record.contacts[0]["source"] == "manual"
    assert any(item.get("type") == "phone" for item in record.contacts)
    assert not any(item.get("value") == "old@acme.example" for item in record.contacts)
    assert record.outreach_draft["toEmail"] == "buyer@acme.example"
    assert record.outreach_draft["subject"] == "Hello"


def test_blank_manual_email_clears_the_lead_address():
    record = ProspectRecord(
        company_name="Acme",
        website="https://acme.example",
        location="",
        industry="",
        company_size="",
        fit_score=0,
        why_this_prospect="",
        recommended_approach="",
        discovered_at="",
        email="buyer@acme.example",
        contacts=[{"type": "email", "value": "buyer@acme.example"}],
        outreach_draft={"toEmail": "buyer@acme.example"},
    )
    apply_manual_lead_email(record, "")
    assert record.email == ""
    assert record.contacts == []
    assert record.outreach_draft["toEmail"] == ""
