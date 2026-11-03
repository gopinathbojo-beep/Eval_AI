"""School management access check, and the account patch shape the admin console uses. Teachers were retired."""

from fastapi import Depends
from pydantic import BaseModel, EmailStr, Field, field_validator

from ..deps import err
from ..models import Teacher
from ..security import current_teacher
from .registration import RegisterIn


def management(user: Teacher = Depends(current_teacher)):
    if user.role != "MANAGEMENT":
        raise err(403, "MANAGEMENT_REQUIRED", "School management access is required.")
    return user


class TeacherPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    password: str | None = Field(None, min_length=8, max_length=72)
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def password_valid(cls, value):
        return RegisterIn.password_bytes(value) if value else value
