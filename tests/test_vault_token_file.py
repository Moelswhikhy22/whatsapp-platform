from __future__ import annotations

from pathlib import Path

import pytest

from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)


def test_token_and_token_file_are_mutually_exclusive(
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text(
        "file-token",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        VaultClient(
            VaultClientConfig(
                url="http://vault:8200",
                token="direct-token",
                token_file=str(token_file),
            )
        )
