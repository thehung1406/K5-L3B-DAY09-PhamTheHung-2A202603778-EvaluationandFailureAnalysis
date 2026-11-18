from contextlib import closing
import json

from lab8.db import connect
from lab8.durability import committed_audit_count, get_refund
from lab8.shapes.workflow import run_claim


def test_workflow_rejects_approval_for_another_claim(public_db):
    with closing(connect(public_db)) as conn:
        conn.execute("UPDATE claims SET approval_id = 'A-001' WHERE claim_id = 'C-008'")
        conn.commit()

        result = run_claim("C-008", seed=11, store_path=str(public_db))

        assert result.status == "denied"
        assert result.proposal_amount == 35000
        assert result.error_reason == "approval_claim_mismatch"
        assert get_refund(conn, "C-008") is None
        row = conn.execute(
            "SELECT details_json FROM audit_events WHERE claim_id = ? AND event_type = 'policy_denied'",
            ("C-008",),
        ).fetchone()
        assert row is not None
        assert json.loads(row["details_json"])["reason"] == "approval_claim_mismatch"


def test_workflow_retry_keeps_one_refund_and_audit(public_db):
    first = run_claim("C-011", seed=11, store_path=str(public_db))
    second = run_claim("C-011", seed=11, store_path=str(public_db))

    assert first.status == second.status == "resolved"
    with closing(connect(public_db)) as conn:
        refunds = conn.execute(
            "SELECT amount_vnd FROM refund_ledger WHERE claim_id = ?", ("C-011",)
        ).fetchall()
        assert [row["amount_vnd"] for row in refunds] == [35000]
        assert committed_audit_count(conn, "C-011") == 1
