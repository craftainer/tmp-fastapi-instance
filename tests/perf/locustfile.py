"""Locust load test against a live, real-stack api -- see tests/perf/README.md.

Not collected by pytest at all (see ../README.md and pyproject.toml's pytest
addopts, which never reference this directory): Locust has its own headless
runner (`uv run locust -f tests/perf/locustfile.py ...`).
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

import httpx
from locust import HttpUser, between, events, task
from locust.env import Environment

from app.config import get_settings

# NFR-0024's ceilings: p95 latency (ms) per endpoint class, checked at the end of
# the run against environment.stats rather than per-request, since a single slow
# request shouldn't fail a whole load run the way an actual error does
# (--exit-code-on-error, passed on the command line, already covers that).
_P95_LATENCY_MS_CEILING = {"/health/live": 50}
_DEFAULT_P95_LATENCY_MS_CEILING = 200


@events.quitting.add_listener  # type: ignore[untyped-decorator] # locust ships no py.typed marker
def _check_latency_thresholds(environment: Environment, **_: object) -> None:
    """Fail the run (NFR-0024) if any endpoint's p95 latency exceeded its ceiling.

    locust's own --exit-code-on-error only covers request errors, not latency, so
    this is the piece that actually enforces NFR-0024's p95 numbers in CI.
    """
    for name, entry in environment.stats.entries.items():
        path = name[0]
        ceiling = _P95_LATENCY_MS_CEILING.get(path, _DEFAULT_P95_LATENCY_MS_CEILING)
        p95 = entry.get_response_time_percentile(0.95)
        if p95 > ceiling:
            print(f"NFR-0024 breach: {name} p95={p95}ms exceeds {ceiling}ms ceiling")
            environment.process_exit_code = 1


# Real Keycloak password-grant login, not POST /mock/token -- this suite targets
# the runner image's MODE=production stack (see docs/adrs/0010-locust-for-load-
# testing.md), and /mock/token is only mounted under MODE=mock (app.controllers.mock).
# Dev-realm password == username, same convention tests/e2e/conftest.py's
# access_token fixture relies on. "maintainer" specifically: each dev-realm user
# carries exactly one client role (realm-export.json), and heroes_v2.py's
# DeleteRoles only grants "maintainer" -- every task below needs read+write+delete.
_LOGIN_USERNAME = "maintainer"

_HERO_LIST_PATH = "/crud/v1/heroes/v2/json"


def _fetch_access_token() -> str:
    """Log in `_LOGIN_USERNAME` against the real dev-realm Keycloak and return their token.

    Duplicates tests/e2e/conftest.py's access_token(dev) branch rather than importing
    it -- tests/e2e/README.md's "Don't" forbids importing across test suites, and this
    suite isn't pytest-collected at all, so it can't share a fixture either way.
    """
    settings = get_settings()
    response = httpx.post(
        settings.oidc_token_url,
        data={
            "grant_type": "password",
            "client_id": settings.oidc_client_id,
            "username": _LOGIN_USERNAME,
            "password": _LOGIN_USERNAME,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]  # type: ignore[no-any-return]


class HeroesUser(HttpUser):
    """Simulates one client driving the Hero CRUD resource and the liveness probe."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Log in once per simulated user and reuse the resulting bearer token."""
        token = _fetch_access_token()
        self.client.headers["Authorization"] = f"Bearer {token}"

    def _create_hero(self) -> dict[str, Any] | None:
        """Create a throwaway Hero and return its JSON body, or None on failure."""
        payload = {
            "name": f"locust-{uuid.uuid4().hex[:8]}",
            "powers": ["flight"],
        }
        with self.client.post(_HERO_LIST_PATH, json=payload, catch_response=True) as response:
            if response.status_code != 201:
                response.failure(f"unexpected status {response.status_code}")
                return None
            return response.json()  # type: ignore[no-any-return]

    @task(10)
    def list_heroes(self) -> None:
        """List heroes -- the read path most traffic is weighted toward."""
        self.client.get(_HERO_LIST_PATH, name=_HERO_LIST_PATH)

    @task(5)
    def get_hero(self) -> None:
        """Create then fetch a single Hero by id."""
        hero = self._create_hero()
        if hero is None:
            return
        self.client.get(f"{_HERO_LIST_PATH}?id={hero['id']}", name=f"{_HERO_LIST_PATH}?id=")

    @task(3)
    def create_hero(self) -> None:
        """Create a Hero (write path)."""
        self._create_hero()

    @task(2)
    def update_hero(self) -> None:
        """Create then partially update a Hero."""
        hero = self._create_hero()
        if hero is None:
            return
        self.client.patch(
            f"{_HERO_LIST_PATH}?id={hero['id']}",
            json={"powers": [*hero["powers"], secrets.choice(["speed", "strength"])]},
            name=f"{_HERO_LIST_PATH}?id= [PATCH]",
        )

    @task(1)
    def delete_hero(self) -> None:
        """Create then delete a Hero, so load runs don't grow the table unbounded."""
        hero = self._create_hero()
        if hero is None:
            return
        self.client.delete(
            f"{_HERO_LIST_PATH}?id={hero['id']}", name=f"{_HERO_LIST_PATH}?id= [DELETE]"
        )

    @task(8)
    def health_live(self) -> None:
        """Hit the liveness probe -- cheap, unauthenticated, high-frequency traffic."""
        self.client.get("/health/live")
