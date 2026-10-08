from __future__ import annotations

import ipaddress

import pytest

from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidationError,
    WebhookEndpointValidator,
)


@pytest.mark.asyncio
async def test_public_https_endpoint_is_allowed() -> None:
    async def resolver(
        host: str,
        port: int,
    ):
        assert host == "example.com"
        assert port == 443

        return {ipaddress.ip_address("8.8.8.8")}

    validator = WebhookEndpointValidator(resolver=resolver)

    result = await validator.validate("https://example.com/hooks")

    assert result == ("https://example.com/hooks")


@pytest.mark.asyncio
async def test_private_endpoint_is_rejected() -> None:
    async def resolver(
        host: str,
        port: int,
    ):
        return {ipaddress.ip_address("10.10.1.20")}

    validator = WebhookEndpointValidator(resolver=resolver)

    with pytest.raises(WebhookEndpointValidationError):
        await validator.validate("https://example.com/hooks")


@pytest.mark.asyncio
async def test_http_endpoint_is_rejected() -> None:
    validator = WebhookEndpointValidator()

    with pytest.raises(WebhookEndpointValidationError):
        await validator.validate("http://example.com/hooks")


@pytest.mark.asyncio
async def test_url_credentials_are_rejected() -> None:
    validator = WebhookEndpointValidator()

    with pytest.raises(WebhookEndpointValidationError):
        await validator.validate(("https://user:password@example.com/hooks"))
