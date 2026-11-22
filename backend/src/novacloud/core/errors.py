class NovaError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, message: str = ""):
        super().__init__(message or self.code)
        self.message = message or self.code


class InvalidInput(NovaError):
    status, code = 422, "invalid_input"


class Unauthorized(NovaError):
    status, code = 401, "unauthorized"


class Forbidden(NovaError):
    status, code = 403, "forbidden"


class NotFound(NovaError):
    status, code = 404, "not_found"


class Conflict(NovaError):
    status, code = 409, "conflict"


class RateLimited(NovaError):
    status, code = 429, "rate_limited"


class ProviderError(NovaError):
    status, code = 502, "provider_error"
