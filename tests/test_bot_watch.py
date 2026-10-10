"""Bot watch: confidence, sell triggers, and coldkey handover. No network."""

from __future__ import annotations

from datetime import datetime, timezone

import bot_watch as bw

OUR = "5OUR"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def ev(ts, block, action, tao, ck, hk="Taostats"):
    return {"ts": ts, "block": block, "action": action, "tao": tao, "ck": ck, "hk": hk}


def _day(day, hour, minute=0):
    return f"2026-10-{day:02d}T{hour:02d}:{minute:02d}:00Z"


def test_sells_on_a_timer_after_its_own_buy():
    bot = "5BOTTIMER"
    events = [
        ev(_day(10, 0, 0), 1000, "stake", 25, OUR),
        ev(_day(10, 0, 1), 1006, "stake", 20, bot),
        ev(_day(10, 0, 6), 1031, "unstake", 20, bot),
    ]
    doc = bw.analyse(events, [OUR], now=NOW, seed_coldkeys=[bot])
    row = doc["wallets"][bot]
    assert row["sell_trigger"] == "timer_after_own_buy"
    assert row["follow_hits"] == 1
    assert row["status"] == "active"
    assert "timer" in row["behaviour"]
    move = doc["our_moves"][0]
    assert move["action"] == "stake"
    assert move["reply_buy_tao"] == 20
    assert move["reply_sell_tao"] == 0


def test_sells_when_we_sell():
    bot = "5BOTSELL"
    events = [
        ev(_day(10, 1, 0), 2000, "stake", 20, bot),
        ev(_day(10, 2, 0), 2500, "unstake", 30, OUR),
        ev(_day(10, 2, 1), 2504, "unstake", 20, bot),
    ]
    doc = bw.analyse(events, [OUR], now=NOW, seed_coldkeys=[bot])
    row = doc["wallets"][bot]
    assert row["sell_trigger"] == "after_our_sell"
    assert row["sell_after_our_sell_hits"] == 1
    sellers = doc["expectation"]["wallets_that_sell_when_we_sell"]
    assert sellers[0]["coldkey"] == bot
    assert sellers[0]["median_lag_blocks"] == 4


def test_sells_into_our_buy_and_same_block_fade():
    fader = "5FADE"
    into = "5INTO"
    events = [
        ev(_day(10, 3, 0), 3000, "stake", 15, fader, hk="tao.bot"),
        ev(_day(10, 3, 0), 3000, "unstake", 15, fader, hk="tao.bot"),
        ev(_day(10, 4, 0), 3400, "stake", 20, into),
        ev(_day(10, 5, 0), 4000, "stake", 25, OUR),
        ev(_day(10, 5, 1), 4004, "unstake", 20, into),
    ]
    # Give the fader enough same-block round trips to be a suspect on its own.
    for i in range(3):
        block = 3100 + i * 10
        events.append(ev(_day(10, 3, 10 + i), block, "stake", 12.4, fader, hk="tao.bot"))
        events.append(ev(_day(10, 3, 10 + i), block, "unstake", 12.4, fader, hk="tao.bot"))
    doc = bw.analyse(events, [OUR], now=NOW, seed_coldkeys=[into])
    assert doc["wallets"][fader]["sell_trigger"] == "same_block_own_buy"
    assert doc["wallets"][fader]["family"] == "same_block_fade"
    assert doc["wallets"][into]["sell_trigger"] == "after_our_buy"


def test_quiet_seed_is_degraded():
    bot = "5QUIET"
    prior = {
        bot: {
            "confidence": "high",
            "confidence_score": 80,
            "last_seen": "2026-10-02T00:00:00Z",
            "family": "round_clip_fast",
            "hotkey": "Taostats",
            "sizes": [20],
        }
    }
    doc = bw.analyse([], [OUR], now=NOW, seed_coldkeys=[bot], prior_wallets=prior)
    row = doc["wallets"][bot]
    assert row["confidence"] == "low"
    assert row["confidence_delta"] == "degraded"
    assert row["status"] == "quiet"


def test_repeated_flat_clips_upgrade_confidence():
    bot = "5GROW"
    events = []
    for i, day in enumerate((8, 9, 10)):
        base = 5000 + i * 100
        events.append(ev(_day(day, 1), base, "stake", 25, OUR))
        events.append(ev(_day(day, 1, 1), base + 4, "stake", 20, bot))
        events.append(ev(_day(day, 1, 6), base + 29, "unstake", 20, bot))
    prior = {bot: {"confidence": "low", "confidence_score": 20}}
    doc = bw.analyse(events, [OUR], now=NOW, seed_coldkeys=[bot], prior_wallets=prior)
    row = doc["wallets"][bot]
    assert row["confidence"] == "high"
    assert row["confidence_delta"] == "upgraded"
    assert row["sell_trigger"] == "timer_after_own_buy"
    assert row["follow_hits"] == 3
    assert doc["expectation"]["median_reply_buy_tao"] == 20


def test_quiet_key_replaced_by_same_signature():
    old, new = "5OLDKEY", "5NEWKEY"
    events = []
    for i in range(4):
        block = 1000 + i * 20
        events.append(ev(_day(1, 10, i), block, "stake", 20, old))
        events.append(ev(_day(1, 10, i), block + 5, "unstake", 20, old))
    for i in range(4):
        block = 8000 + i * 20
        events.append(ev(_day(9, 10, i), block, "stake", 20, new))
        events.append(ev(_day(9, 10, i), block + 5, "unstake", 20, new))
    doc = bw.analyse(events, [OUR], now=NOW)
    assert doc["replacements"]
    pair = doc["replacements"][0]
    assert pair["retired"] == old
    assert pair["successor"] == new
    assert doc["wallets"][old]["status"] == "recycled_out"
    assert doc["wallets"][new]["replaced"] == old
    assert doc["wallets"][new]["status"] == "active"


def test_two_quiet_wallets_are_not_a_handover():
    a, b = "5QUIETA", "5QUIETB"
    events = []
    for ck, day in ((a, 1), (b, 2)):
        for i in range(4):
            block = day * 1000 + i * 20
            events.append(ev(_day(day, 10, i), block, "stake", 40, ck))
    doc = bw.analyse(events, [OUR], now=NOW)
    assert doc["replacements"] == []


def test_run_persists_a_daily_history_row(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "BOT_WATCH_STORE", tmp_path / "bot_watch.json")
    monkeypatch.setattr(bw, "BOT_WATCH_TAPE", tmp_path / "bot_watch_trades.json")
    bot = "5SAVED"
    events = [
        ev(_day(10, 0), 1000, "stake", 25, OUR),
        ev(_day(10, 0, 1), 1004, "stake", 20, bot),
        ev(_day(10, 0, 8), 1040, "unstake", 20, bot),
    ]
    doc = bw.run_bot_watch(events=events, seed_coldkeys=[bot], ours=[OUR], now=NOW)
    assert doc["history"][0]["date"] == "2026-10-10"
    assert (tmp_path / "bot_watch.json").exists()
    again = bw.run_bot_watch(events=events, seed_coldkeys=[bot], ours=[OUR], now=NOW)
    assert len(again["history"]) == 1
    assert again["wallets"][bot]["confidence_delta"] == "unchanged"
