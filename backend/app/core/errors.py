"""Domain errors raised by services; translated to HTTP responses in ``app.main``."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ForbiddenError(DomainError):
    status_code = 403


class ConflictError(DomainError):
    status_code = 409


class ValidationFailedError(DomainError):
    status_code = 422


class DeviceError(DomainError):
    """A switch could not be reached or rejected a change."""

    status_code = 502
