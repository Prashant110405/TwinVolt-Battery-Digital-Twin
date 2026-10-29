"""Cookie-session authentication, CSRF checks, and process-local login throttling."""

from __future__ import annotations

from collections import deque
import hmac
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from werkzeug.security import check_password_hash


class LoginAttemptLimiter:
    """Bounded process-local failed-login rate limiter for the single-worker server."""
    def __init__(self, max_failures: int = 5, window_seconds: int = 900, max_keys: int = 10_000) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            attempts = self._failures.get(key)
            if attempts is None:
                return 0
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            if not attempts:
                self._failures.pop(key, None)
                return 0
            if len(attempts) < self.max_failures:
                return 0
            return max(1, int(self.window_seconds - (now - attempts[0])))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            attempts = self._failures.setdefault(key, deque())
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            attempts.append(now)
            if len(self._failures) > self.max_keys:
                oldest = min(self._failures, key=lambda item: self._failures[item][0] if self._failures[item] else now)
                self._failures.pop(oldest, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


class AuthenticationManager:
    def __init__(self, users: dict[str, str], limiter: LoginAttemptLimiter | None = None) -> None:
        self.users = dict(users)
        self.limiter = limiter or LoginAttemptLimiter()
        if not self.users:
            raise ValueError("At least one authentication account is required.")
        # Validate encoded hashes at startup and prepare a dummy scrypt verification target
        # so unknown usernames still incur the same expensive password check.
        self._dummy_hash = next(iter(self.users.values()))
        try:
            check_password_hash(self._dummy_hash, secrets.token_urlsafe(32))
            for password_hash in self.users.values():
                check_password_hash(password_hash, secrets.token_urlsafe(32))
        except (ValueError, TypeError) as exc:
            raise ValueError("Authentication configuration contains an invalid Werkzeug scrypt hash.") from exc

    def authenticate(self, username: str, password: str, remote_key: str) -> bool:
        key = f"{remote_key}\0{username.casefold()}"
        if self.limiter.retry_after(key):
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.", headers={"Retry-After": str(self.limiter.retry_after(key))})
        password_hash = self.users.get(username, self._dummy_hash)
        try:
            valid = check_password_hash(password_hash, password)
        except (ValueError, TypeError):
            valid = False
        if valid and username in self.users:
            return True
        self.limiter.record_failure(key)
        return False


def session_user(scope: dict[str, Any], users: dict[str, str]) -> str | None:
    session = scope.get("session")
    username = session.get("username") if isinstance(session, dict) else None
    return username if isinstance(username, str) and username in users else None


def csrf_matches(session: dict[str, Any], provided: str | None) -> bool:
    expected = session.get("csrf_token")
    return isinstance(expected, str) and isinstance(provided, str) and hmac.compare_digest(expected, provided)


class AuthGuardMiddleware:
    """Fail-closed ASGI guard for all TwinVolt API and WebSocket operations."""
    _PUBLIC_API_PATHS = {
        "/api/v1/auth/session",
        "/api/v1/auth/csrf",
        "/api/v1/auth/login",
    }
    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, app: Any, users: dict[str, str]) -> None:
        self.app = app
        self.users = users

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
        path = scope.get("path", "")
        protected = path.startswith("/api/v1/") or path == "/health/details"
        if not protected or path in self._PUBLIC_API_PATHS:
            await self.app(scope, receive, send)
            return

        username = session_user(scope, self.users)
        if username is None:
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": 4401})
            else:
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error_type": "AuthenticationRequired", "message": "Authentication required.", "details": {}},
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
            return

        if scope_type == "http" and scope.get("method", "GET").upper() not in self._SAFE_METHODS:
            headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
            session = scope.get("session", {})
            if not csrf_matches(session, headers.get("x-csrf-token")):
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"error_type": "CSRFValidationError", "message": "CSRF validation failed.", "details": {}},
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return

        if scope_type == "websocket" and not self._same_origin_websocket(scope):
            await send({"type": "websocket.close", "code": 4403})
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _same_origin_websocket(scope: dict[str, Any]) -> bool:
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        origin, host = headers.get("origin"), headers.get("host")
        if not origin or not host:
            return False
        try:
            parsed = urlsplit(origin)
            scheme = scope.get("scheme", "ws").lower()
            expected_schemes = {"https", "wss"} if scheme in {"https", "wss"} else {"http", "ws"}
            return parsed.scheme.lower() in expected_schemes and parsed.netloc.lower() == host.lower()
        except ValueError:
            return False


async def require_authenticated(request: Request) -> str:
    """Dependency for sensitive HTTP routes outside the guarded API prefix."""
    manager: AuthenticationManager = request.app.state.auth_manager
    username = session_user(request.scope, manager.users)
    if username is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return username
