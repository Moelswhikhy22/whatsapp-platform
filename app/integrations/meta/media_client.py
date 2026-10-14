from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from time import perf_counter
from typing import cast
from urllib.parse import urlparse
import httpx

from app.observability.external_metrics import (
    external_dependency_metrics,
)

_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")


class MetaMediaAPIError(RuntimeError):
    pass


class MetaMediaAPIRetryableError(MetaMediaAPIError):
    pass


class MetaMediaAPIPermanentError(MetaMediaAPIError):
    pass


class MetaMediaIntegrityError(MetaMediaAPIRetryableError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class MetaDownloadedMedia:
    data: bytes
    mime_type: str | None
    provider_sha256: str | None
    provider_size_bytes: int | None


class MetaMediaAPIClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._http_client = http_client

    async def download_media(
        self,
        *,
        graph_api_version: str,
        provider_media_id: str,
        phone_number_id: str,
        access_token: str,
        max_size_bytes: int | None = None,
    ) -> MetaDownloadedMedia:
        started_at = perf_counter()

        try:
            if max_size_bytes is not None and max_size_bytes <= 0:
                raise ValueError("max_size_bytes must be greater than zero.")

            version = self._validate_version(graph_api_version)

            media_id = provider_media_id.strip()

            if not media_id:
                raise MetaMediaAPIPermanentError("Meta media ID is empty.")

            phone_id = phone_number_id.strip()

            if not phone_id:
                raise MetaMediaAPIPermanentError("Meta phone number ID is empty.")

            result = await self._download_validated_media(
                version=version,
                media_id=media_id,
                phone_id=phone_id,
                access_token=access_token,
                max_size_bytes=max_size_bytes,
            )

        except ValueError:
            raise

        except MetaMediaAPIRetryableError:
            self._observe(
                outcome="retryable_failure",
                started_at=started_at,
            )
            raise

        except MetaMediaAPIPermanentError:
            self._observe(
                outcome="permanent_failure",
                started_at=started_at,
            )
            raise

        except Exception:
            self._observe(
                outcome="failure",
                started_at=started_at,
            )
            raise

        self._observe(
            outcome="success",
            started_at=started_at,
        )

        return result

    async def _download_validated_media(
        self,
        *,
        version: str,
        media_id: str,
        phone_id: str,
        access_token: str,
        max_size_bytes: int | None,
    ) -> MetaDownloadedMedia:
        metadata_url = f"https://graph.facebook.com/{version}/{media_id}"
        metadata_response = await self._get(
            metadata_url,
            operation="media_metadata",
            access_token=access_token,
            params={
                "phone_number_id": phone_id,
            },
        )

        metadata = self._decode_json(metadata_response)

        if not (metadata_response.is_success):
            self._raise_for_response(
                metadata_response,
                metadata,
                operation=("retrieve media URL"),
            )

        returned_id = metadata.get("id")

        if (
            not isinstance(
                returned_id,
                str,
            )
            or returned_id != media_id
        ):
            raise (
                MetaMediaAPIPermanentError(
                    ("Meta media response ID does not match the requested media.")
                )
            )

        raw_url = metadata.get("url")

        if (
            not isinstance(
                raw_url,
                str,
            )
            or not raw_url.strip()
        ):
            raise (MetaMediaAPIRetryableError(("Meta media response contains no download URL.")))

        download_url = raw_url.strip()

        self._validate_download_url(download_url)

        provider_mime_type = self._optional_string(metadata.get("mime_type"))

        provider_sha256 = self._optional_string(metadata.get("sha256"))

        provider_size = self._optional_size(metadata.get("file_size"))

        if (
            max_size_bytes is not None
            and provider_size is not None
            and provider_size > max_size_bytes
        ):
            raise (MetaMediaAPIPermanentError(("Meta media exceeds the configured size limit.")))

        download_response = await self._get(
            download_url,
            operation="media_download",
            access_token=access_token,
        )

        if download_response.status_code == 404:
            raise (
                MetaMediaAPIRetryableError(
                    ("Meta media download URL expired or became temporarily unavailable.")
                )
            )

        if not (download_response.is_success):
            self._raise_for_response(
                download_response,
                {},
                operation="download media",
            )

        data = download_response.content

        if max_size_bytes is not None and len(data) > max_size_bytes:
            raise (
                MetaMediaAPIPermanentError(
                    ("Downloaded Meta media exceeds the configured size limit.")
                )
            )

        if provider_size is not None and len(data) != provider_size:
            raise (
                MetaMediaIntegrityError(
                    ("Downloaded Meta media size does not match provider metadata.")
                )
            )

        if provider_sha256 is not None:
            actual_sha256 = hashlib.sha256(data).hexdigest()

            if actual_sha256.lower() != provider_sha256.lower():
                raise (
                    MetaMediaIntegrityError(
                        ("Downloaded Meta media checksum does not match provider metadata.")
                    )
                )

        response_mime_type = self._response_mime_type(download_response)

        return MetaDownloadedMedia(
            data=data,
            mime_type=(provider_mime_type or response_mime_type),
            provider_sha256=(provider_sha256),
            provider_size_bytes=(provider_size),
        )

    @staticmethod
    def _observe(
        *,
        outcome: str,
        started_at: float,
    ) -> None:
        external_dependency_metrics.observe(
            dependency="meta",
            operation="download_media",
            outcome=outcome,
            duration_seconds=max(
                perf_counter() - started_at,
                0.0,
            ),
        )

    async def _get(
        self,
        url: str,
        *,
        operation: str,
        access_token: str,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        started_at = perf_counter()

        outcome = "failure"

        try:
            try:
                response = await self._http_client.get(
                    url,
                    headers={
                        "Authorization": (f"Bearer {access_token}"),
                    },
                    params=params,
                    follow_redirects=False,
                )

            except (
                httpx.TimeoutException,
                httpx.TransportError,
            ) as exc:
                raise (
                    MetaMediaAPIRetryableError(("Meta media request failed transiently."))
                ) from exc

            if response.is_success:
                outcome = "success"

            return response

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
            raise (MetaMediaAPIPermanentError(("Invalid Meta Graph API version.")))

        return normalized

    @staticmethod
    def _validate_download_url(
        value: str,
    ) -> None:
        parsed = urlparse(value)

        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise (MetaMediaAPIPermanentError(("Meta returned an invalid media download URL.")))

        try:
            port = parsed.port

        except ValueError as exc:
            raise (
                MetaMediaAPIPermanentError(("Meta returned an invalid media download URL."))
            ) from exc

        if port not in {
            None,
            443,
        }:
            raise (MetaMediaAPIPermanentError(("Meta media download URL must use the HTTPS port.")))

        hostname = parsed.hostname.strip().rstrip(".").lower()

        if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
            raise (MetaMediaAPIPermanentError(("Meta returned an unsafe media download host.")))

        try:
            ipaddress.ip_address(hostname)

        except ValueError:
            pass

        else:
            raise (
                MetaMediaAPIPermanentError(("Meta media download URL must not use an IP address."))
            )

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
    def _raise_for_response(
        response: httpx.Response,
        payload: dict[str, object],
        *,
        operation: str,
    ) -> None:
        if (
            response.status_code == 429
            or response.status_code >= 500
            or (MetaMediaAPIClient._is_transient_error(payload))
        ):
            raise (MetaMediaAPIRetryableError((f"Meta could not {operation} transiently.")))

        raise (MetaMediaAPIPermanentError((f"Meta rejected the {operation} request.")))

    @staticmethod
    def _is_transient_error(
        payload: dict[str, object],
    ) -> bool:
        raw_error = payload.get("error")

        if not isinstance(
            raw_error,
            dict,
        ):
            return False

        error = cast(
            dict[str, object],
            raw_error,
        )

        return error.get("is_transient") is True

    @staticmethod
    def _optional_string(
        value: object,
    ) -> str | None:
        if not isinstance(
            value,
            str,
        ):
            return None

        normalized = value.strip()

        return normalized or None

    @staticmethod
    def _optional_size(
        value: object,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(
            value,
            int,
        ) and not isinstance(
            value,
            bool,
        ):
            if value < 0:
                raise (MetaMediaAPIPermanentError(("Meta returned an invalid media file size.")))

            return value

        if isinstance(
            value,
            str,
        ):
            normalized = value.strip()

            if normalized.isdigit():
                return int(normalized)

        raise (MetaMediaAPIPermanentError(("Meta returned an invalid media file size.")))

    @staticmethod
    def _response_mime_type(
        response: httpx.Response,
    ) -> str | None:
        raw_value = response.headers.get("content-type")

        if raw_value is None:
            return None

        normalized = raw_value.split(
            ";",
            1,
        )[0].strip()

        return normalized or None
