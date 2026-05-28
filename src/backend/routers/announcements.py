"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Payload for creating or updating announcements."""

    message: str = Field(..., min_length=1, max_length=500)
    starts_at: Optional[datetime] = None
    expires_at: datetime

    @field_validator("message")
    @classmethod
    def validate_message(cls, message: str) -> str:
        message = message.strip()
        if not message:
            raise ValueError("Message cannot be empty")
        return message

    @model_validator(mode="after")
    def validate_dates(self) -> "AnnouncementPayload":
        starts_at = ensure_utc_datetime(self.starts_at)
        expires_at = ensure_utc_datetime(self.expires_at)

        if starts_at and expires_at <= starts_at:
            raise ValueError("Expiration date must be later than start date")

        self.starts_at = starts_at
        self.expires_at = expires_at
        return self


def ensure_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime values to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize announcement for API responses."""
    starts_at = ensure_utc_datetime(announcement.get("starts_at"))
    expires_at = ensure_utc_datetime(announcement["expires_at"])
    return {
        "id": str(announcement["_id"]),
        "message": announcement["message"],
        "starts_at": starts_at.isoformat() if starts_at else None,
        "expires_at": expires_at.isoformat()
    }


def require_authenticated_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Validate teacher authentication by username."""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently active."""
    now = datetime.now(timezone.utc)
    query = {
        "expires_at": {"$gt": now},
        "$or": [
            {"starts_at": None},
            {"starts_at": {"$exists": False}},
            {"starts_at": {"$lte": now}}
        ]
    }
    announcements = announcements_collection.find(query).sort("expires_at", 1)
    return [serialize_announcement(announcement) for announcement in announcements]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management."""
    require_authenticated_teacher(teacher_username)
    announcements = announcements_collection.find({}).sort("expires_at", 1)
    return [serialize_announcement(announcement) for announcement in announcements]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create an announcement."""
    require_authenticated_teacher(teacher_username)

    document = payload.model_dump()
    result = announcements_collection.insert_one(document)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")
    return serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an announcement."""
    require_authenticated_teacher(teacher_username)
    try:
        object_id = ObjectId(announcement_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid announcement ID") from error

    result = announcements_collection.update_one(
        {"_id": object_id},
        {"$set": payload.model_dump()}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")
    return serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement."""
    require_authenticated_teacher(teacher_username)
    try:
        object_id = ObjectId(announcement_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid announcement ID") from error

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted successfully"}
