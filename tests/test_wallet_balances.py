"""Owner, miner, and validator wallet balances. No network."""

from __future__ import annotations

import wallet_balances as wb
from labels import DEFAULT_HOUSE_KEYS


MINER = "5F9i7LjCW6C8ExBy3mH9jWDWwAwPwCg5UdzY2WzzTHS8LQjH"
VALIDATOR_CK = "5ValidatorColdkeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
HOTKEY = "5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz"


def _raw(**overrides):
    base = {
        "balance_free_tao": 1.5,
        "balance_total_tao": 10.0,
        "balance_total_24hr_ago_tao": 8.0,
        "block_number": 100,
        "alpha_balances": [
            {"netuid": 21, "alpha": 100.0, "alpha_as_tao": 4.0},
            {"netuid": 21, "alpha": 50.0, "alpha_as_tao": 2.0},
            {"netuid": 1, "alpha": 999.0, "alpha_as_tao": 9.0},
        ],
    }
    base.update(overrides)
    return base


def test_summarise_keeps_sn21_alpha_and_prices_the_whole_wallet():
    out = wb.summarise_balance(_raw(), tao_usd=200.0)
    assert out["sn21_alpha"] == 150.0
    assert out["sn21_tao"] == 6.0
    assert out["free_tao"] == 1.5
    assert out["total_tao"] == 10.0
    assert out["usd"] == 2000.0
    assert out["change_24h_pct"] == 25.0
    assert out["sn21_positions"] == 2


def test_summarise_failed_fetch_is_empty():
    out = wb.summarise_balance(None, tao_usd=200.0)
    assert out["sn21_alpha"] is None
    assert out["total_tao"] is None
    assert out["usd"] is None


def test_targets_are_owner_miners_and_validator():
    targets = wb.wallet_targets(VALIDATOR_CK)
    assert [t["role"] for t in targets] == ["owner", "miner", "miner", "miner", "validator"]
    assert targets[0]["coldkey"] == wb.OWNER_SHARE_COLDKEY
    miner_keys = [ss58 for kind, ss58, _note in DEFAULT_HOUSE_KEYS if kind == "coldkey"]
    assert [t["coldkey"] for t in targets if t["role"] == "miner"] == miner_keys
    assert targets[-1]["coldkey"] == VALIDATOR_CK
    assert targets[-1]["hotkey"] == wb.OUR_VALIDATOR_HOTKEY


def test_validator_coldkey_prefers_latest_neurons_row():
    rows = [
        {"hotkey": HOTKEY, "coldkey": "5Old"},
        {"hotkey": "5Other", "coldkey": "5Nope"},
        {"hotkey": HOTKEY, "coldkey": "5New"},
    ]
    assert wb.validator_coldkey_from_records(rows, [{"hotkey": HOTKEY, "coldkey": "5Scan"}]) == "5New"
    assert wb.validator_coldkey_from_records([], [{"hotkey": HOTKEY, "coldkey": "5Scan"}]) == "5Scan"
    assert wb.validator_coldkey_from_records([], []) is None


def test_build_sums_roles_and_counts_a_shared_coldkey_once(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "WALLET_BALANCES_STORE", tmp_path / "wallet_balances.json")
    monkeypatch.setattr(wb, "_api_key", lambda: "test-key")
    monkeypatch.setattr(wb, "_tao_usd", lambda prior: 100.0)

    def fetch(address):
        if address == wb.OWNER_SHARE_COLDKEY:
            return _raw(balance_total_tao=10.0, balance_free_tao=1.0)
        if address == MINER:
            return _raw(balance_total_tao=3.0, balance_free_tao=0.5,
                        alpha_balances=[{"netuid": 21, "alpha": 20.0, "alpha_as_tao": 1.0}])
        return _raw(balance_total_tao=1.0, balance_free_tao=1.0, alpha_balances=[])

    # Validator coldkey is the owner coldkey — one wallet, two roles.
    snap = wb.build_wallet_balances(
        fetch_balance=fetch,
        validator_coldkey=wb.OWNER_SHARE_COLDKEY,
        lookup_coldkey=False,
    )
    assert snap["roles"]["owner"]["total_tao"] == 10.0
    assert snap["roles"]["owner"]["sn21_alpha"] == 150.0
    assert snap["roles"]["miner"]["n"] == 3
    assert snap["roles"]["validator"]["total_tao"] == 10.0
    # Owner and validator are the same coldkey; miners are three more.
    assert snap["total"]["n"] == 4
    assert snap["total"]["total_tao"] == 10.0 + 3.0 + 1.0 + 1.0
    assert snap["total"]["usd"] == snap["total"]["total_tao"] * 100


def test_failed_fetch_keeps_the_previous_balance(tmp_path, monkeypatch):
    store = tmp_path / "wallet_balances.json"
    monkeypatch.setattr(wb, "WALLET_BALANCES_STORE", store)
    monkeypatch.setattr(wb, "_api_key", lambda: "test-key")
    monkeypatch.setattr(wb, "_tao_usd", lambda prior: 100.0)

    def fetch_ok(address):
        return _raw(balance_total_tao=4.0)

    first = wb.build_wallet_balances(
        fetch_balance=fetch_ok,
        validator_coldkey=VALIDATOR_CK,
        lookup_coldkey=False,
    )
    assert first["roles"]["owner"]["total_tao"] == 4.0

    def fetch_fail(address):
        return None

    second = wb.build_wallet_balances(
        fetch_balance=fetch_fail,
        validator_coldkey=VALIDATOR_CK,
        lookup_coldkey=False,
    )
    owner = next(w for w in second["wallets"] if w["role"] == "owner")
    assert owner["total_tao"] == 4.0
    assert owner["stale"] is True
    assert owner["usd"] == 400.0
