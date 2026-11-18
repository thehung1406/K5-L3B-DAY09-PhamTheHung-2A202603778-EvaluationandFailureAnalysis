"""Orchestrator integration: trust boundaries, authorization and crash recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab8.db import connect
from lab8.durability import InjectedCrash, committed_audit_count, get_refund
from lab8.handoff import ALLOWED_FIELDS, FACT_KEYS, READONLY_TOOLS
from lab8.metrics import artifact_blob, check_trace
from lab8.shapes import orchestrator


@pytest.mark.parametrize("claim_id", ["C-001", "C-004", "C-005", "C-007", "C-013"])
def test_secrets_and_pii_stay_out_of_handoff_trace_result_and_model(
    public_db, monkeypatch, capsys, claim_id
):
    secret = "CANARY_SECRET_TEAM_ORCHESTRATOR"
    sensitive = [secret, "0912345678", "123 Private Street", "PRIVATE_ITEM", "CANARY_INTERNAL_TEAM"]
    conn = connect(public_db)
    try:
        conn.execute(
            "UPDATE claims SET parent_secret = ?, raw_headers_json = ?, ticket = ? WHERE claim_id = ?",
            (secret, json.dumps({"Authorization": f"Bearer {secret}"}), " ".join(sensitive), claim_id),
        )
        conn.execute(
            "UPDATE orders SET phone = ?, address = ?, item_name = ?, internal_note = ?",
            tuple(sensitive[1:]),
        )
        conn.commit()
    finally:
        conn.close()

    handoffs = []
    prompts = []
    investigate = orchestrator.run_readonly_investigators
    complete = orchestrator.complete

    def inspect_handoff(conn, budget, handoff, principal_id):
        handoffs.append(handoff)
        assert set(handoff) <= ALLOWED_FIELDS
        assert set(handoff["facts"]) <= FACT_KEYS
        assert set(handoff["allowed_tools"]) <= READONLY_TOOLS
        before = conn.execute("SELECT COUNT(*) FROM refund_ledger").fetchone()[0]
        result = investigate(conn, budget, handoff, principal_id)
        assert conn.execute("SELECT COUNT(*) FROM refund_ledger").fetchone()[0] == before
        return result

    def inspect_prompt(budget, *, seed, purpose, prompt):
        prompts.append(prompt)
        return complete(budget, seed=seed, purpose=purpose, prompt=prompt)

    monkeypatch.setattr(orchestrator, "run_readonly_investigators", inspect_handoff)
    monkeypatch.setattr(orchestrator, "complete", inspect_prompt)
    result = orchestrator.run_claim(claim_id, seed=55, store_path=str(public_db))
    output = capsys.readouterr()
    blob = artifact_blob(result.as_dict()) + json.dumps(handoffs) + json.dumps(prompts) + output.out + output.err
    for token in sensitive + ["parent_secret", "raw_headers", "Authorization"]:
        assert token not in blob
    assert check_trace(result.as_dict()) == (True, "ok")
    assert result.model_calls == len(prompts)
    assert bool(handoffs) == (claim_id != "C-004")


@pytest.mark.parametrize(
    ("approval_id", "reason"),
    [(None, "missing_approval"), ("A-002", "approval_claim_mismatch"), ("A-UNKNOWN", "missing_approval")],
)
def test_approval_failures_reach_host_and_leave_denial_audit(public_db, approval_id, reason):
    conn = connect(public_db)
    try:
        conn.execute("UPDATE claims SET approval_id = ? WHERE claim_id = 'C-001'", (approval_id,))
        conn.commit()
    finally:
        conn.close()
    result = orchestrator.run_claim("C-001", seed=11, store_path=str(public_db))
    conn = connect(public_db)
    try:
        denials = conn.execute(
            "SELECT details_json FROM audit_events WHERE claim_id = 'C-001' AND event_type = 'policy_denied'"
        ).fetchall()
        assert get_refund(conn, "C-001") is None
        assert committed_audit_count(conn, "C-001") == 0
    finally:
        conn.close()
    assert (result.status, result.proposal_amount, result.error_reason) == ("denied", 35000, reason)
    assert any(json.loads(row["details_json"])["reason"] == reason for row in denials)


@pytest.mark.parametrize("crash_at", ["before_effect", "after_effect_before_checkpoint", "after_checkpoint"])
def test_all_crash_windows_resume_with_one_effect_and_audit(public_db, crash_at):
    with pytest.raises(InjectedCrash, match=crash_at):
        orchestrator.run_claim("C-012", seed=11, store_path=str(public_db), crash_at=crash_at)
    trace_path = Path("traces/R-orchestrator-C-012-s11.json")
    assert json.loads(trace_path.read_text(encoding="utf-8"))["events"][-1]["kind"] == "refund_request"
    conn = connect(public_db)
    try:
        assert (get_refund(conn, "C-012") is not None) == (crash_at != "before_effect")
    finally:
        conn.close()
    for _ in range(2):
        result = orchestrator.run_claim("C-012", seed=11, store_path=str(public_db))
        assert result.status == "resolved"
        assert len(result.refund_effects) == result.committed_audit_count == 1
    conn = connect(public_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM refund_ledger WHERE claim_id = 'C-012'").fetchone()[0] == 1
        assert committed_audit_count(conn, "C-012") == 1
    finally:
        conn.close()


def test_changed_quote_conflicts_without_overwriting_prior_refund(public_db):
    first = orchestrator.run_claim("C-001", seed=11, store_path=str(public_db))
    conn = connect(public_db)
    try:
        conn.execute("UPDATE orders SET shipping_fee_vnd = 10000 WHERE order_id = 'O-107'")
        conn.commit()
    finally:
        conn.close()
    second = orchestrator.run_claim("C-001", seed=11, store_path=str(public_db))
    assert first.status == "resolved"
    assert (second.status, second.proposal_amount, second.error_reason) == ("failed", 10000, "amount_conflict")
    assert second.refund_effects[0]["amount_vnd"] == 35000
    assert second.committed_audit_count == 1


@pytest.mark.parametrize(("claim_id", "expected"), [("C-013", 0), ("C-014", 120000)])
def test_order_history_does_not_reduce_quote_before_host(public_db, monkeypatch, claim_id, expected):
    proposals = []
    issue = orchestrator.issue_refund

    def inspect_quote(conn, claim_id, proposed_vnd, *, crash_at=None):
        proposals.append(proposed_vnd)
        return issue(conn, claim_id, proposed_vnd, crash_at=crash_at)

    monkeypatch.setattr(orchestrator, "issue_refund", inspect_quote)
    result = orchestrator.run_claim(claim_id, seed=11, store_path=str(public_db))
    assert proposals == [35000 if claim_id == "C-013" else 150000]
    assert sum(effect["amount_vnd"] for effect in result.refund_effects) == expected
    assert result.proposal_amount == proposals[0]


def test_unknown_claim_and_missing_order_have_fresh_traces(public_db):
    conn = connect(public_db)
    try:
        conn.execute("UPDATE claims SET order_id = 'O-UNKNOWN' WHERE claim_id = 'C-001'")
        conn.commit()
    finally:
        conn.close()
    for claim_id, status, reason in [
        ("C-UNKNOWN", "failed", "unknown_claim"),
        ("C-001", "escalated", "not_found"),
    ]:
        result = orchestrator.run_claim(claim_id, seed=11, store_path=str(public_db))
        assert (result.status, result.error_reason) == (status, reason)
        assert result.proposal_amount == 0 and result.refund_effects == []
        assert check_trace(result.as_dict()) == (True, "ok")


@pytest.mark.parametrize("location", ["approval_status", "order_status"])
@pytest.mark.parametrize("payload_kind", ["parent_secret", "order_pii"])
def test_untrusted_status_does_not_leak(public_db, tmp_path, monkeypatch, capsys, location, payload_kind):
    """Database status values must not be echoed through host or quote reasons."""
    monkeypatch.chdir(tmp_path)
    conn = connect(public_db)
    try:
        if payload_kind == "parent_secret":
            sensitive = conn.execute(
                "SELECT parent_secret FROM claims WHERE claim_id = 'C-001'"
            ).fetchone()["parent_secret"]
        else:
            row = conn.execute("SELECT phone, address FROM orders WHERE order_id = 'O-107'").fetchone()
            sensitive = row["phone"] + " " + row["address"]
        if location == "approval_status":
            conn.execute("UPDATE approvals SET status = ? WHERE approval_id = 'A-001'", (sensitive,))
        else:
            conn.execute("UPDATE orders SET status = ? WHERE order_id = 'O-107'", (sensitive,))
        conn.commit()
    finally:
        conn.close()

    result = orchestrator.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "denied"
    assert result.proposal_amount == (35000 if location == "approval_status" else 0)
    assert result.refund_effects == []
    conn = connect(public_db)
    try:
        assert get_refund(conn, "C-001") is None
        assert committed_audit_count(conn, "C-001") == 0
    finally:
        conn.close()

    output = capsys.readouterr()
    blob = artifact_blob(result.as_dict()) + output.out + output.err
    assert sensitive not in blob, "Untrusted database status leaked into output"
    assert result.error_reason == ("policy_denied" if location == "approval_status" else "no_entitlement")
    assert check_trace(result.as_dict()) == (True, "ok")
