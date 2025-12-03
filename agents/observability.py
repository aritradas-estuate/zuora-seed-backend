"""
OpenTelemetry observability utilities for Zuora Seed Agent.
Provides centralized tracing, metrics collection, and instrumentation.
"""
import os
import time
import functools
from typing import Optional, Dict, Any, Callable
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.trace import Status, StatusCode

# Global singleton instances
_tracer: Optional[trace.Tracer] = None
_meter: Optional[metrics.Meter] = None
_metrics_collector: Optional['MetricsCollector'] = None
_initialized = False


def initialize_observability() -> None:
    """
    Initialize OpenTelemetry tracing and metrics.
    Safe to call multiple times - will only initialize once.
    """
    global _tracer, _meter, _metrics_collector, _initialized

    if _initialized:
        return

    # Check if observability is enabled
    otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() == "true"
    if not otel_enabled:
        # Create no-op tracer and meter
        _tracer = trace.NoOpTracer()
        _meter = metrics.NoOpMeter()
        _metrics_collector = MetricsCollector()
        _initialized = True
        return

    # Create resource with service name and attributes
    service_name = os.getenv("OTEL_SERVICE_NAME", "zuora-seed-agent")
    resource_attributes = {
        "service.name": service_name,
        "deployment.environment": os.getenv("DEPLOYMENT_ENV", "development"),
        "service.version": "0.1.0",
    }

    # Parse additional resource attributes from env var
    additional_attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    if additional_attrs:
        for attr in additional_attrs.split(","):
            if "=" in attr:
                key, value = attr.split("=", 1)
                resource_attributes[key.strip()] = value.strip()

    resource = Resource.create(resource_attributes)

    # Configure tracing
    trace_provider = TracerProvider(resource=resource)

    # OTLP exporter for traces
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otlp_endpoint:
        trace_exporter = OTLPSpanExporter(
            endpoint=f"{otlp_endpoint}/v1/traces",
            headers=_parse_otlp_headers("OTEL_EXPORTER_OTLP_TRACES_HEADERS"),
        )
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(__name__)

    # Configure metrics
    otlp_metric_exporter = None
    if otlp_endpoint:
        otlp_metric_exporter = OTLPMetricExporter(
            endpoint=f"{otlp_endpoint}/v1/metrics",
            headers=_parse_otlp_headers("OTEL_EXPORTER_OTLP_METRICS_HEADERS"),
        )

    if otlp_metric_exporter:
        metric_reader = PeriodicExportingMetricReader(
            otlp_metric_exporter,
            export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "60000"))
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    else:
        meter_provider = MeterProvider(resource=resource)

    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(__name__)

    # Initialize metrics collector
    _metrics_collector = MetricsCollector()

    _initialized = True


def _parse_otlp_headers(env_var_name: str) -> Dict[str, str]:
    """Parse OTLP headers from environment variable."""
    headers = {}
    headers_str = os.getenv(env_var_name, "")
    if headers_str:
        for header in headers_str.split(","):
            if "=" in header:
                key, value = header.split("=", 1)
                headers[key.strip()] = value.strip()
    return headers


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance."""
    if _tracer is None:
        initialize_observability()
    return _tracer


def get_meter() -> metrics.Meter:
    """Get the global meter instance."""
    if _meter is None:
        initialize_observability()
    return _meter


def get_metrics_collector() -> 'MetricsCollector':
    """Get the global metrics collector instance."""
    if _metrics_collector is None:
        initialize_observability()
    return _metrics_collector


def trace_function(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> Callable:
    """
    Decorator to automatically trace a function with OpenTelemetry.

    Args:
        span_name: Custom span name (defaults to function name)
        attributes: Additional span attributes to set

    Usage:
        @trace_function(span_name="my_operation", attributes={"component": "api"})
        def my_function(arg1, arg2):
            # ... implementation ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            name = span_name or f"{func.__module__}.{func.__name__}"

            with tracer.start_as_current_span(name) as span:
                # Set default attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)

                # Execute function
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


class MetricsCollector:
    """
    Centralized metrics collection for the Zuora Seed Agent.
    Provides high-level methods to record various types of metrics.
    """

    def __init__(self):
        meter = get_meter()

        # Request metrics
        self.requests_total = meter.create_counter(
            name="requests_total",
            description="Total number of requests processed",
            unit="1"
        )
        self.request_duration = meter.create_histogram(
            name="request_duration_ms",
            description="Request duration in milliseconds",
            unit="ms"
        )
        self.errors_total = meter.create_counter(
            name="errors_total",
            description="Total number of errors",
            unit="1"
        )

        # Agent metrics
        self.agent_invocations_total = meter.create_counter(
            name="agent_invocations_total",
            description="Total number of agent invocations",
            unit="1"
        )
        self.agent_invocation_duration = meter.create_histogram(
            name="agent_invocation_duration_ms",
            description="Agent invocation duration in milliseconds",
            unit="ms"
        )

        # Tool metrics
        self.tool_executions_total = meter.create_counter(
            name="tool_executions_total",
            description="Total number of tool executions",
            unit="1"
        )
        self.tool_execution_duration = meter.create_histogram(
            name="tool_execution_duration_ms",
            description="Tool execution duration in milliseconds",
            unit="ms"
        )

        # API metrics
        self.api_calls_total = meter.create_counter(
            name="api_calls_total",
            description="Total number of Zuora API calls",
            unit="1"
        )
        self.api_call_duration = meter.create_histogram(
            name="api_call_duration_ms",
            description="Zuora API call duration in milliseconds",
            unit="ms"
        )
        self.api_errors_total = meter.create_counter(
            name="api_errors_total",
            description="Total number of Zuora API errors",
            unit="1"
        )

        # Cache metrics
        self.cache_hits_total = meter.create_counter(
            name="cache_hits_total",
            description="Total number of cache hits",
            unit="1"
        )
        self.cache_misses_total = meter.create_counter(
            name="cache_misses_total",
            description="Total number of cache misses",
            unit="1"
        )

    def record_request(self, persona: str, duration_ms: float, success: bool = True) -> None:
        """Record a request metric."""
        attributes = {"persona": persona, "success": str(success)}
        self.requests_total.add(1, attributes)
        self.request_duration.record(duration_ms, attributes)

        if not success:
            self.errors_total.add(1, attributes)

    def record_agent_invocation(self, persona: str, duration_ms: float, success: bool = True) -> None:
        """Record an agent invocation metric."""
        attributes = {"persona": persona, "success": str(success)}
        self.agent_invocations_total.add(1, attributes)
        self.agent_invocation_duration.record(duration_ms, attributes)

    def record_tool_execution(self, tool_name: str, category: str, duration_ms: float, success: bool = True) -> None:
        """Record a tool execution metric."""
        attributes = {
            "tool_name": tool_name,
            "category": category,
            "success": str(success)
        }
        self.tool_executions_total.add(1, attributes)
        self.tool_execution_duration.record(duration_ms, attributes)

    def record_api_call(self, method: str, endpoint: str, duration_ms: float, success: bool = True) -> None:
        """Record a Zuora API call metric."""
        attributes = {
            "method": method,
            "endpoint": endpoint,
            "success": str(success)
        }
        self.api_calls_total.add(1, attributes)
        self.api_call_duration.record(duration_ms, attributes)

    def record_api_error(self, method: str, endpoint: str, error_type: str = "unknown") -> None:
        """Record a Zuora API error metric."""
        attributes = {
            "method": method,
            "endpoint": endpoint,
            "error_type": error_type
        }
        self.api_errors_total.add(1, attributes)

    def record_cache_hit(self, operation: str) -> None:
        """Record a cache hit metric."""
        self.cache_hits_total.add(1, {"operation": operation})

    def record_cache_miss(self, operation: str) -> None:
        """Record a cache miss metric."""
        self.cache_misses_total.add(1, {"operation": operation})
