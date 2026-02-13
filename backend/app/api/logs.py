# -*- coding: utf-8 -*-
"""Logs management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.api.dependencies import require_admin
from app.models.user import User
from app.schemas.logs import (
    LogClearRequest,
    LogClearResponse,
    LogEntryResponse,
    LogFileResponse,
    LogFilesResponse,
    LogListResponse,
    LogType,
)
from app.services.log_service import get_log_service

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/files", response_model=LogFilesResponse)
async def get_log_files(
    current_user: User = Depends(require_admin()),
):
    service = get_log_service()
    files = service.get_log_files()

    return LogFilesResponse(
        files=[
            LogFileResponse(name=f.name, size=f.size, modified=f.modified)
            for f in files
        ]
    )


@router.get("", response_model=LogListResponse)
async def get_logs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Page size"),
    level: Optional[str] = Query(
        default=None,
        description="Log level: DEBUG/INFO/WARNING/ERROR/CRITICAL",
    ),
    keyword: Optional[str] = Query(default=None, description="Message keyword"),
    start_time: Optional[str] = Query(default=None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(default=None, description="End time (ISO format)"),
    current_user: User = Depends(require_admin()),
):
    if level and level.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid log level",
        )

    service = get_log_service()
    entries, total = service.read_log_paginated(
        level=level,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    return LogListResponse(
        items=[
            LogEntryResponse(
                timestamp=e.timestamp,
                level=e.level,
                source=e.logger_name,
                message=e.message,
            )
            for e in entries
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/download")
async def download_log(
    log_type: LogType = Query(default=LogType.app, description="Log type: app or error"),
    current_user: User = Depends(require_admin()),
):
    filename = f"{log_type.value}.log"
    service = get_log_service()
    content = service.get_log_content(filename)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log file not found",
        )

    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/clear", response_model=LogClearResponse)
async def clear_logs(
    body: LogClearRequest,
    current_user: User = Depends(require_admin()),
):
    service = get_log_service()
    filename = f"{body.log_type.value}.log"

    success = service.clear_log(filename)
    return LogClearResponse(
        success=success,
        message=f"Log file {filename} cleared" if success else "Failed to clear log file",
        cleared_count=1 if success else 0,
    )
