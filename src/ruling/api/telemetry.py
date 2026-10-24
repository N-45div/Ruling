"""Tracing to Application Insights: every agent, model call and tool as an OpenTelemetry span."""

from __future__ import annotations

import logging
import os


def configure() -> bool:
    """Send traces to Application Insights when its connection string is set. Returns whether it did."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return False
    from agent_framework.observability import enable_instrumentation
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()  # reads APPLICATIONINSIGHTS_CONNECTION_STRING
    enable_instrumentation()  # Agent Framework spans: invoke_agent, chat, execute_tool, workflow steps
    # The Azure SDKs log every HTTP request and response at INFO (about 15 lines each); keep warnings only.
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    return True
