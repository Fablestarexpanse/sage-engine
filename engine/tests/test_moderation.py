"""Moderation rules that need no database: address parsing, mutes stop chat, settings file."""

from __future__ import annotations

import asyncio
import tomllib
from datetime import datetime, timedelta

import pytest

from sage import app as app_module
from sage import lexicon
from sage.core.config import ModerationConfig
from sage.core.moderation_persist import save_moderation_toml
from sage.network.session import SessionManager
from sage.services import moderation
from tests.fakes import StubSession, make_fake_server


@pytest.mark.parametrize(
    "text, normal",
    [
        ("203.0.113.7", "203.0.113.7/32"),
        (" 203.0.113.9/24 ", "203.0.113.0/24"),
        ("2001:db8::1", "2001:db8::1/128"),
    ],
)
def test_bans_accept_addresses_and_ranges(text, normal):
    assert moderation.parse_network(text) == normal


@pytest.mark.parametrize("text", ["", "example.com", "300.1.1.1", "10.0.0.0/99"])
def test_bans_refuse_anything_else(text):
    with pytest.raises(ValueError):
        moderation.parse_network(text)


def test_defaults_record_no_addresses_and_keep_registration_open():
    rules = ModerationConfig()
    assert rules.record_login_addresses is False
    assert rules.registration_open is True
    assert rules.login_history_days == 30


def test_settings_file_round_trips(tmp_path):
    rules = ModerationConfig(
        registration_open=False, record_login_addresses=True, login_history_days=7
    )
    path = save_moderation_toml(rules, tmp_path / "moderation.toml")
    assert ModerationConfig.model_validate(tomllib.loads(path.read_text())) == rules


def test_a_muted_character_cannot_say_emote_or_tell():
    from sage.commands.registry import registry

    registry.load_module_strict("sage.commands.communication")
    server = make_fake_server()
    server.session_manager = SessionManager()
    speaker, listener = StubSession("Loud"), StubSession("Quiet")
    listener.id = "listener"
    server.session_manager.sessions = {speaker.id: speaker, listener.id: listener}
    server.session_manager.player_to_session = {"Loud": speaker.id, "Quiet": listener.id}
    speaker.muted_until = datetime.utcnow() + timedelta(minutes=5)
    saved = app_module.app_instance
    app_module.app_instance = server  # type: ignore[assignment]
    try:

        async def run():
            await server.redis.set_player_location("Loud", "z:r")
            await server.redis.set_player_location("Quiet", "z:r")
            for line in ("say hello", "emote waves", "tell Quiet hi"):
                await server.dispatcher.dispatch(speaker, line)
            speaker.muted_until = datetime.utcnow() - timedelta(seconds=1)  # the mute ran out
            await server.dispatcher.dispatch(speaker, "say free again")

        asyncio.run(run())
    finally:
        app_module.app_instance = saved
    muted_line = lexicon.t("moderation.muted")
    assert speaker.sent.count(muted_line) == 3
    heard = "\n".join(listener.sent)
    assert "hello" not in heard and "waves" not in heard and "hi" not in heard
    assert "free again" in heard


def test_an_ipv4_address_carried_in_ipv6_is_read_as_ipv4():
    assert str(moderation._address("::ffff:203.0.113.7")) == "203.0.113.7"
    assert str(moderation._address("::1")) == "::1"
    assert moderation._address("localhost") is None
