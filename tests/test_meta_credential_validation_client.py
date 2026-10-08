from __future__ import annotations

import httpx
import pytest

from app.integrations.meta.credential_validation import (
    MetaCredentialRejectedError,
    MetaCredentialValidationClient,
)


@pytest.mark.asyncio
async def test_meta_phone_number_validation_succeeds() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"

        assert request.url.path == "/v99.0/123456"

        return httpx.Response(
            200,
            json={
                "id": "123456",
                "display_phone_number": ("+201111111111"),
                "verified_name": ("Example"),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = MetaCredentialValidationClient(http_client)

        result = await client.validate_phone_number(
            graph_api_version="v99.0",
            phone_number_id="123456",
            access_token=("secret-token"),
        )

    assert result.phone_number_id == ("123456")


@pytest.mark.asyncio
async def test_meta_rejected_token_is_invalid() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            401,
            json={"error": {"message": ("Invalid token")}},
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCredentialValidationClient(http_client)

        with pytest.raises(MetaCredentialRejectedError):
            await client.validate_phone_number(
                graph_api_version=("v99.0"),
                phone_number_id=("123456"),
                access_token="bad",
            )
