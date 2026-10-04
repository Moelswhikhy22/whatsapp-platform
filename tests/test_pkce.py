from app.auth.pkce import (
    create_code_challenge,
    generate_code_verifier,
)


def test_generate_code_verifier_has_valid_length() -> None:
    verifier = generate_code_verifier()

    assert 43 <= len(verifier) <= 128


def test_create_code_challenge_matches_rfc_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    challenge = create_code_challenge(verifier)

    assert challenge == ("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
