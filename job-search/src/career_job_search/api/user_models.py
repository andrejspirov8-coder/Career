from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    email: str
    created_at: datetime


class UserRow(BaseModel):
    user_id: str
    email: str
    password_hash: str
    password_salt: str
    created_at: str
