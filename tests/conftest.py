import logging

import pytest
import structlog


@pytest.fixture(autouse=True)
def isolate_auth_env(monkeypatch):
    monkeypatch.setenv("CC_ADAPTER_ACCESS_KEY", "")
    monkeypatch.setenv("CC_ADAPTER_ADMIN_PASSWORD", "")


@pytest.fixture(autouse=True, scope="session")
def configure_structlog_for_tests():
    """Configure structlog to use stdlib logging for caplog/capsys capture."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Ensure there's a handler so logs go through stdlib
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.setLevel(logging.DEBUG)
