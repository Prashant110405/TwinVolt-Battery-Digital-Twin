"""Vercel Serverless Function entrypoint for TwinVolt FastAPI Application.

Exports the initialized FastAPI instance `app` for Vercel Python runtime execution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to sys.path so 'src' and 'config' can be resolved
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.app import create_app
from src.config.settings import AppSettings

# Configure independent operational settings for Vercel Serverless environment
# without mutating global singleton cached settings
settings = AppSettings.from_env()
if "TWINVOLT_SEED_DEFAULTS" not in os.environ:
    settings.seed_defaults = True

app = create_app(settings=settings)
