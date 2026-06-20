"""SQLAlchemy ORM models — Account, Character, AdminStaff, AccountSceneImage."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fablestar.state.postgres import Base


def default_character_stats() -> dict:
    return {
        "strength": 10,
        "dexterity": 10,
        "intelligence": 10,
        "perception": 10,
        "conduit": {
            "version": 1,
            "conduit_attributes": {
                "FRT": 10,
                "RFX": 10,
                "ACU": 10,
                "RSV": 10,
                "PRS": 10,
            },
            "proficiencies": {},
            "archive_domain_spent": {},
            "combat_hybrid_legacy": True,
        },
    }


class Account(Base):
    """Player account credentials and metadata."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    # Spendable balance for AI art (portraits / scene art); display label from comfyui.currency_display_name (e.g. pixels).
    echo_credits: Mapped[int] = mapped_column(Integer, default=0)
    # In-game GM crown / staff-visible play account (separate from admin_staff console logins).
    is_gm: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    characters: Mapped[list["Character"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    scene_images: Mapped[list["AccountSceneImage"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class AccountSceneImage(Base):
    """Per-account history of ComfyUI scene images (player gallery)."""

    __tablename__ = "account_scene_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    image_url: Mapped[str] = mapped_column(String(2048))
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    prompt_preview: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped["Account"] = relationship(back_populates="scene_images")


class Character(Base):
    """Persistent game character data linked to an account."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Portrait: URL served under Nexus /media/portraits/... when generated locally; optional.
    portrait_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    portrait_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Last ComfyUI scene image this character paid for; served under /media/rooms/ or /media/room-art/.
    last_scene_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # World state
    room_id: Mapped[str] = mapped_column(String(255), default="test_zone:entrance")
    # In-world wallet (display name from server.game_currency_display_name, e.g. Digi).
    digi_balance: Mapped[int] = mapped_column(Integer, default=0)
    # Opt-in player vs player; default off until toggled in-game or by admin.
    pvp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Moral standing for UI (-100 evil .. 0 neutral .. +100 good); gameplay can widen range later.
    reputation: Mapped[int] = mapped_column(Integer, default=0)

    # Generic stats/data stored as JSON for "Vibe Coding" flexibility
    # This allows us to add stats without frequent schema migrations
    stats: Mapped[dict] = mapped_column(JSON, default=default_character_stats)

    inventory: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="characters")


class AdminStaff(Base):
    """Console staff (head admin, admin, GM) with optional tool/zone restrictions."""

    __tablename__ = "admin_staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    # head_admin | admin | gm
    role: Mapped[str] = mapped_column(String(32), default="gm")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # {"tools": ["dashboard", "players", ...], "zones": ["*"] | ["zone_id", ...]}
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
