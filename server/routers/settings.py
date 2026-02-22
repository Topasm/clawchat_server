import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from models.user_settings import UserSettings
from schemas.settings import SettingsPayload, SettingsResponse

router = APIRouter(tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user)
    )
    row = result.scalar_one_or_none()

    if row is None:
        return SettingsResponse(settings={}, updated_at="")

    return SettingsResponse(
        settings=json.loads(row.settings_json),
        updated_at=row.updated_at.isoformat(),
    )


@router.put("", response_model=SettingsResponse)
async def save_settings(
    payload: SettingsPayload,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user)
    )
    row = result.scalar_one_or_none()

    # Build the incoming dict (only non-None fields)
    incoming = payload.model_dump(exclude_none=True)

    if row is None:
        row = UserSettings(user_id=user, settings_json=json.dumps(incoming))
        db.add(row)
    else:
        existing = json.loads(row.settings_json)
        existing.update(incoming)
        row.settings_json = json.dumps(existing)

    await db.commit()
    await db.refresh(row)

    return SettingsResponse(
        settings=json.loads(row.settings_json),
        updated_at=row.updated_at.isoformat(),
    )
