from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx


_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")


class MetaCredentialValidationError(RuntimeError):
    pass


class MetaCredentialValidationRetryableError(MetaCredentialValidationError):
    pass


class MetaCredentialRejectedError(MetaCredentialValidationError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class MetaPhoneNumberValidationResult:
    phone_number_id: str


class MetaCredentialValidationClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._http_client = http_client

    async def validate_phone_number(
        self,
        *,
        graph_api_version: str,
        phone_number_id: str,
        access_token: str,
    ) -> MetaPhoneNumberValidationResult:
        version = self._validate_version(graph_api_version)

        normalized_phone_id = phone_number_id.strip()

        if not normalized_phone_id:
            raise MetaCredentialRejectedError("Meta phone number ID is empty.")

        safe_phone_id = quote(
            normalized_phone_id,
            safe="",
        )

        url = f"https://graph.facebook.com/{version}/{safe_phone_id}"

        try:
            response = await self._http_client.get(
                url,
                headers={
                    "Authorization": (f"Bearer {access_token}"),
                },
                params={
                    "fields": ("id,display_phone_number,verified_name"),
                },
            )

        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise (
                MetaCredentialValidationRetryableError(
                    "Meta credential validation request failed transiently."
                )
            ) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise (
                MetaCredentialValidationRetryableError(
                    "Meta credential validation is temporarily unavailable."
                )
            )

        if not response.is_success:
            raise MetaCredentialRejectedError("Meta rejected the configured access token.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise (
                MetaCredentialValidationRetryableError(
                    "Meta returned an invalid validation response."
                )
            ) from exc

        if not isinstance(payload, dict):
            raise (
                MetaCredentialValidationRetryableError(
                    "Meta returned an invalid validation response."
                )
            )

        returned_id = payload.get("id")

        if not isinstance(returned_id, str) or returned_id != normalized_phone_id:
            raise MetaCredentialRejectedError(
                "Meta validation returned a different phone number resource."
            )

        return MetaPhoneNumberValidationResult(phone_number_id=returned_id)

    @staticmethod
    def _validate_version(
        value: str,
    ) -> str:
        normalized = value.strip()

        if not _GRAPH_VERSION_PATTERN.fullmatch(normalized):
            raise MetaCredentialRejectedError("Invalid Meta Graph API version configuration.")

        return normalized
