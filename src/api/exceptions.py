"""API Exception Mapping and Handlers.

Translates domain and application service exceptions into standard HTTP problem
responses with appropriate status codes without altering service exception types.
"""

from typing import Any, Mapping
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.exceptions import TwinVoltDomainError
from src.services.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidServiceOperationError,
    PackNotFoundError,
    ServiceError,
    TwinNotFoundError,
)


def create_error_response(
    status_code: int,
    error_type: str,
    message: str,
    service_name: str = "TwinVoltService",
    details: Mapping[str, Any] = None,
) -> JSONResponse:
    """Creates a standardized JSON error response structure."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error_type": error_type,
            "message": message,
            "service_name": service_name,
            "details": dict(details) if details else {},
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers for domain and service errors on the FastAPI application."""

    @app.exception_handler(PackNotFoundError)
    async def pack_not_found_handler(request: Request, exc: PackNotFoundError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="PackNotFoundError",
            message=str(exc),
            service_name=exc.service_name or "PackManagementService",
            details=exc.details,
        )

    @app.exception_handler(TwinNotFoundError)
    async def twin_not_found_handler(request: Request, exc: TwinNotFoundError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="TwinNotFoundError",
            message=str(exc),
            service_name=exc.service_name or "TwinApplicationService",
            details=exc.details,
        )

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="EntityNotFoundError",
            message=str(exc),
            service_name=exc.service_name or "TwinVoltService",
            details=exc.details,
        )

    @app.exception_handler(DuplicateEntityError)
    async def duplicate_entity_handler(request: Request, exc: DuplicateEntityError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_type="DuplicateEntityError",
            message=str(exc),
            service_name=exc.service_name or "TwinVoltService",
            details=exc.details,
        )

    @app.exception_handler(InvalidServiceOperationError)
    async def invalid_service_operation_handler(
        request: Request, exc: InvalidServiceOperationError
    ) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_type="InvalidServiceOperationError",
            message=str(exc),
            service_name=exc.service_name or "TwinVoltService",
            details=exc.details,
        )

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_type=exc.__class__.__name__,
            message=str(exc),
            service_name=exc.service_name or "TwinVoltService",
            details=exc.details,
        )

    @app.exception_handler(TwinVoltDomainError)
    async def domain_error_handler(request: Request, exc: TwinVoltDomainError) -> JSONResponse:
        return create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type=exc.__class__.__name__,
            message=str(exc),
            service_name="TwinVoltDomain",
            details=getattr(exc, "details", {}),
        )
