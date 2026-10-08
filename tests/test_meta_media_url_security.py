from __future__ import annotations

import pytest

from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
    MetaMediaAPIPermanentError,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.com/media",
        "https://localhost/media",
        "https://service.localhost/media",
        "https://127.0.0.1/media",
        "https://10.0.0.1/media",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/media",
        "https://user:password@example.com/media",
        "https://cdn.example.com:8443/media",
    ],
)
def test_unsafe_meta_download_url_is_rejected(
    url: str,
) -> None:
    with pytest.raises(MetaMediaAPIPermanentError):
        MetaMediaAPIClient._validate_download_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/media",
        "https://files.example.com:443/media",
    ],
)
def test_safe_https_meta_download_url_is_allowed(
    url: str,
) -> None:
    MetaMediaAPIClient._validate_download_url(url)
