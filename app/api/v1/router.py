from fastapi import APIRouter

from app.api.v1.audit import (
    router as audit_router,
)
from app.api.v1.conversation_search import (
    router as conversation_search_router,
)
from app.api.v1.conversations import (
    router as conversations_router,
)
from app.api.v1.integration_validation import (
    router as integration_validation_router,
)
from app.api.v1.integrations import (
    router as integrations_router,
)
from app.api.v1.media import (
    router as media_router,
)
from app.api.v1.messages import (
    router as messages_router,
)
from app.api.v1.outgoing_webhooks import (
    router as outgoing_webhooks_router,
)
from app.api.v1.templates import (
    router as templates_router,
)


api_router = APIRouter()


api_router.include_router(
    conversations_router,
)

api_router.include_router(
    messages_router,
)

api_router.include_router(
    outgoing_webhooks_router,
)

api_router.include_router(
    templates_router,
)

api_router.include_router(
    media_router,
)

api_router.include_router(
    integrations_router,
)

api_router.include_router(
    integration_validation_router,
)

api_router.include_router(
    conversation_search_router,
)

api_router.include_router(
    audit_router,
)
