from __future__ import annotations

from time import perf_counter
from types import TracebackType

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
)

from app.observability.metrics import (
    metrics_registry,
)


_OPERATION_DURATION_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class ExternalDependencyMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry,
    ) -> None:
        self._operations = Counter(
            "external_dependency_operations",
            ("External dependency operation results."),
            labelnames=(
                "dependency",
                "operation",
                "outcome",
            ),
            namespace="whatsapp_platform",
            registry=registry,
        )

        self._duration = Histogram(
            ("external_dependency_operation_duration_seconds"),
            ("External dependency operation duration in seconds."),
            labelnames=(
                "dependency",
                "operation",
            ),
            namespace="whatsapp_platform",
            buckets=_OPERATION_DURATION_BUCKETS,
            registry=registry,
        )

    def observe(
        self,
        *,
        dependency: str,
        operation: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        self._operations.labels(
            dependency=dependency,
            operation=operation,
            outcome=outcome,
        ).inc()

        self._duration.labels(
            dependency=dependency,
            operation=operation,
        ).observe(
            max(
                duration_seconds,
                0.0,
            )
        )


external_dependency_metrics = ExternalDependencyMetrics(
    registry=metrics_registry,
)


class _ExternalOperationObservation:
    def __init__(
        self,
        *,
        dependency: str,
        operation: str,
    ) -> None:
        self._dependency = dependency
        self._operation = operation
        self._started_at: float | None = None
        self._finished = False

    def __enter__(
        self,
    ) -> _ExternalOperationObservation:
        self._start()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_value
        del traceback

        self._finish(
            outcome=("success" if exc_type is None else "failure"),
        )

        return False

    async def __aenter__(
        self,
    ) -> _ExternalOperationObservation:
        self._start()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_value
        del traceback

        self._finish(
            outcome=("success" if exc_type is None else "failure"),
        )

        return False

    def _start(
        self,
    ) -> None:
        if self._started_at is not None:
            raise RuntimeError(("External operation observation cannot be reused."))

        self._started_at = perf_counter()

    def _finish(
        self,
        *,
        outcome: str,
    ) -> None:
        if self._finished:
            return

        started_at = self._started_at

        if started_at is None:
            raise RuntimeError(("External operation observation was not started."))

        self._finished = True

        external_dependency_metrics.observe(
            dependency=self._dependency,
            operation=self._operation,
            outcome=outcome,
            duration_seconds=max(
                perf_counter() - started_at,
                0.0,
            ),
        )


def observe_external_operation(
    *,
    dependency: str,
    operation: str,
) -> _ExternalOperationObservation:
    normalized_dependency = dependency.strip().lower()

    normalized_operation = operation.strip().lower()

    if not normalized_dependency:
        raise ValueError("dependency must not be empty.")

    if not normalized_operation:
        raise ValueError("operation must not be empty.")

    return _ExternalOperationObservation(
        dependency=normalized_dependency,
        operation=normalized_operation,
    )
