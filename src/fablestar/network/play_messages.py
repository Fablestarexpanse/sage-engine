"""Play protocol message schemas — the contract between Nexus and the player UI.

WebSocket /play flow
--------------------
1. Client connects and sends one JSON handshake line: ``PlayHandshake``.
2. Server replies with a ``PlayError`` JSON line on failure and closes, or on
   success sends a ``CharacterSnapshotNotice`` JSON line followed by plain-text
   game output. All subsequent client lines are raw command text.

REST /play/* responses
----------------------
Every endpoint returns JSON with an ``ok`` discriminator. Failures are
``PlayError``; successes extend ``PlayAccountResponse`` (account + character
list + economy fields) with endpoint-specific keys documented below.
"""

from typing import Any, Literal, TypedDict


class PlayHandshake(TypedDict, total=False):
    """First WebSocket message from the client.

    Auth is either ``token`` (play session token from /play/auth/login, preferred)
    or ``username`` + ``password``.
    """

    token: str
    username: str
    password: str
    character_id: int  # optional: required only when the account has several characters


class PlayError(TypedDict):
    """Failure shape for both WebSocket handshake errors and REST endpoints."""

    ok: Literal[False]
    error: str


class CharacterSnapshotNotice(TypedDict):
    """First WebSocket line after successful auth (client renders the sheet)."""

    client_notice: Literal["character_snapshot"]
    character_name: str
    stats: dict[str, Any]
    resonance_levels_total: int


class CharacterPayload(TypedDict):
    """One character entry, as built by PlayerService.character_play_dict()."""

    id: int
    name: str
    room_id: str
    portrait_url: str | None
    portrait_prompt: str | None
    last_scene_image_url: str | None
    digi_balance: int
    pvp_enabled: bool
    reputation: int
    stats: dict[str, Any]
    resonance_levels_total: int


class PlayAccountResponse(TypedDict, total=False):
    """Success shape shared by login / register / refresh / create / delete.

    Endpoint-specific extras:
    - /play/characters/create adds ``character`` (the new CharacterPayload),
      optional ``cost_charged``, ``portrait_generation_failed``,
      ``portrait_generation_detail``.
    - /play/characters/portrait returns ``portrait_url`` + ``cost_charged``
      instead of the character list.
    - /play/scene/suggest-prompt returns ``prompt``.
    - /play/scene/generate returns ``scene_image_url`` + ``cost_charged``.
    """

    ok: Literal[True]
    username: str
    account_id: int
    characters: list[CharacterPayload]
    echo_credits: int
    is_gm: bool
    # Present on login/register responses: play session token for later /play/* calls
    # and the WebSocket handshake (send as "token"; supersedes password re-transmission).
    play_token: str
    # Economy fields (EconomyService.public_fields)
    currency_display_name: str
    game_currency_display_name: str
    pixels_per_usd: int
