"""Operational Environment Configuration and Settings.

Provides 12-factor environment variable loading and validation for the TwinVolt edge server.
Uses Pydantic v2 data validation without external uninstalled dependencies.
"""

import os
from typing import Any, Mapping, Optional
from pydantic import BaseModel, Field, field_validator

from src.gateway.base import GatewayOverflowPolicy


class AppSettings(BaseModel):
    """Central operational settings for the TwinVolt Edge Server.

    Reads from environment variables with conservative, deterministic defaults.
    """

    host: str = Field("0.0.0.0", description="Network host address to bind the ASGI server.")
    port: int = Field(8000, ge=1, le=65535, description="Network TCP port for the ASGI server.")
    log_level: str = Field("INFO", description="Standard logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).")
    gateway_autostart: bool = Field(False, description="Whether to automatically start the gateway on server boot.")
    gateway_queue_size: int = Field(1000, ge=1, le=100000, description="Max bounded queue capacity for gateway frames.")
    gateway_overflow_policy: GatewayOverflowPolicy = Field(
        GatewayOverflowPolicy.DROP_OLDEST,
        description="Overflow backpressure policy (DROP_OLDEST, DROP_NEWEST, BLOCK).",
    )
    storage_dir: str = Field("data/storage", description="Base filesystem directory for file-backed persistence.")

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if val not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                raise ValueError(f"Invalid log_level '{v}'. Must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
            return val
        return "INFO"

    @field_validator("gateway_overflow_policy", mode="before")
    @classmethod
    def _validate_overflow_policy(cls, v: Any) -> GatewayOverflowPolicy:
        if isinstance(v, GatewayOverflowPolicy):
            return v
        if isinstance(v, str):
            val = v.strip().upper()
            try:
                return GatewayOverflowPolicy(val)
            except ValueError:
                raise ValueError(
                    f"Invalid gateway_overflow_policy '{v}'. Must be DROP_OLDEST, DROP_NEWEST, or BLOCK."
                )
        return GatewayOverflowPolicy.DROP_OLDEST

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AppSettings":
        """Loads and parses settings from an environment mapping or os.environ."""
        source = os.environ if env is None else env
        kwargs: dict[str, Any] = {}

        if "TWINVOLT_HOST" in source:
            kwargs["host"] = source["TWINVOLT_HOST"]
        elif "API_HOST" in source:
            kwargs["host"] = source["API_HOST"]

        if "TWINVOLT_PORT" in source:
            kwargs["port"] = source["TWINVOLT_PORT"]
        elif "API_PORT" in source:
            kwargs["port"] = source["API_PORT"]

        if "TWINVOLT_LOG_LEVEL" in source:
            kwargs["log_level"] = source["TWINVOLT_LOG_LEVEL"]

        if "TWINVOLT_GATEWAY_AUTOSTART" in source:
            val = source["TWINVOLT_GATEWAY_AUTOSTART"].strip().lower()
            kwargs["gateway_autostart"] = val in ("true", "1", "yes", "on")

        if "TWINVOLT_GATEWAY_QUEUE_SIZE" in source:
            kwargs["gateway_queue_size"] = source["TWINVOLT_GATEWAY_QUEUE_SIZE"]

        if "TWINVOLT_GATEWAY_OVERFLOW_POLICY" in source:
            kwargs["gateway_overflow_policy"] = source["TWINVOLT_GATEWAY_OVERFLOW_POLICY"]

        if "TWINVOLT_STORAGE_DIR" in source:
            kwargs["storage_dir"] = source["TWINVOLT_STORAGE_DIR"]

        return cls(**kwargs)


_cached_settings: Optional[AppSettings] = None


def get_settings(env: Optional[Mapping[str, str]] = None, reload: bool = False) -> AppSettings:
    """Returns the cached global AppSettings instance, or creates a new one."""
    global _cached_settings
    if _cached_settings is None or reload or env is not None:
        settings = AppSettings.from_env(env)
        if env is None:
            _cached_settings = settings
        return settings
    return _cached_settings
