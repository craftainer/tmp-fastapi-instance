"""Shared unit-test fixtures: an all-roles auth override for RBAC-protected routes."""

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.main import app
from app.oidc import get_current_claims

ALL_ROLES = ["viewer", "editor", "maintainer", "security", "detective"]


@pytest.fixture
def authed() -> Iterator[None]:
    """Override get_current_claims to grant every RBAC role, for the test's duration."""
    settings = get_settings()
    app.dependency_overrides[get_current_claims] = lambda: {
        "sub": "test-user",
        "resource_access": {settings.oidc_client_id: {"roles": ALL_ROLES}},
    }
    yield
    del app.dependency_overrides[get_current_claims]
