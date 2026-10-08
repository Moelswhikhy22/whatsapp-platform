from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


EnvironmentName = Literal[
    "local",
    "test",
    "staging",
    "production",
]


@dataclass(
    frozen=True,
    slots=True,
)
class MediaObjectKeyBuilder:
    environment: EnvironmentName

    def build(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        media_id: UUID,
    ) -> str:
        prefix = "prod" if self.environment == "production" else self.environment

        return f"{prefix}/{tenant_id}/whatsapp/{conversation_id}/{message_id}/{media_id}"
