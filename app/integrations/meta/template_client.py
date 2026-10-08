from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import parse_qs, quote, urlparse

import httpx


_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")

_MAX_TEMPLATE_PAGES = 100


@dataclass(frozen=True, slots=True)
class MetaTemplateSubmissionResult:
    provider_template_id: str | None
    provider_status: str | None


@dataclass(frozen=True, slots=True)
class MetaRemoteTemplate:
    provider_template_id: str | None
    name: str
    language: str
    category: str
    status: str
    components: list[dict[str, object]]


class MetaTemplateAPIError(RuntimeError):
    pass


class MetaTemplateAPIRetryableError(MetaTemplateAPIError):
    pass


class MetaTemplateAPIPermanentError(MetaTemplateAPIError):
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


class MetaTemplateAPIClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._http_client = http_client

    async def submit_template(
        self,
        *,
        graph_api_version: str,
        waba_id: str,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, object]],
        access_token: str,
    ) -> MetaTemplateSubmissionResult:
        version = self._validate_version(graph_api_version)

        normalized_waba_id = self._validate_waba_id(waba_id)

        url = self._templates_url(
            version=version,
            waba_id=normalized_waba_id,
        )

        try:
            response = await self._http_client.post(
                url,
                headers=self._headers(access_token),
                json={
                    "name": name,
                    "language": language,
                    "category": category,
                    "components": components,
                },
            )
        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise MetaTemplateAPIRetryableError(
                ("Meta template request failed transiently.")
            ) from exc

        payload = self._decode_json(response)

        self._raise_for_response(
            response=response,
            payload=payload,
            permanent_message=("Meta rejected the template submission."),
        )

        return MetaTemplateSubmissionResult(
            provider_template_id=(self._optional_string(payload.get("id"))),
            provider_status=(self._optional_string(payload.get("status"))),
        )

    async def fetch_templates(
        self,
        *,
        graph_api_version: str,
        waba_id: str,
        access_token: str,
    ) -> list[MetaRemoteTemplate]:
        version = self._validate_version(graph_api_version)

        normalized_waba_id = self._validate_waba_id(waba_id)

        url = self._templates_url(
            version=version,
            waba_id=normalized_waba_id,
        )

        templates: list[MetaRemoteTemplate] = []

        after: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(_MAX_TEMPLATE_PAGES):
            params: dict[str, str] = {
                "fields": ("id,name,language,category,status,components"),
                "limit": "100",
            }

            if after is not None:
                params["after"] = after

            try:
                response = await self._http_client.get(
                    url,
                    headers=self._headers(access_token),
                    params=params,
                )
            except (
                httpx.TimeoutException,
                httpx.TransportError,
            ) as exc:
                raise (
                    MetaTemplateAPIRetryableError(
                        ("Meta template sync request failed transiently.")
                    )
                ) from exc

            payload = self._decode_json(response)

            self._raise_for_response(
                response=response,
                payload=payload,
                permanent_message=("Meta rejected the template sync request."),
            )

            templates.extend(self._parse_template_page(payload))

            next_after = self._next_after_cursor(payload)

            if next_after is None:
                return templates

            if next_after in seen_cursors:
                raise (
                    MetaTemplateAPIRetryableError(("Meta template pagination repeated a cursor."))
                )

            seen_cursors.add(next_after)
            after = next_after

        raise MetaTemplateAPIRetryableError(("Meta template pagination exceeded the safety limit."))

    @staticmethod
    def _headers(
        access_token: str,
    ) -> dict[str, str]:
        return {
            "Authorization": (f"Bearer {access_token}"),
            "Content-Type": ("application/json"),
        }

    @staticmethod
    def _templates_url(
        *,
        version: str,
        waba_id: str,
    ) -> str:
        return f"https://graph.facebook.com/{version}/{quote(waba_id, safe='')}/message_templates"

    @staticmethod
    def _validate_version(
        value: str,
    ) -> str:
        normalized = value.strip()

        if not _GRAPH_VERSION_PATTERN.fullmatch(normalized):
            raise (MetaTemplateAPIPermanentError(("Invalid Meta Graph API version configuration.")))

        return normalized

    @staticmethod
    def _validate_waba_id(
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise (MetaTemplateAPIPermanentError("Meta WABA ID is missing."))

        return normalized

    @classmethod
    def _raise_for_response(
        cls,
        *,
        response: httpx.Response,
        payload: dict[str, object],
        permanent_message: str,
    ) -> None:
        if (
            response.status_code == 429
            or response.status_code >= 500
            or cls._is_transient_error(payload)
        ):
            raise (
                MetaTemplateAPIRetryableError(("Meta template API returned a transient failure."))
            )

        if response.is_success:
            return

        raise MetaTemplateAPIPermanentError(
            permanent_message,
            status_code=(response.status_code),
            meta_error_code=(cls._extract_error_code(payload)),
        )

    @classmethod
    def _parse_template_page(
        cls,
        payload: dict[str, object],
    ) -> list[MetaRemoteTemplate]:
        raw_data = payload.get("data")

        if not isinstance(
            raw_data,
            list,
        ):
            raise (MetaTemplateAPIRetryableError(("Meta template API returned invalid data.")))

        templates: list[MetaRemoteTemplate] = []

        for raw_item in raw_data:
            if not isinstance(
                raw_item,
                dict,
            ):
                raise (
                    MetaTemplateAPIRetryableError(
                        ("Meta template API returned an invalid template record.")
                    )
                )

            item = cast(
                dict[str, object],
                raw_item,
            )

            name = cls._required_string(
                item,
                "name",
            )
            language = cls._required_string(
                item,
                "language",
            )
            category = cls._required_string(
                item,
                "category",
            )
            provider_status = cls._required_string(
                item,
                "status",
            )

            raw_components = item.get("components")

            if not isinstance(
                raw_components,
                list,
            ):
                raise (
                    MetaTemplateAPIRetryableError(
                        ("Meta template API returned invalid components.")
                    )
                )

            components: list[dict[str, object]] = []

            for component in raw_components:
                if not isinstance(
                    component,
                    dict,
                ):
                    raise (MetaTemplateAPIRetryableError(("Meta template component is invalid.")))

                components.append(dict(component))

            templates.append(
                MetaRemoteTemplate(
                    provider_template_id=(cls._optional_string(item.get("id"))),
                    name=name,
                    language=language,
                    category=category,
                    status=provider_status,
                    components=components,
                )
            )

        return templates

    @classmethod
    def _required_string(
        cls,
        payload: dict[str, object],
        key: str,
    ) -> str:
        value = cls._optional_string(payload.get(key))

        if value is None:
            raise (MetaTemplateAPIRetryableError((f"Meta template API response is missing {key}.")))

        return value

    @staticmethod
    def _next_after_cursor(
        payload: dict[str, object],
    ) -> str | None:
        raw_paging = payload.get("paging")

        if not isinstance(
            raw_paging,
            dict,
        ):
            return None

        paging = cast(
            dict[str, object],
            raw_paging,
        )

        raw_next = paging.get("next")

        if not isinstance(
            raw_next,
            str,
        ):
            return None

        parsed = urlparse(raw_next)

        if parsed.scheme != "https" or parsed.hostname != "graph.facebook.com":
            raise (MetaTemplateAPIRetryableError(("Meta template pagination URL is invalid.")))

        query = parse_qs(parsed.query)

        values = query.get("after")

        if not values:
            return None

        cursor = values[0].strip()

        return cursor or None

    @staticmethod
    def _decode_json(
        response: httpx.Response,
    ) -> dict[str, object]:
        try:
            decoded = response.json()
        except ValueError:
            return {}

        if not isinstance(decoded, dict):
            return {}

        return cast(
            dict[str, object],
            decoded,
        )

    @classmethod
    def _extract_error_code(
        cls,
        payload: dict[str, object],
    ) -> int | None:
        error = cls._error_object(payload)

        if error is None:
            return None

        raw_code = error.get("code")

        if isinstance(raw_code, int) and not isinstance(
            raw_code,
            bool,
        ):
            return raw_code

        return None

    @classmethod
    def _is_transient_error(
        cls,
        payload: dict[str, object],
    ) -> bool:
        error = cls._error_object(payload)

        if error is None:
            return False

        return error.get("is_transient") is True

    @staticmethod
    def _error_object(
        payload: dict[str, object],
    ) -> dict[str, object] | None:
        raw_error = payload.get("error")

        if not isinstance(
            raw_error,
            dict,
        ):
            return None

        return cast(
            dict[str, object],
            raw_error,
        )

    @staticmethod
    def _optional_string(
        value: object,
    ) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None

        return value.strip()
