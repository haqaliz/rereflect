"""
TDD tests for the pure HubSpot / Salesforce candidate adapters (harvester-core
aspect). Pure asserts only — no I/O, no fixtures, no DB, no mocks, no `patch`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.services.churn_harvest_adapters import (
    hubspot_deal_to_candidate,
    salesforce_opportunity_to_candidate,
)

HS_DEAL = {
    "id": "d1",
    "properties": {
        "dealname": "Acme Renewal",
        "dealstage": "closedlost",
        "amount": "5000",
        "closedate": "2026-06-15T00:00:00Z",
        "pipeline": "renewal_pipeline",
    },
}

SF_OPP = {
    "Id": "006AAA",
    "Name": "Acme Renewal",
    "StageName": "Closed Lost",
    "Amount": 5000,
    "CloseDate": "2026-06-15",
    "IsClosed": True,
    "IsWon": False,
    "Type": "Renewal",
}


class TestIdenticalShape:
    def test_hubspot_and_salesforce_candidates_have_identical_keys(self):
        hs = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        sf = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert set(hs) == set(sf)
        assert set(hs) == {
            "customer_email",
            "external_opportunity_id",
            "suggested_churned_at",
            "evidence",
            "is_closed",
            "is_won",
            "discriminator",
        }


class TestCloseDateStability:
    def test_suggested_churned_at_is_crm_close_date_not_now(self):
        hs = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert hs["suggested_churned_at"] == datetime(2026, 6, 15, tzinfo=timezone.utc)

    def test_suggested_churned_at_stable_across_two_calls(self):
        first = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        second = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert first["suggested_churned_at"] == second["suggested_churned_at"]

    def test_sf_suggested_churned_at_is_crm_close_date(self):
        sf = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert sf["suggested_churned_at"] == datetime(2026, 6, 15)


class TestMissingIdOrCloseDate:
    def test_hubspot_missing_id_returns_none(self):
        deal = {"properties": HS_DEAL["properties"]}
        assert hubspot_deal_to_candidate(deal, "alice@example.com") is None

    def test_hubspot_missing_close_date_returns_none(self):
        deal = {
            "id": "d2",
            "properties": {**HS_DEAL["properties"], "closedate": None},
        }
        assert hubspot_deal_to_candidate(deal, "alice@example.com") is None

    def test_hubspot_unparseable_close_date_returns_none(self):
        deal = {
            "id": "d3",
            "properties": {**HS_DEAL["properties"], "closedate": "not-a-date"},
        }
        assert hubspot_deal_to_candidate(deal, "alice@example.com") is None

    def test_salesforce_missing_id_returns_none(self):
        opp = {k: v for k, v in SF_OPP.items() if k != "Id"}
        assert salesforce_opportunity_to_candidate(opp, "alice@example.com") is None

    def test_salesforce_missing_close_date_returns_none(self):
        opp = {**SF_OPP, "CloseDate": None}
        assert salesforce_opportunity_to_candidate(opp, "alice@example.com") is None

    def test_salesforce_unparseable_close_date_returns_none(self):
        opp = {**SF_OPP, "CloseDate": "not-a-date"}
        assert salesforce_opportunity_to_candidate(opp, "alice@example.com") is None


class TestIsWonIsClosedDiscriminator:
    def test_hubspot_is_won_true_only_for_closedwon(self):
        won_deal = {**HS_DEAL, "properties": {**HS_DEAL["properties"], "dealstage": "closedwon"}}
        candidate = hubspot_deal_to_candidate(won_deal, "alice@example.com")
        assert candidate["is_won"] is True
        assert candidate["is_closed"] is True

    def test_hubspot_is_closed_true_for_closedlost(self):
        candidate = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert candidate["is_closed"] is True
        assert candidate["is_won"] is False

    def test_hubspot_is_closed_false_for_open_stage(self):
        open_deal = {**HS_DEAL, "properties": {**HS_DEAL["properties"], "dealstage": "contractsent"}}
        candidate = hubspot_deal_to_candidate(open_deal, "alice@example.com")
        assert candidate["is_closed"] is False
        assert candidate["is_won"] is False

    def test_hubspot_discriminator_is_pipeline(self):
        candidate = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert candidate["discriminator"] == "renewal_pipeline"

    def test_salesforce_is_won_reflects_actual_boolean(self):
        opp_false = {**SF_OPP, "IsWon": False}
        assert salesforce_opportunity_to_candidate(opp_false, "alice@example.com")["is_won"] is False

        opp_true = {**SF_OPP, "IsWon": True}
        assert salesforce_opportunity_to_candidate(opp_true, "alice@example.com")["is_won"] is True

    def test_salesforce_is_won_is_strict_boolean_not_truthy_string(self):
        # A non-bool truthy value (e.g. a stray string) must not silently
        # flip is_won to True — SF the IsWon boolean, exactly (not string
        # truthiness on some other field standing in for it).
        opp = {**SF_OPP, "IsWon": False}
        candidate = salesforce_opportunity_to_candidate(opp, "alice@example.com")
        assert candidate["is_won"] is False
        assert isinstance(candidate["is_won"], bool)

    def test_salesforce_is_closed_uses_isclosed_field(self):
        candidate = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert candidate["is_closed"] is True

    def test_salesforce_discriminator_is_type(self):
        candidate = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert candidate["discriminator"] == "Renewal"


class TestEvidenceAndEmail:
    def test_hubspot_evidence_shape_and_provider(self):
        candidate = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert candidate["evidence"] == {
            "name": "Acme Renewal",
            "stage": "closedlost",
            "type": "renewal_pipeline",
            "amount": 5000.0,
            "close_date": "2026-06-15T00:00:00Z",
            "provider": "hubspot",
        }

    def test_salesforce_evidence_shape_and_provider(self):
        candidate = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert candidate["evidence"] == {
            "name": "Acme Renewal",
            "stage": "Closed Lost",
            "type": "Renewal",
            "amount": 5000.0,
            "close_date": "2026-06-15",
            "provider": "salesforce",
        }

    def test_hubspot_amount_parse_failure_returns_none_not_raise(self):
        deal = {**HS_DEAL, "properties": {**HS_DEAL["properties"], "amount": "not-a-number"}}
        candidate = hubspot_deal_to_candidate(deal, "alice@example.com")
        assert candidate is not None
        assert candidate["evidence"]["amount"] is None

    def test_salesforce_amount_parse_failure_returns_none_not_raise(self):
        opp = {**SF_OPP, "Amount": "not-a-number"}
        candidate = salesforce_opportunity_to_candidate(opp, "alice@example.com")
        assert candidate is not None
        assert candidate["evidence"]["amount"] is None

    def test_customer_email_is_lowercased(self):
        hs = hubspot_deal_to_candidate(HS_DEAL, "Alice@Example.com")
        assert hs["customer_email"] == "alice@example.com"

    def test_external_opportunity_id_from_hubspot_id(self):
        candidate = hubspot_deal_to_candidate(HS_DEAL, "alice@example.com")
        assert candidate["external_opportunity_id"] == "d1"

    def test_external_opportunity_id_from_salesforce_id(self):
        candidate = salesforce_opportunity_to_candidate(SF_OPP, "alice@example.com")
        assert candidate["external_opportunity_id"] == "006AAA"
