"""A judgement on request runs as a job: queued by the request, run by the
worker with its phase, retried on a passing failure, stored on its target."""

from .conftest import AUTH, OWNER, FakeStore
from .test_judging import judges, report, run


class Boom:
    """A judge model whose calls fail with something unexpected."""

    model = "test-judge-boom"

    def complete(self, system, user, max_tokens=None, *, thinking=None):
        raise RuntimeError("boom")


def queued(settings, **models):
    judge_models = {**judges(), **models}
    client, store, _, _, out = run(
        settings,
        "report",
        {},
        report("The sky is blue. [1]", "The sky is wrong red. [1]"),
        judge_models=judge_models,
    )
    path = f"/api/rag/outputs/{out['id']}/judge"
    return client, store, out["id"], path


def test_a_judgement_is_queued_run_by_the_worker_and_stored(settings):
    client, store, output_id, path = queued(settings)
    phases = []
    original = store.update_judge_job

    def recording(job_id, **fields):
        if fields.get("phase"):
            phases.append((fields["phase"]["n"], fields["phase"]["of"]))
        original(job_id, **fields)

    store.update_judge_job = recording
    r = client.post(path, json={"level": "high"}, headers=AUTH)
    assert r.status_code == 202, r.text
    job = r.json()
    assert (job["status"], job["target"], job["target_id"], job["level"]) == (
        "queued",
        "output",
        output_id,
        "high",
    )
    # one at a time per target
    again = client.post(path, json={"level": "low"}, headers=AUTH)
    assert (again.status_code, again.json()) == (
        409,
        {"error": "a judgement is already running", "job_id": job["job_id"]},
    )
    client.worker.run_once()
    done = client.get(f"/api/rag/judge-jobs/{job['job_id']}", headers=AUTH).json()
    assert (done["status"], done["phase"], done["attempts"]) == ("done", None, 1)
    assert done["finished_at"]
    assert phases[0] == (0, 2) and phases[-1] == (2, 2)
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert [u["judge"]["verdict"] for u in out["content"]["units"]] == ["supported", "contradicted"]
    assert client.get(path, headers=AUTH).json()["job_id"] == job["job_id"]
    # a new judgement may start once the last one ended
    assert client.post(path, json={"level": "low"}, headers=AUTH).status_code == 202


def test_a_failing_judgement_is_retried_then_failed_with_its_attempts(settings):
    client, store, _, path = queued(settings, high=Boom())
    job_id = client.post(path, json={"level": "high"}, headers=AUTH).json()["job_id"]
    for _ in range(3):
        client.worker.run_once()
    job = client.get(f"/api/rag/judge-jobs/{job_id}", headers=AUTH).json()
    assert (job["status"], job["attempts"]) == ("failed", 3)
    assert [a["attempt"] for a in job["attempt_log"]] == [1, 2, 3]
    assert job["attempt_log"][0]["error_kind"] == "internal"
    assert job["error"]


def test_a_target_gone_fails_the_judgement_at_once(settings):
    client, store, output_id, path = queued(settings)
    job_id = client.post(path, json={"level": "high"}, headers=AUTH).json()["job_id"]
    store.outputs[output_id]["deleted_at"] = "2026-10-15T12:00:00+00:00"  # trashed meanwhile
    client.worker.run_once()
    job = client.get(f"/api/rag/judge-jobs/{job_id}", headers=AUTH).json()
    assert (job["status"], job["attempts"]) == ("failed", 1)


def test_only_the_owner_reads_a_judgement(settings):
    client, store, output_id, path = queued(settings)
    job_id = client.post(path, json={"level": "high"}, headers=AUTH).json()["job_id"]
    store.judge_jobs[job_id]["owner"] = "someone-else"
    r = client.get(f"/api/rag/judge-jobs/{job_id}", headers=AUTH)
    assert (r.status_code, r.json()) == (404, {"error": "no judgement"})
    assert client.get(path, headers=AUTH).status_code == 404
    assert OWNER != "someone-else" and isinstance(store, FakeStore)
