# Multi-Architecture Dockerfile for TwinVolt Edge Server (ARM64 / AMD64)
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TWINVOLT_HOST=0.0.0.0 \
    TWINVOLT_PORT=8000 \
    TWINVOLT_LOG_LEVEL=INFO

WORKDIR /app

# Install runtime system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    numpy \
    scipy \
    pyyaml

# Expose HTTP / WebSocket API port
EXPOSE 8000

# Health check using the liveness endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Launch single-worker TwinVolt server
CMD ["python", "-m", "src.server"]
