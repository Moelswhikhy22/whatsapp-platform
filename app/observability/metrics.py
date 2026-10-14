from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


_HTTP_LATENCY_BUCKETS = (
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

_READINESS_LATENCY_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
)


class ApiMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._registry = registry if registry is not None else CollectorRegistry()

        self._requests = Counter(
            "http_requests",
            "Total HTTP requests processed.",
            labelnames=(
                "method",
                "route",
                "status",
            ),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds.",
            labelnames=(
                "method",
                "route",
                "status",
            ),
            namespace="whatsapp_platform",
            buckets=_HTTP_LATENCY_BUCKETS,
            registry=self._registry,
        )

    def observe_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        labels = {
            "method": method.upper(),
            "route": route,
            "status": str(status_code),
        }

        self._requests.labels(**labels).inc()

        self._request_duration.labels(**labels).observe(
            max(
                duration_seconds,
                0.0,
            )
        )

    def render_latest(self) -> bytes:
        return generate_latest(self._registry)


class InfrastructureMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._registry = registry if registry is not None else CollectorRegistry()

        self._dependency_up = Gauge(
            "dependency_up",
            ("Whether an infrastructure dependency is currently healthy."),
            labelnames=("dependency",),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._dependency_checks = Counter(
            "dependency_health_checks",
            ("Infrastructure dependency health-check results."),
            labelnames=(
                "dependency",
                "outcome",
            ),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._readiness_checks = Counter(
            "readiness_checks",
            "Application readiness checks.",
            labelnames=("status",),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._readiness_duration = Histogram(
            "readiness_check_duration_seconds",
            ("Duration of application readiness checks."),
            namespace="whatsapp_platform",
            buckets=_READINESS_LATENCY_BUCKETS,
            registry=self._registry,
        )

    def observe_dependency_health(
        self,
        *,
        postgres: bool,
        redis: bool,
        rabbitmq: bool,
    ) -> None:
        dependencies = {
            "postgresql": postgres,
            "redis": redis,
            "rabbitmq": rabbitmq,
        }

        for dependency, healthy in dependencies.items():
            self._dependency_up.labels(
                dependency=dependency,
            ).set(1 if healthy else 0)

            self._dependency_checks.labels(
                dependency=dependency,
                outcome=("up" if healthy else "down"),
            ).inc()

    def observe_readiness(
        self,
        *,
        status: str,
        duration_seconds: float,
    ) -> None:
        self._readiness_checks.labels(
            status=status,
        ).inc()

        self._readiness_duration.observe(
            max(
                duration_seconds,
                0.0,
            )
        )

    def render_latest(self) -> bytes:
        return generate_latest(self._registry)


class RabbitMQQueueMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._registry = registry if registry is not None else CollectorRegistry()

        self._messages = Gauge(
            "rabbitmq_queue_messages",
            ("Current number of ready messages in a RabbitMQ queue."),
            labelnames=(
                "queue",
                "kind",
            ),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._consumers = Gauge(
            "rabbitmq_queue_consumers",
            ("Current number of consumers attached to a RabbitMQ queue."),
            labelnames=(
                "queue",
                "kind",
            ),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._depth_alert = Gauge(
            "rabbitmq_queue_depth_alert",
            ("Whether a queue depth threshold is currently exceeded."),
            labelnames=(
                "queue",
                "kind",
                "severity",
            ),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._collection_up = Gauge(
            "rabbitmq_queue_collection_up",
            ("Whether the latest RabbitMQ queue metrics collection succeeded."),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

        self._collection_failures = Counter(
            "rabbitmq_queue_collection_failures",
            ("Total RabbitMQ queue metrics collection failures."),
            namespace="whatsapp_platform",
            registry=self._registry,
        )

    def observe_queue(
        self,
        *,
        queue_name: str,
        kind: str,
        message_count: int,
        consumer_count: int,
        warning_threshold: int,
        critical_threshold: int,
    ) -> None:
        labels = {
            "queue": queue_name,
            "kind": kind,
        }

        self._messages.labels(**labels).set(message_count)

        self._consumers.labels(**labels).set(consumer_count)

        self._depth_alert.labels(
            **labels,
            severity="warning",
        ).set((1 if message_count >= warning_threshold else 0))

        self._depth_alert.labels(
            **labels,
            severity="critical",
        ).set((1 if message_count >= critical_threshold else 0))

    def observe_collection_success(
        self,
    ) -> None:
        self._collection_up.set(1)

    def observe_collection_failure(
        self,
    ) -> None:
        self._collection_up.set(0)

        self._collection_failures.inc()

    def render_latest(self) -> bytes:
        return generate_latest(self._registry)


metrics_registry = CollectorRegistry()

api_metrics = ApiMetrics(registry=metrics_registry)

infrastructure_metrics = InfrastructureMetrics(registry=metrics_registry)

rabbitmq_queue_metrics = RabbitMQQueueMetrics(registry=metrics_registry)


def render_latest_metrics() -> bytes:
    return generate_latest(metrics_registry)
