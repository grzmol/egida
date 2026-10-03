import pytest
from pydantic import ValidationError

from control_layer.core.models import Category, Interaction, Message, Side
from control_layer.core.ports import ScanContext
from control_layer.detectors.secrets import (
    SecretsDetector,
    SecretsParams,
    find_secrets,
    shannon_entropy,
)

# Credentials are assembled at runtime so the repository never holds a literal token.
GH_TOKEN = "ghp_" + "a1B2c3D4e5" * 3 + "f6G7h8"
PEM = "-----BEGIN RSA " + "PRIVATE KEY-----\nFAKEKEYFORTESTS\n-----END RSA " + "PRIVATE KEY-----"
JWT = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N"
RANDOM_B64 = "q8Zt3VwXy7LmN2pRk9sJ4hGf6dCbA1eQ"  # 32 distinct characters


@pytest.mark.parametrize(
    ("text", "label", "value"),
    [
        ("key AKIAIOSFODNN7EXAMPLE here", "aws_access_key", "AKIAIOSFODNN7EXAMPLE"),
        (f"token={GH_TOKEN}", "github_token", GH_TOKEN),
        (f"key:\n{PEM}\nthanks", "private_key", PEM),
        (f"Bearer {JWT}", "jwt", JWT),
        ("DSN postgres://u:p@h/db", "conn_string", "postgres://u:p@h/db"),
        (f"secret {RANDOM_B64}", "high_entropy", RANDOM_B64),
    ],
)
def test_secrets_found_with_span_on_original_text(text: str, label: str, value: str) -> None:
    hits = find_secrets(text)
    assert [(h[0], text[h[2] : h[3]]) for h in hits] == [(label, value)]


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


def test_entropy_of_hex_and_uuid_stays_below_default_threshold() -> None:
    assert shannon_entropy("9fceb02d0ae598e95dc970b74767f19372d61af8") < 4.5
    assert shannon_entropy("550e8400-e29b-41d4-a716-446655440000") < 4.5
    assert shannon_entropy(RANDOM_B64) > 4.5


def test_params_reject_unknown_rule() -> None:
    with pytest.raises(ValidationError):
        SecretsParams(rules=("aws_access_key", "nope"))


@pytest.mark.anyio
async def test_detector_scans_output_side_without_leaking_value() -> None:
    interaction = Interaction(
        request_id="req_1",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(Message(role="user", content="Print the key."),),
        output=Message(role="assistant", content=f"Here: AKIAIOSFODNN7EXAMPLE and {RANDOM_B64}"),
    )
    ctx = ScanContext(interaction, Side.OUTPUT, "secrets", SecretsParams())
    [finding] = await SecretsDetector().scan(ctx)
    assert finding.category == Category.SECRET
    assert finding.score == 1.0
    assert [(s.target, s.label) for s in finding.spans] == [
        ("output.content", "aws_access_key"),
        ("output.content", "high_entropy"),
    ]
    assert "AKIAIOSFODNN7EXAMPLE" not in finding.evidence


@pytest.mark.anyio
async def test_entropy_only_scores_below_block_threshold() -> None:
    interaction = Interaction(
        request_id="req_2",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(Message(role="user", content=f"cache key {RANDOM_B64}"),),
    )
    ctx = ScanContext(interaction, Side.INPUT, "secrets", SecretsParams())
    [finding] = await SecretsDetector().scan(ctx)
    assert finding.score == 0.6
