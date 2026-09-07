"""Approval basis and proposal revisions cannot retain obsolete spending authority."""

import json
import time

import pytest

from reference_organizations.store.agent import seed_lucy
from sovereign_agent import database
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_work import claim, enqueue
from sovereign_agent.database import Database


class Supplier:
    idempotent = True
    identity = "lucy-local"
    timeout = 1

    def __init__(self, *, lose_response=False, discover=True):
        self.calls = 0
        self.lookups = 0
        self.receipt = None
        self.lose_response = lose_response
        self.discover = discover

    def lookup(self, operation):
        self.lookups += 1
        return self.receipt if self.discover else None

    def order(self, operation, proposal):
        self.calls += 1
        self.receipt = {"operation": operation, "proposal": proposal, "status": "ACCEPTED"}
        if self.lose_response:
            raise TimeoutError("accepted but response lost")
        return self.receipt


def setup(root):
    db = Database(root / "agent.sqlite")
    seed_lucy(db)
    enqueue(db, "morning", "lucy", "Replenish vanilla")
    work = claim(db, "worker")
    operation = propose(db, work, "SKU-VANILLA", 6)
    return db, work, operation


def grant(db, operation, *, automatic=False, policy=None):
    digest = db.connection.execute(
        "SELECT digest FROM assistant_orders WHERE id=?", (operation,)
    ).fetchone()[0]
    approve(
        db,
        operation,
        digest,
        actor="lucy",
        policy=policy or SpendingPolicy(frozenset({"lucy"}), automatic_order_pence=2000),
        expires=time.time() + 60,
        automatic=automatic,
    )


def balances(db):
    return tuple(
        db.connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending"
        ).fetchone()
    )


def test_reduced_automatic_limit_requires_operator_approval_even_after_restart(tmp_path):
    db, work, operation = setup(tmp_path)
    grant(db, operation, automatic=True)
    db.close()
    db = Database(tmp_path / "agent.sqlite")
    supplier = Supplier()
    policy = SpendingPolicy(frozenset({"lucy"}), automatic_order_pence=0)
    with pytest.raises(PermissionError, match="current spending authority"):
        execute(db, work, operation, supplier, policy=policy)
    assert supplier.calls == 0 and balances(db) == (1500, 0)
    grant(db, operation, policy=policy)
    grant(db, operation, policy=policy)
    assert balances(db) == (1500, 0)
    assert execute(db, work, operation, supplier, policy=policy)["status"] == "ACCEPTED"
    assert supplier.calls == 1 and balances(db) == (0, 1500)
    db.close()


@pytest.mark.parametrize("discover", [True, False])
def test_reduced_authority_allows_discovery_but_never_an_unapproved_retransmission(
    tmp_path, discover
):
    db, work, operation = setup(tmp_path)
    grant(db, operation, automatic=True)
    supplier = Supplier(lose_response=True, discover=discover)
    allowed = SpendingPolicy(frozenset({"lucy"}), automatic_order_pence=2000)
    assert execute(db, work, operation, supplier, policy=allowed)["status"] == "UNKNOWN"
    reduced = SpendingPolicy(frozenset({"lucy"}), automatic_order_pence=0)
    if discover:
        assert execute(db, work, operation, supplier, policy=reduced)["status"] == "ACCEPTED"
        assert balances(db) == (0, 1500)
    else:
        with pytest.raises(PermissionError):
            execute(db, work, operation, supplier, policy=reduced)
        assert balances(db) == (1500, 0)
    assert supplier.calls == 1 and supplier.lookups == 1
    db.close()


def test_unknown_historical_approval_needs_reapproval_without_reserving_twice(
    tmp_path, monkeypatch
):
    current = database.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(database, "MIGRATIONS", tuple(item for item in current if item[0] <= 24))
        db, work, operation = setup(tmp_path)
        with db.immediate() as connection:
            connection.execute(
                "UPDATE assistant_orders SET status='APPROVED',approved_by='lucy',approved_until=?",
                (time.time() + 60,),
            )
            connection.execute(
                "INSERT INTO assistant_spending(id,limit_pence,reserved_pence) "
                "VALUES (1,20000,1500)"
            )
        db.close()
    db = Database(tmp_path / "agent.sqlite")
    assert 25 in db.applied_versions()
    assert (
        db.connection.execute("SELECT approval_basis FROM assistant_orders").fetchone()[0]
        == "UNKNOWN"
    )
    supplier = Supplier()
    policy = SpendingPolicy(frozenset({"lucy"}))
    with pytest.raises(PermissionError):
        execute(db, work, operation, supplier, policy=policy)
    assert supplier.calls == 0 and balances(db) == (1500, 0)
    grant(db, operation, policy=policy)
    assert execute(db, work, operation, supplier, policy=policy)["status"] == "ACCEPTED"
    assert balances(db) == (0, 1500)
    db.close()


@pytest.mark.parametrize("approved", [False, True])
def test_revision_revokes_prior_proposal_and_never_reuses_its_permission(tmp_path, approved):
    db, work, original = setup(tmp_path)
    policy = SpendingPolicy(frozenset({"lucy"}))
    if approved:
        grant(db, original)
    original_digest = db.connection.execute("SELECT digest FROM assistant_orders").fetchone()[0]
    revised = propose(db, work, "SKU-VANILLA", 7)
    assert original != revised
    assert tuple(
        db.connection.execute(
            "SELECT status,revoked FROM assistant_orders WHERE id=?", (original,)
        ).fetchone()
    ) == ("REVOKED", 1)
    if approved:
        assert balances(db) == (0, 0)
    assert propose(db, work, "SKU-VANILLA", 6) == original
    assert (
        db.connection.execute(
            "SELECT status FROM assistant_orders WHERE id=?", (original,)
        ).fetchone()[0]
        == "REVOKED"
    )
    supplier = Supplier()
    for operation in (original, revised):
        with pytest.raises(PermissionError):
            execute(db, work, operation, supplier, policy=policy)
    with pytest.raises(PermissionError, match="exact proposal"):
        approve(db, revised, original_digest, actor="lucy", policy=policy, expires=time.time() + 60)
    grant(db, revised, policy=policy)
    assert execute(db, work, revised, supplier, policy=policy)["status"] == "ACCEPTED"
    assert supplier.calls == 1 and balances(db) == (0, 1750)
    event = json.loads(
        db.connection.execute(
            "SELECT payload FROM events WHERE kind='assistant.order.superseded'"
        ).fetchone()[0]
    )
    assert event == {"order": original, "replacement": revised}
    db.close()


@pytest.mark.parametrize("uncertain", [False, True])
def test_transmitted_product_cannot_be_revised_into_another_purchase(tmp_path, uncertain):
    db, work, operation = setup(tmp_path)
    grant(db, operation)
    policy = SpendingPolicy(frozenset({"lucy"}))
    supplier = Supplier(lose_response=uncertain)
    execute(db, work, operation, supplier, policy=policy)
    before = balances(db)
    with pytest.raises(PermissionError, match="new purchase needs new work"):
        propose(db, work, "SKU-VANILLA", 7)
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 1
    assert balances(db) == before
    # A different product in the same assignment remains independent.
    other = propose(db, work, "SKU-STRAWBERRY", 4)
    assert other != operation and supplier.calls == 1
    db.close()


def test_non_boolean_approval_basis_cannot_be_misread_as_operator_consent(tmp_path):
    db, _, operation = setup(tmp_path)
    with pytest.raises(ValueError, match="approval basis"):
        grant(db, operation, automatic="false")
    assert db.connection.execute("SELECT status FROM assistant_orders").fetchone()[0] == "DRAFT"
    db.close()


def test_failed_revision_keeps_old_permission_and_reservation_together(tmp_path, monkeypatch):
    from sovereign_agent import assistant_orders

    db, work, original = setup(tmp_path)
    grant(db, original)
    original_event = assistant_orders.append_event

    def fail_event(db, kind, payload):
        if kind == "assistant.order.superseded":
            raise OSError("simulated event write failure")
        return original_event(db, kind, payload)

    monkeypatch.setattr(assistant_orders, "append_event", fail_event)
    with pytest.raises(OSError, match="event write"):
        propose(db, work, "SKU-VANILLA", 7)
    assert balances(db) == (1500, 0)
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 1
    assert tuple(
        db.connection.execute(
            "SELECT status,revoked FROM assistant_orders WHERE id=?", (original,)
        ).fetchone()
    ) == ("APPROVED", 0)
    db.close()
