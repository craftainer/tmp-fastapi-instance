"""RFC 9457 Problem Details error responses.

Registers handlers that turn every HTTPException (including every existing
`raise HTTPException(...)` in app.controllers/app.oidc, unchanged), FastAPI's
request validation errors, and any other unhandled exception into a single
consistent `application/problem+json` body, instead of FastAPI's default
`{"detail": ...}` shape.
"""

import logging
from collections.abc import Sequence
from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ProblemDetailResponse(JSONResponse):
    """A JSONResponse whose media type is application/problem+json, per RFC 9457."""

    media_type = "application/problem+json"


def _problem(
    *, status_code: int, title: str, detail: str | Sequence[object], instance: str
) -> ProblemDetailResponse:
    """Build an RFC 9457 problem-details body for the given status/title/detail."""
    return ProblemDetailResponse(
        status_code=status_code,
        content={
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": instance,
        },
    )


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> ProblemDetailResponse:
    """Render any raised HTTPException as a problem-details body."""
    return _problem(
        status_code=exc.status_code,
        title=HTTPStatus(exc.status_code).phrase,
        detail=exc.detail,
        instance=request.url.path,
    )


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> ProblemDetailResponse:
    """Render a request validation failure as a problem-details body."""
    return _problem(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        title=HTTPStatus.UNPROCESSABLE_CONTENT.phrase,
        detail=exc.errors(),
        instance=request.url.path,
    )


async def _handle_unhandled_exception(  # pragma: no cover
    request: Request, exc: Exception
) -> ProblemDetailResponse:
    """Render any otherwise-unhandled exception as a generic 500 problem-details body.

    `detail` includes the exception message only when MODE=dev -- mock/production
    hide it to avoid leaking internals, matching the debug=... split in app.main.

    The body's `# pragma: no cover` is for tests/e2e specifically: none of this
    app's routes raise an unhandled exception on any real input, so there's no
    live request that reaches this handler -- tests/unit/test_problem_details.py
    exercises it directly (against a throwaway route built to raise) and still
    counts toward its own 95% gate.
    """
    logger.exception("Unhandled exception for %s", request.url.path, exc_info=exc)
    detail = str(exc) if settings.mode == "dev" else "Internal Server Error"
    return _problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title=HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
        detail=detail,
        instance=request.url.path,
    )


def register_problem_handlers(app: FastAPI) -> None:
    """Register the RFC 9457 exception handlers on the given app.

    Uses the `exception_handler` decorator form (called directly, not as `@`) rather
    than `add_exception_handler`: its `DecoratedCallable` TypeVar preserves each
    handler's own (narrower) exception-argument type instead of widening it to the
    bare `Exception` `add_exception_handler`'s stub requires.
    """
    app.exception_handler(StarletteHTTPException)(_handle_http_exception)
    app.exception_handler(RequestValidationError)(_handle_validation_error)
    app.exception_handler(Exception)(_handle_unhandled_exception)
