from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DependencyState = Literal["up", "down"]
ReadinessState = Literal["ready", "degraded", "not_ready"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class DependencyHealthResponse(BaseModel):
    postgres: DependencyState
    redis: DependencyState
    rabbitmq: DependencyState


class ReadinessResponse(BaseModel):
    status: ReadinessState
    dependencies: DependencyHealthResponse
