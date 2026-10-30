"""REST API Routes for Arduino Firmware Management and Workflow.

Provides secure firmware file listing, uploading, inspecting, static validation,
and controlled invocation of arduino-cli compiler/flasher when available.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/firmware", tags=["Arduino Firmware"])

FIRMWARE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "firmware" / "arduino"
MAX_FIRMWARE_SIZE_BYTES = 1024 * 1024  # 1 MB
ALLOWED_EXTENSIONS = {".ino", ".cpp", ".c", ".h", ".hpp"}


class FirmwareFileInfo(BaseModel):
    """Metadata describing a firmware source file."""
    filename: str
    size_bytes: int
    modified_iso: str
    extension: str
    is_example: bool = False


class FirmwareValidationResult(BaseModel):
    """Result of static or compiler validation on firmware source."""
    is_valid: bool
    filename: str
    board_fqbn: Optional[str] = None
    compiler_available: bool = False
    exit_code: Optional[int] = None
    output: str
    static_checks: dict[str, Any]


class FirmwareFlashResult(BaseModel):
    """Result of firmware upload / flashing operation."""
    success: bool
    filename: str
    port: str
    board_fqbn: str
    output: str
    exit_code: Optional[int] = None


def _get_firmware_dir() -> Path:
    """Ensures firmware workspace directory exists."""
    FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
    return FIRMWARE_DIR


def _sanitize_filename(name: str) -> str:
    """Sanitizes filename against path traversal and dangerous characters."""
    clean = os.path.basename(name.strip())
    # Strip any directory separators or null bytes
    clean = re.sub(r"[^\w\.-]", "_", clean)
    if not clean:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    ext = Path(clean).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    return clean


def _find_firmware_file(filename: str) -> Optional[Path]:
    """Finds a firmware file in either the arduino or esp32 workspace directories."""
    clean = _sanitize_filename(filename)
    candidates = [
        _get_firmware_dir() / clean,
        _get_firmware_dir().parent / "esp32" / clean,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@router.get("/files", response_model=dict[str, Any])
def list_firmware_files() -> dict[str, Any]:
    """Lists all available firmware files in the firmware workspace (Arduino & ESP32)."""
    search_dirs = [_get_firmware_dir(), _get_firmware_dir().parent / "esp32"]
    files: list[FirmwareFileInfo] = []
    seen_names: set[str] = set()

    for base_dir in search_dirs:
        if not base_dir.is_dir():
            continue
        for item in sorted(base_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in ALLOWED_EXTENSIONS and item.name not in seen_names:
                seen_names.add(item.name)
                stat = item.stat()
                from datetime import datetime, timezone
                mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                files.append(
                    FirmwareFileInfo(
                        filename=item.name,
                        size_bytes=stat.st_size,
                        modified_iso=mod_time,
                        extension=item.suffix.lower(),
                        is_example="example" in item.name.lower() or "esp32" in item.name.lower(),
                    )
                )

    return {"files": [f.model_dump() for f in files]}


@router.get("/files/{filename}")
def get_firmware_content(filename: str):
    """Returns the raw source text of a specific firmware file."""
    target = _find_firmware_file(filename)
    if not target or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Firmware file '{filename}' not found.")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return PlainTextResponse(content, media_type="text/plain")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error reading file: {exc}")


@router.get("/files/{filename}/download")
def download_firmware_file(filename: str):
    """Downloads the firmware source file."""
    target = _find_firmware_file(filename)
    if not target or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Firmware file '{filename}' not found.")
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


@router.post("/upload", response_model=FirmwareFileInfo)
async def upload_firmware_file(file: UploadFile = File(...)) -> FirmwareFileInfo:
    """Uploads or imports a new firmware source file into the workspace."""
    clean_name = _sanitize_filename(file.filename or "sketch.ino")
    content = await file.read(MAX_FIRMWARE_SIZE_BYTES + 1024)

    if len(content) > MAX_FIRMWARE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum permitted size of {MAX_FIRMWARE_SIZE_BYTES // 1024} KB.",
        )

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    target = _get_firmware_dir() / clean_name
    try:
        target.write_bytes(content)
        stat = target.stat()
        from datetime import datetime, timezone
        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return FirmwareFileInfo(
            filename=clean_name,
            size_bytes=len(content),
            modified_iso=mod_time,
            extension=target.suffix.lower(),
            is_example=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save firmware: {exc}")


class SaveFirmwareRequest(BaseModel):
    filename: str
    content: str


@router.post("/save", response_model=FirmwareFileInfo)
def save_firmware_file(req: SaveFirmwareRequest) -> FirmwareFileInfo:
    """Saves updated source code text to a firmware file."""
    clean_name = _sanitize_filename(req.filename)
    encoded = req.content.encode("utf-8")
    if len(encoded) > MAX_FIRMWARE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Content exceeds maximum permitted size of {MAX_FIRMWARE_SIZE_BYTES // 1024} KB.",
        )
    target = _get_firmware_dir() / clean_name
    try:
        target.write_bytes(encoded)
        stat = target.stat()
        from datetime import datetime, timezone
        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return FirmwareFileInfo(
            filename=clean_name,
            size_bytes=len(encoded),
            modified_iso=mod_time,
            extension=target.suffix.lower(),
            is_example="example" in clean_name.lower(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")


class VerifyRequest(BaseModel):
    filename: str
    board_fqbn: Optional[str] = "arduino:avr:uno"


@router.post("/verify", response_model=FirmwareValidationResult)
def verify_firmware(req: VerifyRequest) -> FirmwareValidationResult:
    """Performs static checks and runs arduino-cli verification if installed."""
    clean = _sanitize_filename(req.filename)
    target = _get_firmware_dir() / clean
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Firmware file '{clean}' not found.")

    text = target.read_text(encoding="utf-8", errors="replace")

    # Static checks
    has_setup = bool(re.search(r"\bvoid\s+setup\s*\(", text))
    has_loop = bool(re.search(r"\bvoid\s+loop\s*\(", text))
    has_serial_begin = bool(re.search(r"\bSerial\.begin\s*\(", text))

    detected_baud = None
    direct_baud_match = re.search(r"\bSerial\.begin\s*\(\s*(\d+)", text)
    if direct_baud_match:
        detected_baud = int(direct_baud_match.group(1))
    else:
        var_match = re.search(r"\bSerial\.begin\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)", text)
        if var_match:
            var_name = var_match.group(1)
            val_match = re.search(rf"\b{var_name}\s*=\s*(\d+)", text)
            if val_match:
                detected_baud = int(val_match.group(1))

    static_checks = {
        "has_setup_function": has_setup,
        "has_loop_function": has_loop,
        "has_serial_begin": has_serial_begin,
        "detected_baud_rate": detected_baud,
        "line_count": len(text.splitlines()),
    }

    # Check if arduino-cli is present on system PATH
    cli_path = shutil.which("arduino-cli")
    if cli_path is None:
        # Static checks only
        is_valid = has_setup and has_loop and has_serial_begin
        output_msg = (
            "Static verification passed: valid Arduino structure detected (setup(), loop(), Serial.begin()).\n"
            "Note: 'arduino-cli' is not installed on this system host.\n"
            "To enable actual compilation, install arduino-cli: https://arduino.github.io/arduino-cli/"
        ) if is_valid else (
            "Static verification warning: Missing standard Arduino structure. "
            f"(setup={has_setup}, loop={has_loop}, Serial.begin={has_serial_begin})"
        )
        return FirmwareValidationResult(
            is_valid=is_valid,
            filename=clean,
            board_fqbn=req.board_fqbn,
            compiler_available=False,
            output=output_msg,
            static_checks=static_checks,
        )

    # If arduino-cli is installed, run compile with timeout
    try:
        res = subprocess.run(
            [cli_path, "compile", "--fqbn", req.board_fqbn or "arduino:avr:uno", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (res.stdout + "\n" + res.stderr).strip()
        return FirmwareValidationResult(
            is_valid=(res.returncode == 0),
            filename=clean,
            board_fqbn=req.board_fqbn,
            compiler_available=True,
            exit_code=res.returncode,
            output=output or "Compilation succeeded with 0 errors.",
            static_checks=static_checks,
        )
    except subprocess.TimeoutExpired:
        return FirmwareValidationResult(
            is_valid=False,
            filename=clean,
            board_fqbn=req.board_fqbn,
            compiler_available=True,
            output="Compilation timed out after 30 seconds.",
            static_checks=static_checks,
        )
    except Exception as exc:
        return FirmwareValidationResult(
            is_valid=False,
            filename=clean,
            board_fqbn=req.board_fqbn,
            compiler_available=True,
            output=f"Error executing arduino-cli: {exc}",
            static_checks=static_checks,
        )


class FlashRequest(BaseModel):
    filename: str
    port: str
    board_fqbn: str = "arduino:avr:uno"


@router.post("/flash", response_model=FirmwareFlashResult)
def flash_firmware(req: FlashRequest) -> FirmwareFlashResult:
    """Flashes firmware to connected hardware using local arduino-cli if configured."""
    clean = _sanitize_filename(req.filename)
    target = _get_firmware_dir() / clean
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Firmware file '{clean}' not found.")

    cli_path = shutil.which("arduino-cli")
    if cli_path is None:
        return FirmwareFlashResult(
            success=False,
            filename=clean,
            port=req.port,
            board_fqbn=req.board_fqbn,
            output=(
                "Direct flashing requires 'arduino-cli' installed on the machine with access to the serial port.\n"
                "Please either install arduino-cli (https://arduino.github.io/arduino-cli/) or open the source file "
                f"'{clean}' in Arduino IDE and click Upload."
            ),
            exit_code=-1,
        )

    try:
        res = subprocess.run(
            [
                cli_path,
                "compile",
                "--upload",
                "-p",
                req.port,
                "--fqbn",
                req.board_fqbn,
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = (res.stdout + "\n" + res.stderr).strip()
        return FirmwareFlashResult(
            success=(res.returncode == 0),
            filename=clean,
            port=req.port,
            board_fqbn=req.board_fqbn,
            output=combined,
            exit_code=res.returncode,
        )
    except subprocess.TimeoutExpired:
        return FirmwareFlashResult(
            success=False,
            filename=clean,
            port=req.port,
            board_fqbn=req.board_fqbn,
            output="Upload timed out after 60 seconds.",
            exit_code=-1,
        )
    except Exception as exc:
        return FirmwareFlashResult(
            success=False,
            filename=clean,
            port=req.port,
            board_fqbn=req.board_fqbn,
            output=f"Flashing failed: {exc}",
            exit_code=-1,
        )
