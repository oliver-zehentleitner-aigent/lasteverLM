"""The sign-in mail offers the link and the same token as a code to paste."""

from __future__ import annotations

from lasteverlm_account.mail import magic_link_mail


def test_mail_has_link_then_code_with_one_shared_note() -> None:
    link = "https://lasteverlm.test/auth/callback?token=abc-DEF_123"
    subject, body = magic_link_mail(link, "abc-DEF_123", 15)
    assert subject == "Your lasteverLM sign-in link"
    assert body.index(link) < body.index("Or paste this code on the sign-in page:")
    assert body.index("Or paste this code on the sign-in page:") < body.index("\nabc-DEF_123\n")
    assert body.count("abc-DEF_123") == 2  # once in the link, once as the code
    assert "works once and expires in 15 minutes" in body
    assert body.count("expires in") == 1  # one note covering both ways in
