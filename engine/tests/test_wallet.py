"""Engine wallet: balances in the world's declared currencies, never a hardcoded one."""

from types import SimpleNamespace

import pytest

from sage import lexicon
from sage.world.package import Currency, available_worlds, load_world_package
from sage.world.wallet import Wallet, WalletError
from tests.fakes import ROOT


def _world(*currencies: Currency) -> SimpleNamespace:
    return SimpleNamespace(id="test", currencies=list(currencies))


def _two() -> Wallet:
    return Wallet(
        _world(
            Currency(key="shells", label="currency.shells.name", starting=7),
            Currency(key="pearls", label="currency.pearls.name"),
        )
    )


def test_primary_currency_is_the_first_declared():
    wallet = _two()
    assert wallet.key() == "shells"
    assert wallet.starting() == 7
    stats: dict = {}
    wallet.credit(stats, 5)
    assert stats == {"shells": 5}


def test_debit_refuses_overdraft_and_takes_nothing():
    wallet = _two()
    stats = {"shells": 3}
    assert wallet.debit(stats, 4) is False
    assert stats["shells"] == 3
    assert wallet.debit(stats, 3) is True
    assert wallet.balance(stats) == 0


def test_take_up_to_bills_down_to_zero():
    wallet = _two()
    stats = {"shells": 4}
    assert wallet.take_up_to(stats, 10) == 4
    assert wallet.balance(stats) == 0


def test_named_currency_and_unknown_currency():
    wallet = _two()
    stats: dict = {}
    wallet.credit(stats, 2, key="pearls")
    assert wallet.balance(stats, "pearls") == 2 and wallet.balance(stats) == 0
    with pytest.raises(WalletError):
        wallet.credit(stats, 1, key="gold")


def test_negative_amounts_are_refused():
    wallet = _two()
    with pytest.raises(WalletError):
        wallet.credit({}, -1)
    with pytest.raises(WalletError):
        wallet.debit({}, -1)


def test_world_without_currencies_has_a_disabled_wallet():
    wallet = Wallet(_world())
    assert not wallet.enabled
    assert wallet.balance({"gold": 50}) == 0
    with pytest.raises(WalletError):
        wallet.credit({}, 1)


@pytest.mark.parametrize("world_id", available_worlds(ROOT / "worlds"))
def test_every_world_names_its_primary_currency_through_the_lexicon(world_id):
    world = load_world_package(ROOT / "worlds" / world_id)
    previous = lexicon.active()
    lexicon.set_active(lexicon.build_lexicon(world.lexicon_dir))
    try:
        wallet = Wallet(world)
        assert wallet.key() == world.currencies[0].key
        name = wallet.name()
        assert name and not name.startswith("["), f"{world_id}: missing {world.currencies[0].label}"
    finally:
        lexicon.set_active(previous)
