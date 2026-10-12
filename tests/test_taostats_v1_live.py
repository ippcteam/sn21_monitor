"""Live Taostats /v1 contract, plus a side-by-side check while /api/ still answers.

Skipped when TAOSTATS_API_KEY is unset. Does not write data/ and does not print the key.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from bot_watch import STAKE_EVENTS_PATH
from stake_watch import OUR_VALIDATOR_HOTKEY, OWNER_SHARE_COLDKEY

pytestmark = pytest.mark.live

NETUID = 21
BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")


def _key() -> str:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip()


@pytest.fixture(scope="module", autouse=True)
def _require_key():
    if not _key():
        pytest.skip("TAOSTATS_API_KEY not set")


def _get(path: str, params: dict | None = None) -> requests.Response:
    """GET with the same 429 backoff the sync jobs use. The suite bursts otherwise."""
    response = None
    for attempt in range(8):
        response = requests.get(
            f"{BASE}{path}",
            params=params or {},
            headers={"Authorization": _key(), "Accept": "application/json"},
            timeout=90,
        )
        if response.status_code != 429:
            time.sleep(0.4)
            return response
        time.sleep(min(2 ** attempt + 0.5, 20))
    assert response is not None
    return response


def _data(path: str, params: dict | None = None) -> list:
    response = _get(path, params)
    assert response.status_code == 200, response.status_code
    body = response.json()
    data = body.get("data")
    assert data, path
    return data if isinstance(data, list) else [data]


def _pages(path: str, params: dict, limit: int = 200, skip_missing: bool = False) -> list:
    rows: list = []
    page = 1
    while page:
        response = _get(path, {**params, "limit": limit, "page": page})
        if response.status_code == 404 and skip_missing:
            pytest.skip(f"{path} is gone")
        assert response.status_code == 200, response.status_code
        body = response.json()
        rows.extend(body.get("data") or [])
        nxt = (body.get("pagination") or {}).get("next_page")
        page = int(nxt) if nxt else 0
        if page > 10:
            break
    return rows


def _maybe_old(path: str, params: dict) -> requests.Response | None:
    response = _get(path, params)
    if response.status_code == 404:
        pytest.skip(f"{path} is gone")
    return response


def test_price_is_parseable():
    price = _data("/v1/price", {"asset": "tao"})[0]["price"]
    assert float(price) > 0


def test_owner_account_when_configured():
    owner = (os.environ.get("TAOSTATS_OWNER_ID") or "").strip()
    if not owner:
        pytest.skip("TAOSTATS_OWNER_ID not set")
    row = _data(f"/v1/accounts/{owner}")[0]
    assert row["address"] == owner
    int(row["balance_total"])


def test_pool_and_aggregate_fields():
    pool = _data("/v1/subnets/pools", {"netuid": NETUID})[0]
    aggregate = _data("/v1/subnets/pools/aggregate", {"netuid": NETUID})[0]
    assert pool.get("tao_in_pool") not in (None, "")
    assert pool.get("price") not in (None, "")
    assert "tao_volume_24_hr" in aggregate


def test_metrics_and_hyperparameters():
    metrics = _data("/v1/subnets/metrics", {"netuid": NETUID})[0]
    hyper = _data("/v1/subnets/hyperparameters", {"netuid": NETUID})[0]
    assert metrics.get("incentive_burn") not in (None, "")
    assert hyper.get("max_allowed_uids")
    assert hyper.get("tempo")


def test_metagraph_covers_256_uids():
    rows = _pages("/v1/subnets/metagraph", {"netuid": NETUID})
    uids = {row["uid"] for row in rows}
    assert len(rows) >= 200
    assert len(uids) == 256
    sample = rows[0]
    assert isinstance(sample["hotkey"], str)
    assert isinstance(sample["coldkey"], str)
    assert isinstance(sample["is_immune"], bool)


def test_leaderboard_reports_holder_count():
    row = _data("/v1/alpha/leaderboard", {"netuid": NETUID, "limit": 1, "order_by": "subnet_rank", "order_dir": "asc"})[0]
    assert isinstance(row["subnet_total_holders"], int)
    stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    print(f"leaderboard age_seconds={age:.0f} holders={row['subnet_total_holders']}")


def test_validators_active_rejects_limit():
    ok = _get("/v1/validators/active", {"netuid": NETUID})
    assert ok.status_code == 200, ok.status_code
    assert ok.json().get("data")
    rejected = _get("/v1/validators/active", {"netuid": NETUID, "limit": 1})
    assert rejected.status_code == 400, rejected.status_code


def test_alpha_history_when_position_is_configured():
    coldkey = (os.environ.get("OWNER_SHARE_COLDKEY") or OWNER_SHARE_COLDKEY or "").strip()
    hotkey = (os.environ.get("OUR_VALIDATOR_HOTKEY") or OUR_VALIDATOR_HOTKEY or "").strip()
    if not coldkey or not hotkey:
        pytest.skip("stake-watch coldkey or hotkey is unset")
    row = _data("/v1/alpha/history", {
        "coldkey": coldkey,
        "hotkey": hotkey,
        "netuid": NETUID,
        "limit": 5,
        "order_by": "timestamp",
        "order_dir": "desc",
    })[0]
    assert row.get("balance") not in (None, "")
    assert row.get("timestamp")


def test_bot_watch_path():
    assert STAKE_EVENTS_PATH == "/v1/subnets/stake-events"


def test_pool_reserve_matches_old_api():
    old = _maybe_old("/api/dtao/pool/latest/v1", {"netuid": NETUID})
    assert old is not None and old.status_code == 200, old.status_code if old else None
    new = _data("/v1/subnets/pools", {"netuid": NETUID})[0]
    previous = old.json()["data"][0]
    assert int(new["tao_in_pool"]) == int(previous["total_tao"])
    aggregate = _data("/v1/subnets/pools/aggregate", {"netuid": NETUID})[0]
    print(
        f"sentiment new={aggregate.get('sentiment_index')} old={previous.get('fear_and_greed_index')} "
        f"market_cap new={new.get('market_cap')} old={previous.get('market_cap')}"
    )


def test_subnet_burn_and_uid_cap_match_old_api():
    old = _maybe_old("/api/subnet/latest/v1", {"netuid": NETUID})
    assert old is not None and old.status_code == 200, old.status_code if old else None
    previous = old.json()["data"][0]
    metrics = _data("/v1/subnets/metrics", {"netuid": NETUID})[0]
    hyper = _data("/v1/subnets/hyperparameters", {"netuid": NETUID})[0]
    assert abs(float(metrics["incentive_burn"]) - float(previous["incentive_burn"])) < 1e-6
    assert int(hyper["max_allowed_uids"]) == int(previous["max_neurons"])
    print(
        f"old net_flow_1_day={previous.get('net_flow_1_day')} "
        f"net_flow_7_days={previous.get('net_flow_7_days')} "
        f"net_flow_30_days={previous.get('net_flow_30_days')} stored_as=null"
    )


def test_metagraph_uids_and_mining_match_old_api():
    # Unordered old pages overlap: 256 rows, fewer unique UIDs, and the rest never
    # appear. uid order returns each UID once and matches /v1.
    old_rows = _pages(
        "/api/metagraph/latest/v1",
        {"netuid": NETUID, "order": "uid_asc"},
        limit=100,
        skip_missing=True,
    )
    new_rows = _pages("/v1/subnets/metagraph", {"netuid": NETUID})
    old_by_uid = {row["uid"]: row for row in old_rows}
    new_by_uid = {row["uid"]: row for row in new_rows}
    if set(old_by_uid) != set(new_by_uid):
        print(
            f"counts old_rows={len(old_rows)} old_uids={len(old_by_uid)} "
            f"new_rows={len(new_rows)} new_uids={len(new_by_uid)}"
        )
        print("only_old", sorted(set(old_by_uid) - set(new_by_uid))[:30])
        print("only_new", sorted(set(new_by_uid) - set(old_by_uid))[:30])
    assert set(old_by_uid) == set(new_by_uid)
    shared = sorted(set(old_by_uid) & set(new_by_uid))[:5]
    reward_matches = []
    for uid in shared:
        old_row = old_by_uid[uid]
        new_row = new_by_uid[uid]
        same_block = old_row.get("block_number") == new_row.get("block_number")
        mining_same = str(old_row.get("daily_mining_alpha")) == str(new_row.get("daily_mining_alpha"))
        if same_block:
            assert mining_same
        emission = old_row.get("emission")
        reward = old_row.get("daily_reward")
        try:
            product = int(emission) * 20
            matched = int(reward) == product
        except (TypeError, ValueError):
            product = None
            matched = False
        reward_matches.append(matched)
        print(
            f"uid={uid} same_block={same_block} mining_same={mining_same} "
            f"old_block={old_row.get('block_number')} new_block={new_row.get('block_number')} "
            f"new_emission={new_row.get('emission')!r} "
            f"daily_reward={reward} emission_x20={product} match={matched}"
        )
    print(f"daily_reward_identity={'yes' if reward_matches and all(reward_matches) else 'no'}")


def test_holder_count_and_validator_set_are_reported():
    old_holders = _get("/api/dtao/stake_balance/latest/v1", {"netuid": NETUID, "limit": 1})
    new_row = _data("/v1/alpha/leaderboard", {"netuid": NETUID, "limit": 1})[0]
    if old_holders.status_code == 200:
        previous = (old_holders.json().get("data") or [{}])[0].get("subnet_total_holders")
        print(f"holders new={new_row.get('subnet_total_holders')} old={previous}")
    else:
        print(f"old holder route status={old_holders.status_code}")
    old_validators = _get("/api/dtao/validator/available/v1", {"netuid": NETUID, "limit": 200})
    new_validators = _data("/v1/validators/active", {"netuid": NETUID})
    new_keys = {row.get("address") for row in new_validators}
    if old_validators.status_code == 200:
        old_rows = old_validators.json().get("data") or []

        def _addr(row):
            address = row.get("address")
            if isinstance(address, dict):
                return address.get("ss58")
            return address

        old_keys = {_addr(row) for row in old_rows}
        print(
            f"validators only_old={sorted(old_keys - new_keys)} "
            f"only_new={sorted(new_keys - old_keys)}"
        )
