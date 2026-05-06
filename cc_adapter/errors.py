from __future__ import annotations


class AdapterError(Exception):
    def __init__(self, message: str, status_code: int = 500, original_status: int | None = None):
        self.message = message
        self.status_code = status_code
        self.original_status = original_status
        super().__init__(self.message)

    def to_openai_error(self) -> dict:
        error_type_map = {
            401: "authentication_error",
            403: "authentication_error",
            404: "not_found",
            429: "rate_limit_error",
            400: "invalid_request_error",
            502: "api_error",
            504: "timeout_error",
        }
        error_type = error_type_map.get(self.original_status or self.status_code, "api_error")
        return {
            "error": {
                "message": self.message,
                "type": error_type,
                "code": self.original_status or self.status_code,
            }
        }


class AuthenticationError(AdapterError):
    def __init__(self, message: str = "Authentication failed", original_status: int | None = 401):
        super().__init__(message=message, status_code=401, original_status=original_status)


class RateLimitError(AdapterError):
    def __init__(self, message: str = "Rate limit exceeded", original_status: int | None = 429):
        super().__init__(message=message, status_code=429, original_status=original_status)


class UpstreamError(AdapterError):
    def __init__(self, message: str = "Upstream server error", original_status: int | None = 502):
        super().__init__(message=message, status_code=502, original_status=original_status)


class TimeoutError_(AdapterError):
    def __init__(self, message: str = "Request timed out", original_status: int | None = 504):
        super().__init__(message=message, status_code=504, original_status=original_status)


def map_upstream_error(status_code: int, message: str) -> AdapterError:
    if status_code == 401 or status_code == 403:
        return AuthenticationError(message=message, original_status=status_code)
    elif status_code == 429:
        return RateLimitError(message=message, original_status=status_code)
    elif status_code >= 500:
        return UpstreamError(message=message, original_status=status_code)
    elif status_code == 400 or status_code == 404:
        return AdapterError(message=message, status_code=status_code, original_status=status_code)
    return AdapterError(message=message, status_code=502, original_status=status_code)
