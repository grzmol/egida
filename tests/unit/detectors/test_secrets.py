import pytest

from control_layer.detectors.secrets import find_secrets

# Credentials are assembled at runtime so the repository never holds a literal token.
GH_TOKEN = "ghp_" + "a1B2c3D4e5" * 3 + "f6G7h8"
PEM = "-----BEGIN RSA " + "PRIVATE KEY-----\nFAKEKEYFORTESTS\n-----END RSA " + "PRIVATE KEY-----"
JWT = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N"


@pytest.mark.parametrize(
    ("text", "label", "value"),
    [
        ("key AKIAIOSFODNN7EXAMPLE here", "aws_access_key", "AKIAIOSFODNN7EXAMPLE"),
        (f"token={GH_TOKEN}", "github_token", GH_TOKEN),
        (f"key:\n{PEM}\nthanks", "private_key", PEM),
        (f"Bearer {JWT}", "jwt", JWT),
        ("DSN postgres://u:p@h/db", "connection_string", "postgres://u:p@h/db"),
    ],
)
def test_secrets_found_with_span_on_original_text(text: str, label: str, value: str) -> None:
    hits = find_secrets(text)
    assert [(h[0], text[h[1] : h[2]]) for h in hits] == [(label, value)]


@pytest.mark.parametrize(
    "text",
    [
        "Jak skonfigurować AWS CLI?",
        "Commit 9fceb02d0ae598e95dc970b74767f19372d61af8",
        "id 550e8400-e29b-41d4-a716-446655440000",
        "See https://example.com/docs?page=2",
        "-----BEGIN PUBLIC KEY-----",
    ],
)
def test_secret_look_alikes_pass(text: str) -> None:
    assert find_secrets(text) == []
