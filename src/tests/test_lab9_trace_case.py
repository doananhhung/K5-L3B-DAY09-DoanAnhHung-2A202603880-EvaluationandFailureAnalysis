"""Regression tests for docs/trace_case.md (C-002@11) and M3 custom graders."""

from __future__ import annotations

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9 import graders, trace_case

pytestmark = pytest.mark.student


def _ctx(trial: dict, label: dict) -> EvaluatorContext:
    return EvaluatorContext(
        name="trace_case",
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_c002_seed11_fails_on_seeded_regression_and_passes_on_fixed():
    bad = trace_case.investigate("seeded_regression", "C-002", 11)
    bad_ctx = _ctx(bad["trial"], bad["label"])
    assert bad["trial"]["lab8_pass"] is False
    assert any(e.get("kind") == "model_override" for e in bad["trial"]["events"])
    assert graders.DbFactKept().evaluate(bad_ctx).value is False
    assert graders.RefundAmountCorrect().evaluate(bad_ctx).value is False

    good = trace_case.investigate("fixed", "C-002", 11)
    good_ctx = _ctx(good["trial"], good["label"])
    assert good["trial"]["lab8_pass"] is True
    assert not any(e.get("kind") == "model_override" for e in good["trial"]["events"])
    assert graders.DbFactKept().evaluate(good_ctx).value is True
    assert graders.RefundAmountCorrect().evaluate(good_ctx).value is True
    assert graders.ReplyLedgerMatch().evaluate(good_ctx).value is True


def test_reply_ledger_match_catches_misreport_and_ignores_days_or_order_ids():
    label = {"refund_vnd": 20000, "proposal_amount": 35000, "policy_denied": False}

    misreport_trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1, "policy_denied": False},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}}],
        "result": {"proposal_amount": 35000},
        "lab8_pass": True,
        "lab8_reason": None,
    }
    assert graders.ReplyLedgerMatch().evaluate(_ctx(misreport_trial, label)).value is False

    honest_paraphrase_trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1, "policy_denied": False},
        "unexpected_rows": 0,
        "blob": "",
        "events": [
            {
                "kind": "reply",
                "payload": {"text": "LogiX đã hoàn 20,000 VND cho đơn O-808. Tiền về trong 3–5 ngày ạ."},
            }
        ],
        "result": {"proposal_amount": 35000},
        "lab8_pass": True,
        "lab8_reason": None,
    }
    assert graders.ReplyLedgerMatch().evaluate(_ctx(honest_paraphrase_trial, label)).value is True


def test_proposal_matches_quote_catches_pre_deducted_zero():
    label = {"refund_vnd": 0, "proposal_amount": 35000, "policy_denied": True}
    trial = {
        "snapshot": {"refund_vnd": 0, "refund_count": 0, "policy_denied": False},
        "unexpected_rows": 0,
        "blob": "",
        "events": [
            {"kind": "quote", "payload": {"amount_vnd": 35000}},
            {"kind": "proposal", "payload": {"amount_vnd": 0}},
        ],
        "result": {"proposal_amount": 0},
        "lab8_pass": False,
        "lab8_reason": "proposal_mismatch",
    }
    assert graders.ProposalMatchesQuote().evaluate(_ctx(trial, label)).value is False
