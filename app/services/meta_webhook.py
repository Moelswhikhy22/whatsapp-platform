from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from app.db.models.integration import Integration
from app.db.models.raw_webhook_event import (
    RawWebhookProcessingStatus,
)
from app.integrations.meta.webhook_security import (
    MetaWebhookCredentialProvider,
    derive_provider_event_key,
    verify_meta_challenge_token,
    verify_meta_signature,
)
from app.repositories.meta_webhook import (
    MetaWebhookRepository,
)


class MetaWebhookError(RuntimeError):
    pass


class MetaWebhookIntegrationNotFoundError(MetaWebhookError):
    pass


class MetaWebhookVerificationError(MetaWebhookError):
    pass


class MetaWebhookInvalidSignatureError(MetaWebhookError):
    pass


class MetaWebhookInvalidPayloadError(MetaWebhookError):
    pass


@dataclass(frozen=True, slots=True)
class MetaWebhookIngressResult:
    raw_event_id: UUID | None
    duplicate: bool
    tenant_resolved: bool


class MetaWebhookIngressService:
    def __init__(
        self,
        *,
        repository: MetaWebhookRepository,
        credential_provider: (MetaWebhookCredentialProvider),
    ) -> None:
        self._repository = repository
        self._credential_provider = credential_provider

    async def verify_challenge(
        self,
        *,
        integration_id: UUID,
        mode: str,
        verify_token: str,
        challenge: str,
    ) -> str:
        if mode != "subscribe":
            raise MetaWebhookVerificationError

        integration = await self._get_integration(integration_id)

        credentials = await self._credential_provider.get_credentials(integration)

        if not verify_meta_challenge_token(
            received_token=verify_token,
            expected_token=(credentials.verify_token),
        ):
            raise MetaWebhookVerificationError

        return challenge

    async def receive(
        self,
        *,
        integration_id: UUID,
        raw_body: bytes,
        signature_header: str | None,
    ) -> MetaWebhookIngressResult:
        integration = await self._get_integration(integration_id)

        credentials = await self._credential_provider.get_credentials(integration)

        if not verify_meta_signature(
            raw_body=raw_body,
            signature_header=(signature_header),
            app_secret=(credentials.app_secret),
        ):
            raise MetaWebhookInvalidSignatureError

        payload = self._decode_payload(raw_body)

        provider_event_key = derive_provider_event_key(raw_body)

        phone_number_ids = self._extract_phone_number_ids(payload)

        event_type = self._extract_event_type(payload)

        (
            tenant_id,
            unresolved_reason,
        ) = await self._resolve_tenant(
            integration=integration,
            phone_number_ids=(phone_number_ids),
        )

        processing_status = (
            RawWebhookProcessingStatus.RECEIVED
            if tenant_id is not None
            else RawWebhookProcessingStatus.UNRESOLVED
        )

        raw_event_id = await self._repository.insert_raw_event_if_new(
            tenant_id=tenant_id,
            provider_event_key=(provider_event_key),
            event_type=event_type,
            payload_json=payload,
            processing_status=(processing_status),
            last_error=(unresolved_reason),
        )

        if raw_event_id is None:
            return MetaWebhookIngressResult(
                raw_event_id=None,
                duplicate=True,
                tenant_resolved=(tenant_id is not None),
            )

        if tenant_id is not None:
            self._repository.add_inbound_outbox_event(
                tenant_id=tenant_id,
                raw_event_id=raw_event_id,
            )

        return MetaWebhookIngressResult(
            raw_event_id=raw_event_id,
            duplicate=False,
            tenant_resolved=(tenant_id is not None),
        )

    async def _get_integration(
        self,
        integration_id: UUID,
    ) -> Integration:
        integration = await self._repository.get_active_meta_integration(integration_id)

        if integration is None:
            raise (MetaWebhookIntegrationNotFoundError)

        return integration

    async def _resolve_tenant(
        self,
        *,
        integration: Integration,
        phone_number_ids: set[str],
    ) -> tuple[UUID | None, str | None]:
        if not phone_number_ids:
            return (
                None,
                "META_PHONE_NUMBER_ID_MISSING",
            )

        numbers = await self._repository.get_active_whatsapp_numbers(phone_number_ids)

        number_by_meta_id = {number.meta_phone_number_id: number for number in numbers}

        if set(number_by_meta_id) != phone_number_ids:
            return (
                None,
                "META_PHONE_NUMBER_ID_UNKNOWN",
            )

        for number in numbers:
            if number.integration_id != integration.id or number.tenant_id != integration.tenant_id:
                return (
                    None,
                    ("META_PHONE_NUMBER_ID_INTEGRATION_MISMATCH"),
                )

        return (
            integration.tenant_id,
            None,
        )

    @staticmethod
    def _decode_payload(
        raw_body: bytes,
    ) -> dict[str, object]:
        try:
            decoded = json.loads(raw_body)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise (MetaWebhookInvalidPayloadError) from exc

        if not isinstance(
            decoded,
            dict,
        ):
            raise (MetaWebhookInvalidPayloadError)

        return cast(
            dict[str, object],
            decoded,
        )

    @classmethod
    def _extract_phone_number_ids(
        cls,
        payload: dict[str, object],
    ) -> set[str]:
        result: set[str] = set()

        entries = payload.get("entry")

        if not isinstance(entries, list):
            return result

        for raw_entry in entries:
            if not isinstance(
                raw_entry,
                dict,
            ):
                continue

            entry = cast(
                dict[str, object],
                raw_entry,
            )

            changes = entry.get("changes")

            if not isinstance(
                changes,
                list,
            ):
                continue

            for raw_change in changes:
                if not isinstance(
                    raw_change,
                    dict,
                ):
                    continue

                change = cast(
                    dict[str, object],
                    raw_change,
                )

                raw_value = change.get("value")

                if not isinstance(
                    raw_value,
                    dict,
                ):
                    continue

                value = cast(
                    dict[str, object],
                    raw_value,
                )

                raw_metadata = value.get("metadata")

                if not isinstance(
                    raw_metadata,
                    dict,
                ):
                    continue

                metadata = cast(
                    dict[str, object],
                    raw_metadata,
                )

                raw_phone_number_id = metadata.get("phone_number_id")

                if (
                    isinstance(
                        raw_phone_number_id,
                        str,
                    )
                    and raw_phone_number_id
                ):
                    result.add(raw_phone_number_id)

        return result

    @staticmethod
    def _extract_event_type(
        payload: dict[str, object],
    ) -> str | None:
        fields: set[str] = set()

        entries = payload.get("entry")

        if not isinstance(entries, list):
            return None

        for raw_entry in entries:
            if not isinstance(
                raw_entry,
                dict,
            ):
                continue

            entry = cast(
                dict[str, object],
                raw_entry,
            )

            changes = entry.get("changes")

            if not isinstance(
                changes,
                list,
            ):
                continue

            for raw_change in changes:
                if not isinstance(
                    raw_change,
                    dict,
                ):
                    continue

                change = cast(
                    dict[str, object],
                    raw_change,
                )

                field = change.get("field")

                if isinstance(
                    field,
                    str,
                ):
                    fields.add(field)

        if not fields:
            return None

        if len(fields) == 1:
            return next(iter(fields))

        return "batch"
