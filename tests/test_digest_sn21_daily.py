"""Daily digest: tape verdict, burn-setpoint flags, rotation vs real flow."""

from __future__ import annotations

from digest.composers.fallback import compose as fallback_compose
from digest.sources import sn21_daily as src


def test_is_real_net_move_drops_rotation():
    # Taostats-style: huge gross, modest net.
    assert src._is_real_net_move(11_500, 90_000, "taostats", "Taostats") is False
    # Directional unknown wallet.
    assert src._is_real_net_move(9_000, 10_000, None, "5GpQRRjU") is True
    # Known brand needs ≥ 8k net AND high ratio.
    assert src._is_real_net_move(5_000, 5_200, "arbos", "Arbos") is False
    assert src._is_real_net_move(16_500, 17_000, "tao.bot", "tao.bot") is True


def test_flow_group_key_prefers_brand():
    assert src._flow_group_key("taostats", "Taostats 2", "ckA") == "brand:taostats"
    assert src._flow_group_key("taostats", "Taostats", "ckB") == "brand:taostats"
    assert src._flow_group_key(None, "Solo Val", "ckC") == "name:solo val"


def test_tape_buy_won_despite_more_sells():
    subnet_log = [{
        "date": "2026-08-17",
        "pool": {
            "fear_and_greed_index": 49,
            "fear_and_greed_sentiment": "Neutral",
            "buys_24h": 40,
            "sells_24h": 66,
            "buyers_24h": 19,
            "sellers_24h": 19,
            "tao_buy_volume_24h": 16.25,
            "tao_sell_volume_24h": 14.54,
        },
    }]
    tape = src._tape_section(subnet_log, {})
    assert tape["available"] is True
    assert tape["verdict"] == "buy_won"
    assert tape["count_vs_volume"] == "more_sells_buy_won"
    assert tape["net_tao_24h"] == 1.71
    assert "buy volume won" in tape["verdict_plain"].lower()


def test_tape_thin():
    subnet_log = [{
        "date": "2026-08-13",
        "pool": {
            "tao_buy_volume_24h": 2.0,
            "tao_sell_volume_24h": 1.5,
            "buys_24h": 4,
            "sells_24h": 3,
        },
    }]
    tape = src._tape_section(subnet_log, {})
    assert tape["verdict"] == "thin"


def test_flags_silent_on_standing_burn_and_flat_entitlement():
    owner = {
        "entitled_7d_pct": 0.0,
        "burn_rate_pct": 45.12,
        "burn_vs_setpoint_pp": 0.02,
        "burn_7d_pp": 0.0,
        "miner_share_pct": 54.88,
    }
    tape = {
        "available": True,
        "net_tao_24h": 1.71,
        "sentiment_index": 49,
        "sentiment_label": "Neutral",
        "sentiment_7d_delta": 2,
        "tao_buy_volume_7d_pct": 5.0,
    }
    market = {"available": True, "verdict": "inline", "breadth": {}, "sn21": {}}
    flags = src._flags({}, {"available": False}, owner, market, tape)
    assert flags == []
    # Baseline census must not flag; add/drop after baseline must.
    assert src._flags(
        {}, {"available": False}, owner, market, tape,
        {"available": True, "is_baseline": True, "adds": ["Rizzo"]},
    ) == []
    fired = src._flags(
        {}, {"available": False}, owner, market, tape,
        {"available": True, "is_baseline": False, "adds": ["Rizzo"], "drops": ["OTF"]},
    )
    assert any("ADD: Rizzo" in f for f in fired)
    assert any("DROP: OTF" in f for f in fired)


def test_flags_fire_on_burn_move_and_sn21_specific():
    owner = {
        "entitled_7d_pct": 0.0,
        "burn_rate_pct": 60.0,
        "burn_vs_setpoint_pp": 14.9,
        "burn_7d_pp": 14.9,
        "miner_share_pct": 40.0,
    }
    market = {
        "available": True,
        "verdict": "sn21_specific",
        "breadth": {"median_move_24h_tao_pct": -0.24},
        "sn21": {"move_24h_percentile": 11},
    }
    flags = src._flags({}, {"available": False}, owner, market, {"available": False})
    assert any("Burn moved" in f for f in flags)
    assert any("SN21-SPECIFIC" in f for f in flags)
    assert not any("off full burn-to-owner" in f for f in flags)


def test_flags_tape_extremes():
    owner = {"entitled_7d_pct": 0.0, "burn_rate_pct": 45.12,
             "burn_vs_setpoint_pp": 0.02, "burn_7d_pp": 0.0}
    tape = {
        "available": True,
        "net_tao_24h": -8.4,
        "sentiment_index": 18,
        "sentiment_label": "Fear",
        "sentiment_7d_delta": -20,
        "tao_buy_volume_7d_pct": -74.6,
    }
    flags = src._flags({}, {"available": False}, owner, None, tape)
    assert any("Tape net -8.40" in f for f in flags)
    assert any("Sentiment extreme" in f for f in flags)
    assert any("Sentiment swung" in f for f in flags)
    assert any("Buy volume dry-up" in f for f in flags)


def test_owner_econ_setpoint_language():
    oe = src._owner_economics_section(
        {"our_entitled_alpha": 324.0},
        {},
        {"burn_rate_pct": 45.12},
        {},
        {"burn_rate_pct": {"d-7": 45.11, "7d_pct": 0.02},
         "our_entitled_alpha": {"7d_pct": 0.0, "30d_pct": 0.0},
         "owner_share_alpha": {}},
    )
    assert oe["burn_regime"] == "setpoint 45.1%"
    assert abs(oe["burn_vs_setpoint_pp"]) < 0.1
    assert oe["burn_7d_pp"] == 0.01


def test_fallback_includes_tape_not_burn_collapse():
    text = fallback_compose({
        "date": "2026-08-17",
        "owner_economics": {
            "entitled_alpha_today": 324,
            "entitled_7d_pct": 0.0,
            "entitled_30d_pct": 0.0,
            "owner_pool_alpha": 39891.89,
            "owner_pool_delta_24h": 429,
            "wallet_balance_tao": 132.23,
            "wallet_change_24h_pct": 1.29,
            "burn_rate_pct": 45.12,
            "burn_regime": "setpoint 45.1%",
        },
        "tape": {
            "available": True,
            "sentiment_index": 49,
            "sentiment_label": "Neutral",
            "buys_24h": 40,
            "sells_24h": 66,
            "buyers_24h": 19,
            "sellers_24h": 19,
            "tao_buy_volume_24h": 16.25,
            "tao_sell_volume_24h": 14.54,
            "net_tao_24h": 1.71,
            "verdict_plain": "More sellers, larger buys — buy volume won.",
        },
        "market": {"available": False},
        "price": {"alpha_price_tao": 0.003309},
        "flows": {"available": True, "holder_count": 2256, "holder_delta": -17,
                  "new_positions": 4, "exited_positions": 20,
                  "house_net_alpha_24h": 80, "net_movers": []},
        "flags": [],
    }, "SN21 Daily")
    assert "TAPE" in text
    assert "49" in text
    assert "16.25" in text
    assert "setpoint 45.1%" in text
    assert "collapsed" not in text.lower()
    assert "SUSTAINED" not in text


def test_fallback_root_baskets_adds_first():
    text = fallback_compose({
        "date": "2026-08-29",
        "root_baskets": {
            "available": True,
            "is_baseline": False,
            "n_curating": 2,
            "n_leftover": 4,
            "realizable_tao_21": 12.5,
            "n_significant": 2,
            "adds": ["Taostats"],
            "drops": ["Rizzo"],
            "significant": [
                {"name": "Taostats", "reasons": ["curated_add"]},
                {"name": "Rizzo", "reasons": ["curated_drop"]},
            ],
        },
        "flags": [],
    }, "SN21 Daily")
    assert "ROOT BASKETS" in text
    add_at = text.index("ADD: Taostats")
    drop_at = text.index("DROP: Rizzo")
    assert add_at < drop_at
