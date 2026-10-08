from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.authorization import (
    AuthorizationDeniedError,
    TenantIsolationError,
)
from app.authorization.permissions import (
    Permission,
)
from app.authorization.policy import (
    require_permission,
)
from app.core.config import get_settings
from app.db.models.outgoing_webhook import (
    OutgoingWebhookAttemptOutcome,
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryAttempt,
    OutgoingWebhookDeliveryStatus,
    OutgoingWebhookSubscription,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidationError,
    WebhookEndpointValidator,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookRepository,
)
from app.security_access import (
    record_security_access,
)
from app.services.outgoing_webhook_management import (
    OutgoingWebhookDeliveryNotFoundError,
    OutgoingWebhookDeliveryRetryConflictError,
    OutgoingWebhookManagementService,
)
from app.services.outgoing_webhook_subscription import (
    OutgoingWebhookPersistenceError,
    OutgoingWebhookSecretStorageError,
    OutgoingWebhookSubscriptionInvalidError,
    OutgoingWebhookSubscriptionService,
)


router = APIRouter(
    prefix="/webhooks",
    tags=["outgoing-webhooks"],
)


class CreateWebhookSubscriptionRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    endpoint_url: str = Field(
        min_length=1,
        max_length=2048,
    )

    event_types: list[str] = Field(
        min_length=1,
    )

    signing_secret: SecretStr


class WebhookSubscriptionResponse(BaseModel):
    id: UUID
    name: str
    endpoint_url: str
    event_types: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    id: UUID
    subscription_id: UUID
    event_id: UUID
    event_type: str
    status: OutgoingWebhookDeliveryStatus
    attempt_count: int
    next_attempt_at: datetime
    last_attempt_at: datetime | None
    last_http_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryAttemptResponse(BaseModel):
    id: UUID
    delivery_id: UUID
    attempt_number: int
    outcome: OutgoingWebhookAttemptOutcome
    http_status_code: int | None
    error_message: str | None
    attempted_at: datetime


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookSubscriptionResponse,
)
async def create_webhook_subscription(
    payload: CreateWebhookSubscriptionRequest,
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> WebhookSubscriptionResponse:
    settings = get_settings()

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=settings.vault_token,
            token_file=settings.vault_token_file,
            namespace=settings.vault_namespace,
            verify=settings.vault_verify,
            timeout_seconds=settings.vault_timeout_seconds,
            kv_mount_point=settings.vault_kv_mount_point,
        )
    )

    repository = OutgoingWebhookRepository(
        session=session,
        tenant=request_context.tenant,
    )

    audit_repository = BusinessAuditLogRepository(
        session=session,
        tenant=request_context.tenant,
    )

    service = OutgoingWebhookSubscriptionService(
        repository=repository,
        audit_repository=audit_repository,
        vault_client=vault_client,
        path_builder=VaultPathBuilder(
            root=settings.vault_path_root,
        ),
        endpoint_validator=WebhookEndpointValidator(),
    )

    try:
        subscription = await service.create(
            context=request_context.authorization,
            name=payload.name,
            endpoint_url=payload.endpoint_url,
            event_types=payload.event_types,
            signing_secret=payload.signing_secret.get_secret_value(),
        )

        await session.commit()

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="outgoing_webhook_subscription",
            resource_id=None,
            reason_code="webhook_manage_not_allowed",
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WEBHOOK_MANAGE_FORBIDDEN",
                "message": "Webhook management is not allowed.",
            },
        ) from exc

    except (
        OutgoingWebhookSubscriptionInvalidError,
        WebhookEndpointValidationError,
    ) as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_WEBHOOK_SUBSCRIPTION",
                "message": str(exc),
            },
        ) from exc

    except OutgoingWebhookSecretStorageError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEBHOOK_SECRET_STORAGE_UNAVAILABLE",
                "message": "Webhook secret storage is unavailable.",
            },
        ) from exc

    except OutgoingWebhookPersistenceError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEBHOOK_SUBSCRIPTION_PERSISTENCE_FAILED",
                "message": "Webhook subscription could not be created.",
            },
        ) from exc

    finally:
        await vault_client.close()

    return _subscription_response(subscription)


@router.get(
    "",
    response_model=list[WebhookSubscriptionResponse],
)
async def list_webhook_subscriptions(
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> list[WebhookSubscriptionResponse]:
    repository = OutgoingWebhookRepository(
        session=session,
        tenant=request_context.tenant,
    )

    try:
        require_permission(
            request_context.authorization,
            Permission.WEBHOOK_MANAGE,
        )

        subscriptions = await repository.list_subscriptions()

    except AuthorizationDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WEBHOOK_MANAGE_FORBIDDEN",
                "message": "Webhook management is not allowed.",
            },
        ) from exc

    return [_subscription_response(item) for item in subscriptions]


@router.get(
    "/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
async def list_webhook_deliveries(
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    subscription_id: UUID | None = None,
    delivery_status: Annotated[
        OutgoingWebhookDeliveryStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=200,
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
) -> list[WebhookDeliveryResponse]:
    service = _management_service(
        request_context=request_context,
        session=session,
    )

    try:
        deliveries = await service.list_deliveries(
            context=request_context.authorization,
            subscription_id=subscription_id,
            status=delivery_status,
            limit=limit,
            offset=offset,
        )

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        raise _manage_forbidden(exc)

    return [_delivery_response(item) for item in deliveries]


@router.get(
    "/deliveries/{delivery_id}/attempts",
    response_model=list[WebhookDeliveryAttemptResponse],
)
async def list_webhook_delivery_attempts(
    delivery_id: UUID,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> list[WebhookDeliveryAttemptResponse]:
    service = _management_service(
        request_context=request_context,
        session=session,
    )

    try:
        attempts = await service.list_attempts(
            context=request_context.authorization,
            delivery_id=delivery_id,
        )

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        raise _manage_forbidden(exc)

    except OutgoingWebhookDeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WEBHOOK_DELIVERY_NOT_FOUND",
                "message": "Webhook delivery was not found.",
            },
        ) from exc

    return [_attempt_response(item) for item in attempts]


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryResponse,
)
async def retry_webhook_delivery(
    delivery_id: UUID,
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> WebhookDeliveryResponse:
    service = _management_service(
        request_context=request_context,
        session=session,
    )

    try:
        delivery = await service.retry_failed_delivery(
            context=request_context.authorization,
            delivery_id=delivery_id,
        )

        await session.commit()

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="outgoing_webhook_delivery",
            resource_id=str(delivery_id),
            reason_code="webhook_retry_not_allowed",
        )

        raise _manage_forbidden(exc)

    except OutgoingWebhookDeliveryNotFoundError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WEBHOOK_DELIVERY_NOT_FOUND",
                "message": "Webhook delivery was not found.",
            },
        ) from exc

    except OutgoingWebhookDeliveryRetryConflictError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WEBHOOK_DELIVERY_NOT_FAILED",
                "message": ("Only failed webhook deliveries can be manually retried."),
            },
        ) from exc

    return _delivery_response(delivery)


def _management_service(
    *,
    request_context: HumanConversationRequestContext,
    session: AsyncSession,
) -> OutgoingWebhookManagementService:
    repository = OutgoingWebhookRepository(
        session=session,
        tenant=request_context.tenant,
    )

    outbox_repository = OutboxEventRepository(
        session=session,
        tenant=request_context.tenant,
    )

    return OutgoingWebhookManagementService(
        repository=repository,
        outbox_repository=outbox_repository,
    )


def _manage_forbidden(
    exc: Exception,
) -> HTTPException:
    del exc

    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "WEBHOOK_MANAGE_FORBIDDEN",
            "message": "Webhook management is not allowed.",
        },
    )


def _subscription_response(
    subscription: OutgoingWebhookSubscription,
) -> WebhookSubscriptionResponse:
    return WebhookSubscriptionResponse(
        id=subscription.id,
        name=subscription.name,
        endpoint_url=subscription.endpoint_url,
        event_types=list(subscription.event_types_json),
        active=subscription.active,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def _delivery_response(
    delivery: OutgoingWebhookDelivery,
) -> WebhookDeliveryResponse:
    return WebhookDeliveryResponse(
        id=delivery.id,
        subscription_id=delivery.subscription_id,
        event_id=delivery.event_id,
        event_type=delivery.event_type,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        next_attempt_at=delivery.next_attempt_at,
        last_attempt_at=delivery.last_attempt_at,
        last_http_status_code=delivery.last_http_status_code,
        last_error=delivery.last_error,
        delivered_at=delivery.delivered_at,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


def _attempt_response(
    attempt: OutgoingWebhookDeliveryAttempt,
) -> WebhookDeliveryAttemptResponse:
    return WebhookDeliveryAttemptResponse(
        id=attempt.id,
        delivery_id=attempt.delivery_id,
        attempt_number=attempt.attempt_number,
        outcome=attempt.outcome,
        http_status_code=attempt.http_status_code,
        error_message=attempt.error_message,
        attempted_at=attempt.attempted_at,
    )
