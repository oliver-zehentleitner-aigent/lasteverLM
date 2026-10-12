"""The seams between this service and core: token resolution and the
rate-limit middleware, as the API sees them."""

import datetime as dt
from uuid import UUID, uuid4

import jwt
from fastapi.testclient import TestClient
from lasteverlm_core import MemoryRateLimitStore

from lasteverlm_ingest.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeEmbedder, FakeSummarizer, InMemoryRepository, InMemoryStorage


def app_with(repo, **env):
    return create_app(
        make_settings(**env),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=InMemoryStorage(),
        embedder=FakeEmbedder(),
        summarizer=FakeSummarizer(),
    )


def test_jwt_from_the_account_service_is_accepted_beside_the_demo_token():
    repo = InMemoryRepository()
    secret = "s" * 32
    user = uuid4()
    token = jwt.encode(
        {
            "sub": str(user),
            "iss": "lasteverlm",
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    with TestClient(app_with(repo, AUTH_JWT_SECRET=secret)) as c:
        r = c.post(
            "/api/ingest/notebooks",
            json={"title": "mine"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert repo.notebooks[UUID(r.json()["id"])][0] == user
        demo = c.get("/api/ingest/notebooks", headers={"Authorization": "Bearer test-demo-token"})
        assert demo.status_code == 200 and demo.json() == []
        bad = c.get("/api/ingest/notebooks", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401 and bad.json() == {"error": "invalid bearer token"}


def test_rate_limit_middleware_answers_429_before_the_app():
    with TestClient(app_with(InMemoryRepository(), RATE_LIMIT_PER_MINUTE="2")) as c:
        statuses = [c.get("/api/ingest/notebooks").status_code for _ in range(4)]
    assert statuses[:2] == [401, 401]
    assert 429 in statuses[2:]
