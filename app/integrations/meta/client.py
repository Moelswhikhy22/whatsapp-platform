from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote
from time import perf_counter
import httpx

from app.observability.external_metrics import (
    external_dependency_metrics,
)

_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")

_RETRYABLE_META_ERROR_CODES = frozenset(
    {
        130429,
        131048,
        131056,
    }
)


@dataclass(
    frozen=True,
    slots=True,
)
class MetaSendMessageResult:
    meta_message_id: str


class MetaCloudAPIError(RuntimeError):
    pass


class MetaCloudAPIRetryableError(MetaCloudAPIError):
    pass


class MetaCloudAPIPermanentError(MetaCloudAPIError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        meta_error_code: int | None = None,
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.meta_error_code = meta_error_code


class MetaCloudAPIAmbiguousResponseError(MetaCloudAPIError):
    """
    Meta returned HTTP success but the
    response could not be correlated
    to a wamid.

    Retrying automatically could
    duplicate an already accepted
    WhatsApp message.
    """


class MetaCloudAPIClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._http_client = http_client

    async def send_text(
        self,
        *,
        graph_api_version: str,
        phone_number_id: str,
        recipient_phone: str,
        body_text: str,
        access_token: str,
    ) -> MetaSendMessageResult:
        started_at = perf_counter()

        try:
            result = await self._send_message(
                graph_api_version=graph_api_version,
                phone_number_id=phone_number_id,
                access_token=access_token,
                payload={
                    "messaging_product": "whatsapp",
                    "to": recipient_phone,
                    "type": "text",
                    "text": {
                        "body": body_text,
                        "preview_url": False,
                    },
                },
            )

        except MetaCloudAPIRetryableError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_text",
                outcome="retryable_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        except MetaCloudAPIPermanentError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_text",
                outcome="permanent_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        except MetaCloudAPIAmbiguousResponseError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_text",
                outcome="ambiguous_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        else:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_text",
                outcome="success",
                duration_seconds=(perf_counter() - started_at),
            )

            return result

    async def send_template(
        self,
        *,
        graph_api_version: str,
        phone_number_id: str,
        recipient_phone: str,
        template_name: str,
        language: str,
        components: list[dict[str, object]],
        access_token: str,
    ) -> MetaSendMessageResult:
        started_at = perf_counter()

        template_payload: dict[
            str,
            object,
        ] = {
            "name": template_name,
            "language": {
                "code": language,
            },
        }

        if components:
            template_payload["components"] = components

        try:
            result = await self._send_message(
                graph_api_version=graph_api_version,
                phone_number_id=phone_number_id,
                access_token=access_token,
                payload={
                    "messaging_product": "whatsapp",
                    "to": recipient_phone,
                    "type": "template",
                    "template": template_payload,
                },
            )

        except MetaCloudAPIRetryableError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_template",
                outcome="retryable_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        except MetaCloudAPIPermanentError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_template",
                outcome="permanent_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        except MetaCloudAPIAmbiguousResponseError:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_template",
                outcome="ambiguous_failure",
                duration_seconds=(perf_counter() - started_at),
            )
            raise

        else:
            external_dependency_metrics.observe(
                dependency="meta",
                operation="send_template",
                outcome="success",
                duration_seconds=(perf_counter() - started_at),
            )

            return result
    async def _send_message(
        self,
        *,
        operation: str,
        graph_api_version: str,
        phone_number_id: str,
        access_token: str,
        payload: dict[str, object],
    ) -> MetaSendMessageResult:
        version = self._validate_version(graph_api_version)

        safe_phone_number_id = quote(
            phone_number_id,
            safe="",
        )

        url = f"https://graph.facebook.com/{version}/{safe_phone_number_id}/messages"

        started_at = perf_counter()

        outcome = "failure"

        try:
            try:
                response = await self._http_client.post(
                    url,
                    headers={
                        "Authorization": (f"Bearer {access_token}"),
                        "Content-Type": ("application/json"),
                    },
                    json=payload,
                )

            except (
                httpx.TimeoutException,
                httpx.TransportError,
            ) as exc:
                raise (
                    MetaCloudAPIRetryableError(("Meta Cloud API request failed transiently."))
                ) from exc

            response_payload = self._decode_json(response)

            if response.status_code == 429 or response.status_code >= 500:
                raise (
                    MetaCloudAPIRetryableError(("Meta Cloud API returned a retryable HTTP status."))
                )

            meta_error_code = self._extract_error_code(response_payload)

            if meta_error_code in _RETRYABLE_META_ERROR_CODES:
                raise (
                    MetaCloudAPIRetryableError(
                        ("Meta Cloud API returned a retryable provider error.")
                    )
                )

            if not response.is_success:
                raise (
                    MetaCloudAPIPermanentError(
                        ("Meta Cloud API rejected the outbound message."),
                        status_code=(response.status_code),
                        meta_error_code=(meta_error_code),
                    )
                )

            meta_message_id = self._extract_message_id(response_payload)

            if meta_message_id is None:
                raise (
                    MetaCloudAPIAmbiguousResponseError(
                        ("Meta returned success without a message ID.")
                    )
                )

            outcome = "success"

            return MetaSendMessageResult(
                meta_message_id=(meta_message_id),
            )

        finally:
            external_dependency_metrics.observe(
                dependency="meta",
                operation=operation,
                outcome=outcome,
                duration_seconds=max(
                    perf_counter() - started_at,
                    0.0,
                ),
            )

    @staticmethod
    def _validate_version(
        value: str,
    ) -> str:
        normalized = value.strip()

        if not (_GRAPH_VERSION_PATTERN.fullmatch(normalized)):
            raise (MetaCloudAPIPermanentError(("Invalid Meta Graph API version configuration.")))

        return normalized

    @staticmethod
    def _decode_json(
        response: httpx.Response,
    ) -> dict[str, object]:
        try:
            decoded = response.json()

        except ValueError:
            return {}

        if not isinstance(
            decoded,
            dict,
        ):
            return {}

        return cast(
            dict[str, object],
            decoded,
        )

    @staticmethod
    def _extract_error_code(
        payload: dict[str, object],
    ) -> int | None:
        raw_error = payload.get("error")

        if not isinstance(
            raw_error,
            dict,
        ):
            return None

        error = cast(
            dict[str, object],
            raw_error,
        )

        raw_code = error.get("code")

        if isinstance(
            raw_code,
            int,
        ) and not isinstance(
            raw_code,
            bool,
        ):
            return raw_code

        return None

    @staticmethod
    def _extract_message_id(
        payload: dict[str, object],
    ) -> str | None:
        raw_messages = payload.get("messages")

        if (
            not isinstance(
                raw_messages,
                list,
            )
            or not raw_messages
        ):
            return None

        raw_message = raw_messages[0]

        if not isinstance(
            raw_message,
            dict,
        ):
            return None

        message = cast(
            dict[str, object],
            raw_message,
        )

        raw_id = message.get("id")

        if (
            not isinstance(
                raw_id,
                str,
            )
            or not raw_id
        ):
            return None

        return raw_id
