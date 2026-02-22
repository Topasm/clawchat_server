import os
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from config import settings as app_settings
from database import get_db
from exceptions import NotFoundError, ValidationError
from models.attachment import Attachment
from schemas.attachment import AttachmentResponse
from utils import make_id

router = APIRouter()

_ALLOWED_EXTENSIONS: set[str] | None = None


def _get_allowed_extensions() -> set[str]:
    global _ALLOWED_EXTENSIONS
    if _ALLOWED_EXTENSIONS is None:
        _ALLOWED_EXTENSIONS = {
            ext.strip().lower() for ext in app_settings.allowed_extensions.split(",") if ext.strip()
        }
    return _ALLOWED_EXTENSIONS


def _to_response(att: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=att.id,
        filename=att.filename,
        stored_filename=att.stored_filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        memo_id=att.memo_id,
        todo_id=att.todo_id,
        url=f"/api/attachments/{att.id}/download",
        created_at=att.created_at,
    )


@router.post("", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    memo_id: str | None = Query(None),
    todo_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    if not file.filename:
        raise ValidationError("No filename provided")

    # Validate extension
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _get_allowed_extensions():
        raise ValidationError(f"File type '.{ext}' is not allowed")

    # Read file content and validate size
    content = await file.read()
    max_bytes = app_settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"File exceeds maximum size of {app_settings.max_upload_size_mb}MB")

    # Store file on disk
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(app_settings.upload_dir, stored_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Create DB record
    attachment = Attachment(
        id=make_id("att_"),
        filename=file.filename,
        stored_filename=stored_filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        memo_id=memo_id,
        todo_id=todo_id,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return _to_response(attachment)


@router.get("", response_model=list[AttachmentResponse])
async def list_attachments(
    memo_id: str | None = Query(None),
    todo_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    q = select(Attachment).order_by(Attachment.created_at.desc())
    if memo_id:
        q = q.where(Attachment.memo_id == memo_id)
    if todo_id:
        q = q.where(Attachment.todo_id == todo_id)
    rows = (await db.execute(q)).scalars().all()
    return [_to_response(att) for att in rows]


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise NotFoundError("Attachment not found")

    file_path = os.path.join(app_settings.upload_dir, attachment.stored_filename)
    if not os.path.exists(file_path):
        raise NotFoundError("Attachment file not found on disk")

    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise NotFoundError("Attachment not found")

    # Remove file from disk
    file_path = os.path.join(app_settings.upload_dir, attachment.stored_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    await db.delete(attachment)
    await db.commit()
