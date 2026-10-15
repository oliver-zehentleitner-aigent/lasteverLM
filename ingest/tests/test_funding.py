"""A read is funded when it is asked for: if the balance covers its
estimated maximum plus what the owner's started work holds (other funded
reads still waiting, rag's waiting and processing outputs), it is marked
and later read whatever the balance is by then."""

from decimal import Decimal
from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID


def _add(client, name, size=3000):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    r = client.post(url, files={"file": (name, b"x" * size, "text/plain")}).json()
    return r["library_id"], url


def _process(client, *ids):
    r = client.post("/api/ingest/sources/process", json={"library_ids": list(ids)})
    assert r.status_code == 200
    return r.json()


def test_funded_at_request_is_read_after_the_balance_went_negative(client, repo, run_queue):
    lib, url = _add(client, "a.txt")
    _process(client, lib)
    row = repo.library[UUID(lib)]
    assert row.funded_request_at is not None and row.funded_cents > 0
    # Something else spent the balance before a worker came to it.
    repo.credits[DEMO_USER_ID] = -5
    assert [s["status"] for s in client.get(url).json()] == ["processing"]  # not waiting
    assert run_queue() == 1
    done = repo.library[UUID(lib)]
    assert done.status == "ready" and done.funded_request_at is None and done.funded_cents is None


def test_requested_at_zero_waits(client, repo):
    lib, url = _add(client, "a.txt")
    repo.credits[DEMO_USER_ID] = 0
    _process(client, lib)
    assert repo.library[UUID(lib)].funded_request_at is None
    assert [s["status"] for s in client.get(url).json()] == ["waiting_for_credit"]
    assert repo.claim_library_source("w", 600) is None


def test_a_balance_below_the_estimate_does_not_fund_the_request(client, repo):
    lib, url = _add(client, "big.txt", size=4000)
    repo.credits[DEMO_USER_ID] = Decimal("0.0001")  # positive, but far below the estimate
    _process(client, lib)
    assert repo.library[UUID(lib)].funded_request_at is None
    assert repo.claim_library_source("w", 600) is None


def test_funded_work_still_waiting_counts_against_the_next_request(client, repo):
    first, _ = _add(client, "a.txt")
    second, _ = _add(client, "b.txt", size=3001)
    estimate = client.post(
        "/api/ingest/sources/estimate", json={"library_ids": [first, second]}
    ).json()["items"]
    one = Decimal(estimate[0]["charge_cents_max"])
    # Enough for one read, not for two.
    repo.credits[DEMO_USER_ID] = one * Decimal("1.5")
    _process(client, first)
    _process(client, second)
    assert repo.library[UUID(first)].funded_request_at is not None
    assert repo.library[UUID(second)].funded_request_at is None
    assert repo.held_cents(DEMO_USER_ID) == repo.library[UUID(first)].funded_cents


def test_a_refetch_is_funded_and_a_new_version_keeps_the_funding(client, repo):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": "https://x.test/"}).json()
    lib = UUID(r["library_id"])
    repo.set_library_status(lib, "ready")
    assert client.post(f"/api/ingest/sources/{r['id']}/refetch").status_code == 202
    held = repo.library[lib].funded_cents
    assert repo.library[lib].funded_request_at is not None and held > 0
    new = repo.new_version(lib)
    assert repo.library[new].funded_cents == held and repo.library[lib].funded_cents is None


def test_an_outputs_reservation_makes_a_queued_source_wait(client, repo):
    """Rag reserves an output's estimated maximum (outputs.reserved_cents)
    while it waits or runs; ingest holds the same sum, so a read the rest
    of the balance does not cover waits until the output is done."""
    lib, url = _add(client, "a.txt")
    estimate = client.post("/api/ingest/sources/estimate", json={"library_ids": [lib]}).json()
    needed = Decimal(estimate["items"][0]["charge_cents_max"])
    repo.credits[DEMO_USER_ID] = needed * 2
    output = uuid4()
    repo.reservations[output] = (DEMO_USER_ID, "processing", needed * Decimal("1.5"))
    _process(client, lib)
    assert repo.library[UUID(lib)].funded_request_at is None
    assert [s["status"] for s in client.get(url).json()] == ["waiting_for_credit"]
    assert repo.claim_library_source("w", 600) is None
    # The output is done: its reservation no longer counts, the read starts.
    repo.reservations[output] = (DEMO_USER_ID, "ready", needed * Decimal("1.5"))
    assert [s["status"] for s in client.get(url).json()] == ["processing"]
    assert repo.claim_library_source("w", 600) == UUID(lib)


def test_a_running_plans_explain_step_makes_a_queued_source_wait(client, repo):
    """Rag holds the estimated maximum of a running plan's explain steps;
    ingest counts the same, so the read waits until the step has run."""
    lib, url = _add(client, "a.txt")
    estimate = client.post("/api/ingest/sources/estimate", json={"library_ids": [lib]}).json()
    needed = Decimal(estimate["items"][0]["charge_cents_max"])
    repo.credits[DEMO_USER_ID] = needed * 2
    step = {
        "tool": "explain_output",
        "state": "waiting",
        "estimate": {"max": float(needed * 3 / 2)},
    }
    done = {"tool": "explain_output", "state": "done", "estimate": {"max": 1000}}
    plan = uuid4()
    repo.plans[plan] = (DEMO_USER_ID, "running", [done, step])
    _process(client, lib)
    assert repo.library[UUID(lib)].funded_request_at is None
    assert [s["status"] for s in client.get(url).json()] == ["waiting_for_credit"]
    assert repo.claim_library_source("w", 600) is None
    # The step ran: it holds nothing any more, the read starts.
    repo.plans[plan] = (DEMO_USER_ID, "running", [done, {**step, "state": "done"}])
    assert repo.claim_library_source("w", 600) == UUID(lib)
