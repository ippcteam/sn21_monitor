"""Taostats /v1 adapters. No network."""

from __future__ import annotations

import pytest

import taostats_v1 as v1

SS58 = "5HjCYVfrWSkzTfJM5rkWBW3qTTJqXEFUzZrKty5hodpgfjyW"


def test_transfer_params_sort_without_legacy_order():
    params = v1.transfer_params(SS58, limit=50)
    assert params["order_by"] == "timestamp"
    assert params["order_dir"] == "desc"
    assert params["address"] == SS58
    assert params["network"] == "finney"
    assert params["limit"] == 50
    assert "order" not in params


def test_leaderboard_params_force_subnet_rank_and_drop_order():
    params = v1.leaderboard_params(netuid=21, limit=200, order="balance_desc")
    assert params["order_by"] == "subnet_rank"
    assert params["order_dir"] == "asc"
    assert params["netuid"] == 21
    assert params["limit"] == 200
    assert "order" not in params


def test_account_path_keeps_a_plain_ss58():
    assert v1.account_path(SS58) == f"/v1/accounts/{SS58}"


def test_ss58_reads_string_and_legacy_object():
    assert v1.ss58(f"  {SS58}  ") == SS58
    assert v1.ss58({"ss58": SS58, "hex": "0x00"}) == SS58
    assert v1.ss58({"hex": "0x00"}) is None
    assert v1.ss58(None) is None
    assert v1.ss58("  ") is None


def test_legacy_pool_maps_reserve_and_aggregate_volumes():
    pool = {
        "tao_in_pool": "1000000000",
        "price": "0.01",
        "liquidity": "2",
        "market_cap": "3",
        "total_alpha": "4",
        "block_number": 10,
        "timestamp": "2026-10-12T00:00:00.000Z",
    }
    aggregate = {
        "alpha_volume_24_hr": "9",
        "tao_buy_volume_24_hr": "8",
        "buys_24_hr": 3,
        "price_change_1_day": "-1.5",
        "sentiment_index": "49.2",
        "sentiment": "Neutral",
    }
    out = v1.legacy_pool(pool, aggregate)
    assert out["total_tao"] == "1000000000"
    assert out["price"] == "0.01"
    assert out["block_number"] == 10
    assert out["alpha_volume_24_hr"] == "9"
    assert out["tao_buy_volume_24_hr"] == "8"
    assert out["buys_24_hr"] == 3
    assert out["price_change_1_day"] == "-1.5"
    assert out["fear_and_greed_index"] == "49.2"
    assert out["fear_and_greed_sentiment"] == "Neutral"
    assert out["rank"] is None


def test_legacy_pool_raises_when_reserve_is_missing():
    with pytest.raises(ValueError, match="tao_in_pool"):
        v1.legacy_pool({"price": "0.01"}, {"sentiment_index": "1"})
    with pytest.raises(ValueError, match="tao_in_pool"):
        v1.legacy_pool(None, {})


def test_legacy_subnet_maps_hyperparams_and_clears_net_flow():
    metrics = {
        "incentive_burn": "0.45",
        "validators": 64,
        "active_validators": 20,
        "active_miners": 200,
        "active_keys": 220,
        "neuron_registration_cost": "1000",
        "neuron_registrations_this_interval": 1,
        "recycled_lifetime": "50",
        "tao_from_neuron_registration_24_hours": "7",
        "block_number": 11,
        "timestamp": "2026-10-12T00:00:00.000Z",
    }
    hyper = {
        "max_allowed_uids": 256,
        "tempo": 360,
        "min_burn": "1",
        "max_burn": "2",
        "burn_half_life": 3,
        "burn_increase_mult": "1.1",
        "registration_allowed": True,
    }
    out = v1.legacy_subnet(metrics, hyper)
    assert out["incentive_burn"] == "0.45"
    assert out["max_neurons"] == 256
    assert out["tempo"] == 360
    assert out["registration_allowed"] is True
    assert out["min_burn"] == "1"
    assert out["recycled_24_hours"] == "7"
    assert out["recycled_lifetime"] == "50"
    assert out["active_miners"] == 200
    assert out["net_flow_1_day"] is None
    assert out["net_flow_7_days"] is None
    assert out["net_flow_30_days"] is None


def test_legacy_subnet_raises_when_burn_is_missing():
    with pytest.raises(ValueError, match="incentive_burn"):
        v1.legacy_subnet({"validators": 1}, {"max_allowed_uids": 256})


def test_legacy_metagraph_row_maps_immunity_and_axon():
    out = v1.legacy_metagraph_row({
        "uid": 7,
        "is_immune": True,
        "axon": "1.2.3.4:9000",
        "emission": "20",
    })
    assert out["is_immunity_period"] is True
    assert out["axon"] == {"ip": "1.2.3.4", "port": 9000, "block": None}
    assert out["daily_reward"] == 400


def test_legacy_metagraph_row_leaves_a_missing_axon_absent():
    out = v1.legacy_metagraph_row({"uid": 1, "is_immunity_period": False})
    assert "axon" not in out
    assert out["is_immunity_period"] is False
    assert "daily_reward" not in out


def test_legacy_metagraph_row_keeps_a_supplied_daily_reward():
    out = v1.legacy_metagraph_row({"uid": 1, "emission": "20", "daily_reward": "7"})
    assert out["daily_reward"] == "7"


def test_legacy_account_ss58_reads_a_string():
    assert v1.legacy_account_ss58({"address": SS58}, "fallback") == SS58
    assert v1.legacy_account_ss58({"address": {"ss58": SS58}}, "fallback") == SS58
    assert v1.legacy_account_ss58({}, "fallback") == "fallback"


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, payload):
        self.headers: dict = {}
        self.calls: list[dict] = []
        self._payload = payload

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}})
        return _Response(self._payload)


def _install_session(monkeypatch, payload):
    import taostats_sync

    holder: dict = {}

    def factory():
        session = _Session(payload)
        holder["session"] = session
        return session

    monkeypatch.setenv("TAOSTATS_API_KEY", "test-key")
    monkeypatch.setattr(taostats_sync.requests, "Session", factory)
    return taostats_sync, holder


def test_sync_paths_match_the_adapter():
    import taostats_sync

    assert taostats_sync.TRANSFER_PATH == v1.PATH_TRANSFERS
    assert taostats_sync.PRICE_LATEST_PATH == v1.PATH_PRICE


def test_price_fetch_uses_v1_and_parses_a_decimal_string(monkeypatch):
    sync, holder = _install_session(monkeypatch, {"data": [{"price": "345.12"}]})
    assert sync.fetch_tao_usd() == 345.12
    call = holder["session"].calls[0]
    assert call["url"].endswith("/v1/price")
    assert call["params"] == {"asset": "tao"}
    assert "order" not in call["params"]


def test_balance_fetch_puts_the_address_in_the_path(monkeypatch):
    payload = {
        "data": [{
            "address": SS58,
            "balance_total": "1000000000",
            "balance_free": "400000000",
            "balance_staked": "600000000",
            "balance_staked_alpha_as_tao": "0",
            "balance_staked_root": "0",
            "balance_total_24hr_ago": "900000000",
            "block_number": 12,
            "timestamp": "2026-10-12T00:00:00.000Z",
            "rank": 4,
            "alpha_balances": [{
                "netuid": 21,
                "hotkey": {"ss58": SS58},
                "balance": "2000000000",
                "balance_as_tao": "1000000000",
            }],
        }]
    }
    sync, holder = _install_session(monkeypatch, payload)
    out = sync.fetch_owner_balance(SS58, network="finney")
    call = holder["session"].calls[0]
    assert call["url"].endswith(f"/v1/accounts/{SS58}")
    assert call["params"] == {}
    assert out["address"] == SS58
    assert out["network"] == "finney"
    assert out["balance_total_tao"] == 1.0
    assert out["alpha_balances"][0]["hotkey"] == SS58
    assert out["alpha_balances"][0]["alpha"] == 2.0


def test_transfer_fetch_sorts_without_legacy_order(monkeypatch):
    payload = {
        "data": [{
            "id": "t1",
            "timestamp": "2026-10-12T00:00:00.000Z",
            "block_number": 9,
            "from": SS58,
            "to": "5to",
            "amount": "1",
        }],
        "pagination": {"next_page": None, "total_pages": 1},
    }
    sync, holder = _install_session(monkeypatch, payload)
    monkeypatch.delenv("TAOSTATS_TRANSFER_MERGE_DIRECTIONS", raising=False)
    rows, _pag = sync.fetch_all_transfers(address=SS58)
    assert [row["id"] for row in rows] == ["t1"]
    params = holder["session"].calls[0]["params"]
    assert params["order_by"] == "timestamp"
    assert params["order_dir"] == "desc"
    assert params["address"] == SS58
    assert "order" not in params
    assert holder["session"].calls[0]["url"].endswith("/v1/transfers")


def test_transfer_direction_merge_keeps_the_new_sort(monkeypatch):
    payload = {
        "data": [],
        "pagination": {"next_page": None, "total_pages": 0},
    }
    sync, holder = _install_session(monkeypatch, payload)
    monkeypatch.setenv("TAOSTATS_TRANSFER_MERGE_DIRECTIONS", "1")
    sync.fetch_all_transfers(address=SS58)
    calls = holder["session"].calls
    assert len(calls) == 3
    assert calls[1]["params"]["from"] == SS58
    assert calls[2]["params"]["to"] == SS58
    for call in calls:
        assert call["params"]["order_by"] == "timestamp"
        assert call["params"]["order_dir"] == "desc"
        assert "order" not in call["params"]


class _Rows:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_subnet_daily_join_keeps_total_tao_and_null_net_flow(monkeypatch):
    import subnet_sync

    monkeypatch.setattr(subnet_sync._time, "sleep", lambda *_a, **_k: None)
    payloads = [
        {"data": [{"tao_in_pool": "5000000000", "price": "0.02", "block_number": 1, "timestamp": "t"}]},
        {"data": [{"alpha_volume_24_hr": "9", "tao_buy_volume_24_hr": "8", "sentiment_index": "40", "sentiment": "Fear"}]},
        {"data": [{"incentive_burn": "0.45", "active_validators": 10, "active_miners": 20, "tao_from_neuron_registration_24_hours": "7", "recycled_lifetime": "50"}]},
        {"data": [{"max_allowed_uids": 256, "tempo": 360, "registration_allowed": True, "min_burn": "1", "max_burn": "2"}]},
        {"data": [{"subnet_total_holders": 1968}]},
    ]

    class Session:
        def get(self, url, params=None, timeout=None):
            assert "order" not in (params or {})
            return _Rows(payloads.pop(0))

    session = Session()
    pool = subnet_sync.fetch_pool_latest(session)
    subnet = subnet_sync.fetch_subnet_latest(session)
    holders = subnet_sync.fetch_total_holders(session)
    assert pool["total_tao"] == 5.0
    assert pool["fear_and_greed_index"] == 40.0
    assert subnet["incentive_burn"] == 0.45
    assert subnet["max_neurons"] == 256
    assert subnet["tempo"] == 360
    assert subnet["net_flow_1d_tao"] is None
    assert subnet["net_flow_7d_tao"] is None
    assert subnet["net_flow_30d_tao"] is None
    assert holders == 1968
    assert payloads == []


def test_scout_pool_join_exposes_total_tao(monkeypatch):
    import subnet_scan

    monkeypatch.setattr(subnet_scan.time, "sleep", lambda *_a, **_k: None)
    payloads = [
        {"data": [{"tao_in_pool": "5000000000", "price": "0.02"}]},
        {"data": [{"alpha_volume_24_hr": "9"}]},
        {"data": [{"incentive_burn": "0.45", "active_validators": 1, "active_miners": 2, "neuron_registration_cost": "1000"}]},
        {"data": [{"max_allowed_uids": 256, "registration_allowed": True}]},
    ]

    class Session:
        def get(self, url, params=None, timeout=None, headers=None):
            assert "order" not in (params or {})
            return _Rows(payloads.pop(0))

    pool = subnet_scan._fetch_pool(Session(), 8)
    sub = subnet_scan._fetch_subnet(Session(), 8)
    assert pool["total_tao"] == "5000000000"
    assert pool["alpha_volume_24_hr"] == "9"
    assert sub["incentive_burn"] == "0.45"
    assert sub["max_neurons"] == 256
    assert sub["net_flow_30_days"] is None


def test_holder_and_name_queries_omit_order():
    import holders_sync
    import weights_scan

    captured = []

    class Session:
        def get(self, url, params=None, timeout=None):
            captured.append(params or {})
            return _Rows({"data": [{"hotkey_name": "Named"}], "pagination": {}})

    holders_sync._fetch_page(Session(), 3)
    assert weights_scan._fetch_hotkey_name(Session(), "5hotkey") == "Named"
    assert captured[0]["page"] == 3
    assert captured[0]["limit"] == 200
    assert captured[1]["limit"] == 1
    for params in captured:
        assert "order" not in params
        assert params["order_by"] == "subnet_rank"
        assert params["order_dir"] == "asc"


def test_neurons_read_adapted_immunity_and_axon():
    import neurons_sync

    raw = v1.legacy_metagraph_row({
        "uid": 7,
        "is_immune": True,
        "axon": "1.2.3.4:9000",
        "hotkey": SS58,
        "coldkey": SS58,
    })
    row = neurons_sync._normalise_row(raw, None, None, None)
    assert row["is_immunity_period"] is True
    assert row["axon_ip"] == "1.2.3.4"
    assert row["axon_port"] == 9000
    assert "daily_reward" not in raw


def test_bot_watch_stays_on_v1_stake_events():
    import bot_watch

    assert bot_watch.STAKE_EVENTS_PATH == "/v1/subnets/stake-events"
