"""Safe default response headers for API and browser-facing documentation."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


_PRODUCTION_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply non-secret browser defenses to every response.

    CSP is production-only because FastAPI's local Swagger UI loads its
    scripts and styles from a CDN. The production API policy intentionally
    permits only same-origin resources and contains no unsafe directives.
    """

    def __init__(self, app, *, production: bool) -> None:
        super().__init__(app)
        self.production = production

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["X-Frame-Options"] = "DENY"
        if self.production:
            response.headers["Content-Security-Policy"] = _PRODUCTION_CSP
        return response
