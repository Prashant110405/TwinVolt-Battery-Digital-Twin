"""Unified Production Server Entrypoint for TwinVolt Digital Twin.

Launches the unified FastAPI ASGI application hosting REST APIs, WebSocket streams,
Static UI, and Edge Gateway Daemon on a single worker event loop.
"""

import argparse
import sys
import uvicorn

from src.config.settings import get_settings


def main() -> None:
    """Main execution function parsing CLI arguments and launching Uvicorn ASGI server."""
    parser = argparse.ArgumentParser(
        description="TwinVolt Universal Battery Digital Twin Edge Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", type=str, default=None, help="Host network interface to bind (e.g. 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="TCP port to listen on (e.g. 8000)")
    parser.add_argument("--log-level", type=str, default=None, help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument(
        "--gateway-autostart",
        action="store_true",
        default=None,
        help="Automatically start registered edge gateway sources upon server startup",
    )

    args = parser.parse_args()

    # Load baseline settings from environment
    settings = get_settings()

    # Apply CLI overrides if explicitly passed
    if args.host is not None:
        settings.host = args.host
    if args.port is not None:
        settings.port = args.port
    if args.log_level is not None:
        settings.log_level = args.log_level
    if args.gateway_autostart is not None:
        settings.gateway_autostart = args.gateway_autostart

    print("==================================================================")
    print("  TwinVolt — Universal Battery Digital Twin Platform")
    print(f"  Bound to: http://{settings.host}:{settings.port}")
    print(f"  UI:       http://{settings.host}:{settings.port}/ui")
    print(f"  Docs:     http://{settings.host}:{settings.port}/docs")
    print(f"  Gateway:  {'ENABLED (Autostart)' if settings.gateway_autostart else 'STANDBY'}")
    print("  Workers:  1 (Single-process state model)")
    print("==================================================================")

    # Launch Uvicorn with factory and strictly single worker
    uvicorn.run(
        "src.api.app:create_app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        factory=True,
        workers=1,
    )


if __name__ == "__main__":
    main()
