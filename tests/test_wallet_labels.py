"""House vs bot labels share one file and must not collapse into each other."""

from __future__ import annotations

import labels


def test_default_bots_are_not_house(tmp_path, monkeypatch):
    monkeypatch.setattr(labels, "WALLET_LABELS_STORE", tmp_path / "wallet_labels.json")
    bots = labels.bot_set()
    house = labels.house_set()

    assert len(bots) == len(labels.DEFAULT_BOT_KEYS)
    assert bots.isdisjoint(house)
    for _kind, ss58, _note in labels.DEFAULT_BOT_KEYS:
        assert ss58 in bots
        assert labels.is_house(ss58) is False
    for _kind, ss58, _note in labels.DEFAULT_HOUSE_KEYS:
        assert ss58 in house
        assert labels.is_house(coldkey=ss58) or labels.is_house(hotkey=ss58)
