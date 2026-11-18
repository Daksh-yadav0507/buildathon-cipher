"""Insights Buddy: the server package.

ApiError lives here (not in api.py) so every module can raise it without
importing the app and causing an import loop.
"""


class ApiError(Exception):
    """Raise from any route or helper: the officer sees {"error": message}."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = int(status)
        self.message = str(message)


def fail(status: int, message: str):
    """Stop the request with a plain sentence for the officer, e.g. fail(404, "That record isn't in this case.")."""
    raise ApiError(status, message)


__all__ = ["ApiError", "fail"]
