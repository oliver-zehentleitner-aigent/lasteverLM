"""Voucher codes stored encrypted: shown again, mailed, masked in the list; old rows not."""

from __future__ import annotations

import base64
import uuid

import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.config import ConfigError, Settings
from lasteverlm_account.crypto import VoucherCipher, load_key
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import FakeMailer, bearer, login

VOUCHERS = "/api/account/admin/vouchers"


def _create(client: TestClient, token: str, **body: object) -> tuple[str, str]:
    r = client.post(VOUCHERS, json={"amount_cents": 1250, **body}, headers=bearer(token))
    assert r.status_code == 201, r.text
    code = r.json()["codes"][0]
    for row in client.get(VOUCHERS, headers=bearer(token)).json():  # same timestamp: match
        vid = row["id"]
        if client.get(f"{VOUCHERS}/{vid}/code", headers=bearer(token)).json().get("code") == code:
            return code, vid
    raise AssertionError("created voucher not listed")


def test_code_is_encrypted_at_rest_and_shown_again(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    code, vid = _create(client, token)
    stored = next(iter(repo.vouchers.values()))
    assert stored.code_enc and code not in stored.code_enc
    r = client.get(f"{VOUCHERS}/{vid}/code", headers=bearer(token))
    assert r.status_code == 200 and r.json() == {"code": code}
    row = client.get(VOUCHERS, headers=bearer(token)).json()[0]
    assert row["recoverable"] is True and row["code_masked"] == f"{code[:4]}-****-****-****"
    assert code not in client.get(VOUCHERS, headers=bearer(token)).text
    # redeem still works through the hash
    r = client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(token))
    assert r.status_code == 200


def test_old_vouchers_are_not_recoverable(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    _, vid = _create(client, token)
    next(iter(repo.vouchers.values())).code_enc = None  # as created before migration 0008
    r = client.get(f"{VOUCHERS}/{vid}/code", headers=bearer(token))
    assert r.status_code == 404 and r.json()["code"] == "not_recoverable"
    row = client.get(VOUCHERS, headers=bearer(token)).json()[0]
    assert row["recoverable"] is False and row["code_masked"] is None
    r = client.post(
        f"{VOUCHERS}/{vid}/send", json={"email": "x@example.org"}, headers=bearer(token)
    )
    assert r.status_code == 404 and r.json()["code"] == "not_recoverable"
    r = client.get(f"{VOUCHERS}/{uuid.uuid4()}/code", headers=bearer(token))
    assert r.status_code == 404 and "code" not in r.json()


def test_send_mails_the_code_allowlists_and_records(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    code, vid = _create(client, token)
    r = client.post(
        f"{VOUCHERS}/{vid}/send",
        json={"email": "Friend@Outside.test", "message": "Viel Spass!"},
        headers=bearer(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["sent_to"] == "friend@outside.test" and r.json()["sent_at"]
    mail = mailer.sent[-1]
    assert mail.to == "friend@outside.test"
    assert mail.subject == "You received a lasteverLM voucher of €12.50"
    assert code in mail.body and "https://lasteverlm.test" in mail.body
    assert "A note from the sender:\nViel Spass!" in mail.body
    allow = client.get("/api/account/admin/settings/allowlist", headers=bearer(token)).json()
    assert "friend@outside.test" in allow["allowed_addresses"]
    # allow on an address already covered by a domain changes nothing
    _, vid2 = _create(client, token)
    client.post(f"{VOUCHERS}/{vid2}/send", json={"email": "a@example.org"}, headers=bearer(token))
    allow = client.get("/api/account/admin/settings/allowlist", headers=bearer(token)).json()
    assert "a@example.org" not in allow["allowed_addresses"]
    # allow false leaves the allowlist alone
    _, vid3 = _create(client, token)
    client.post(
        f"{VOUCHERS}/{vid3}/send",
        json={"email": "solo@elsewhere.test", "allow": False},
        headers=bearer(token),
    )
    allow = client.get("/api/account/admin/settings/allowlist", headers=bearer(token)).json()
    assert "solo@elsewhere.test" not in allow["allowed_addresses"]


def test_send_refuses_redeemed_quota_and_mail_failure(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    code, vid = _create(client, token)
    client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(token))
    r = client.post(
        f"{VOUCHERS}/{vid}/send", json={"email": "b@example.org"}, headers=bearer(token)
    )
    assert r.status_code == 409 and r.json()["code"] == "already_redeemed"
    for _ in range(5):
        _, v = _create(client, token)
        r = client.post(
            f"{VOUCHERS}/{v}/send", json={"email": "c@example.org"}, headers=bearer(token)
        )
        assert r.status_code == 200
    _, v = _create(client, token)
    r = client.post(f"{VOUCHERS}/{v}/send", json={"email": "c@example.org"}, headers=bearer(token))
    assert r.status_code == 429 and r.json()["code"] == "too_many_mails"
    mailer.fail = True
    r = client.post(f"{VOUCHERS}/{v}/send", json={"email": "d@example.org"}, headers=bearer(token))
    assert r.status_code == 502 and r.json()["code"] == "mail_failed"
    long = "x" * 1001
    r = client.post(
        f"{VOUCHERS}/{v}/send",
        json={"email": "d@example.org", "message": long},
        headers=bearer(token),
    )
    assert r.status_code == 422


def test_create_with_send_to_mails_each_voucher(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    before = len(mailer.sent)
    r = client.post(
        VOUCHERS,
        json={"amount_cents": 500, "count": 2, "send_to": "team@example.org"},
        headers=bearer(token),
    )
    assert r.status_code == 201 and len(r.json()["codes"]) == 2
    sent = mailer.sent[before:]
    assert [m.to for m in sent] == ["team@example.org"] * 2
    assert {c for c in r.json()["codes"]} == {
        c for m in sent for c in r.json()["codes"] if c in m.body
    }


def test_german_mail_for_a_german_admin(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    client.put("/api/account/me/preferences", json={"ui_language": "de"}, headers=bearer(token))
    _, vid = _create(client, token)
    client.post(f"{VOUCHERS}/{vid}/send", json={"email": "e@example.org"}, headers=bearer(token))
    assert mailer.sent[-1].subject == "Dein lasteverLM-Gutschein über 12,50 €"


def test_viewer_cannot_see_codes(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    _, vid = _create(client, token)
    _, viewer = login(client, mailer, "v@example.org")
    client.patch(
        f"/api/account/admin/users/{viewer['id']}", json={"role": "viewer"}, headers=bearer(token)
    )
    vtoken, _ = login(client, mailer, "v@example.org")
    assert client.get(f"{VOUCHERS}/{vid}/code", headers=bearer(vtoken)).status_code == 403


def test_key_must_be_32_base64_bytes() -> None:
    good = base64.b64encode(b"k" * 32).decode()
    assert load_key(good) == b"k" * 32
    assert load_key(base64.urlsafe_b64encode(b"\xff" * 32).decode().rstrip("=")) == b"\xff" * 32
    env = {"DATABASE_URL": "x", "AUTH_JWT_SECRET": "y", "PUBLIC_BASE_URL": "https://z"}
    for bad in (None, "", "not base64!!", base64.b64encode(b"short").decode()):
        with pytest.raises(ConfigError, match="VOUCHER_KEY"):
            Settings.from_env({**env, **({"VOUCHER_KEY": bad} if bad is not None else {})})
    cipher, other = VoucherCipher(b"a" * 32), VoucherCipher(b"b" * 32)
    token = cipher.encrypt("ABCD-EFGH-JKLM-NPQR")
    assert cipher.decrypt(token) == "ABCD-EFGH-JKLM-NPQR"
    assert other.decrypt(token) is None and cipher.decrypt("garbage") is None
