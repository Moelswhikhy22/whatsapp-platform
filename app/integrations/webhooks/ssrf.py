from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

Resolver = Callable[
    [str, int],
    Awaitable[set[IPAddress]],
]


class WebhookEndpointValidationError(ValueError):
    pass


class WebhookEndpointValidator:
    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
    ) -> None:
        self._resolver = resolver if resolver is not None else self._resolve_addresses

    async def validate(
        self,
        endpoint_url: str,
    ) -> str:
        normalized = endpoint_url.strip()

        if not normalized:
            raise WebhookEndpointValidationError("Webhook endpoint URL must not be blank.")

        parsed = urlsplit(normalized)

        if parsed.scheme.lower() != "https":
            raise WebhookEndpointValidationError("Webhook endpoint must use HTTPS.")

        if parsed.username is not None:
            raise WebhookEndpointValidationError("Webhook URL must not contain credentials.")

        if parsed.password is not None:
            raise WebhookEndpointValidationError("Webhook URL must not contain credentials.")

        if parsed.fragment:
            raise WebhookEndpointValidationError("Webhook URL must not contain a fragment.")

        hostname = parsed.hostname

        if hostname is None:
            raise WebhookEndpointValidationError("Webhook URL has no hostname.")

        try:
            port = parsed.port
        except ValueError as exc:
            raise WebhookEndpointValidationError("Webhook URL contains an invalid port.") from exc

        resolved_port = port if port is not None else 443

        addresses = await self._resolver(
            hostname,
            resolved_port,
        )

        if not addresses:
            raise WebhookEndpointValidationError("Webhook hostname could not be resolved.")

        if any(not address.is_global for address in addresses):
            raise WebhookEndpointValidationError(
                ("Webhook endpoint resolves to a non-public address.")
            )

        return normalized

    @staticmethod
    async def _resolve_addresses(
        hostname: str,
        port: int,
    ) -> set[IPAddress]:
        loop = asyncio.get_running_loop()

        try:
            results = await loop.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror as exc:
            raise WebhookEndpointValidationError("Webhook hostname could not be resolved.") from exc

        addresses: set[IPAddress] = set()

        for result in results:
            raw_address = result[4][0]

            try:
                addresses.add(ipaddress.ip_address(raw_address))
            except ValueError:
                continue

        return addresses
