from __future__ import annotations

from typing import cast

from fastapi import HTTPException, Request, status

from app.integrations.meta.webhook_security import (
    MetaWebhookCredentialProvider,
)


def get_meta_webhook_credential_provider(
    request: Request,
) -> MetaWebhookCredentialProvider:
    provider = getattr(
        request.app.state,
        "meta_webhook_credential_provider",
        None,
    )

    if provider is None:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Meta webhook credential service is unavailable."),
        )

    return cast(
        MetaWebhookCredentialProvider,
        provider,
    )
