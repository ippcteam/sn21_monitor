"""Taostats `/v1` paths and adapters that keep the old response field names.

No HTTP. Callers keep their own retry loops and pass the JSON rows in.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

PATH_TRANSFERS = "/v1/transfers"
PATH_PRICE = "/v1/price"
PATH_ALPHA_LEADERBOARD = "/v1/alpha/leaderboard"
PATH_ALPHA_HISTORY = "/v1/alpha/history"
PATH_METAGRAPH = "/v1/subnets/metagraph"
PATH_POOLS = "/v1/subnets/pools"
PATH_POOLS_AGGREGATE = "/v1/subnets/pools/aggregate"
PATH_SUBNET_METRICS = "/v1/subnets/metrics"
PATH_SUBNET_HYPERPARAMETERS = "/v1/subnets/hyperparameters"
PATH_VALIDATORS_ACTIVE = "/v1/validators/active"

# Names the old pool payload carried and the aggregate route still uses.
_AGGREGATE_KEYS = (
    "alpha_buy_volume_24_hr",
    "alpha_sell_volume_24_hr",
    "alpha_volume_24_hr",
    "alpha_volume_24_hr_change_1_day",
    "tao_buy_volume_24_hr",
    "tao_sell_volume_24_hr",
    "tao_volume_24_hr",
    "tao_volume_24_hr_change_1_day",
    "buys_24_hr",
    "sells_24_hr",
    "buyers_24_hr",
    "sellers_24_hr",
    "price_change_1_hour",
    "price_change_1_day",
    "price_change_1_week",
    "price_change_1_month",
    "highest_price_24_hr",
    "lowest_price_24_hr",
    "last_price",
    "market_cap_change_1_day",
    "seven_day_prices",
)

_HYPER_KEYS = (
    "tempo",
    "min_burn",
    "max_burn",
    "burn_half_life",
    "burn_increase_mult",
    "registration_allowed",
)


def account_path(address: str) -> str:
    """One path segment. A plain SS58 address is already URL-safe."""
    return "/v1/accounts/" + quote(address, safe="")


def ss58(value: Any) -> str | None:
    """Read an SS58 address from a plain string or an old `{ss58, hex}` object."""
    if isinstance(value, dict):
        value = value.get("ss58")
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def transfer_params(
    address: str,
    network: str = "finney",
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "network": network,
        "address": address,
        "limit": limit,
        "order_by": "timestamp",
        "order_dir": "desc",
    }


def leaderboard_params(**filters: Any) -> dict[str, Any]:
    """Largest alpha balance first. Rank 1 is that balance, so direction is asc."""
    params = {key: value for key, value in filters.items() if key != "order"}
    params["order_by"] = "subnet_rank"
    params["order_dir"] = "asc"
    return params


def _present(row: dict[str, Any] | None, key: str) -> bool:
    if not row:
        return False
    value = row.get(key)
    return value is not None and value != ""


def legacy_pool(
    pool_row: dict[str, Any] | None,
    aggregate_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Old `/api/dtao/pool/latest/v1` shape from the pools plus aggregate routes."""
    if not _present(pool_row, "tao_in_pool"):
        raise ValueError("tao_in_pool missing")
    pool_row = pool_row or {}
    aggregate_row = aggregate_row or {}
    out: dict[str, Any] = {
        "block_number": pool_row.get("block_number"),
        "timestamp": pool_row.get("timestamp"),
        "price": pool_row.get("price"),
        "liquidity": pool_row.get("liquidity"),
        "market_cap": pool_row.get("market_cap"),
        "total_alpha": pool_row.get("total_alpha"),
        "total_tao": pool_row.get("tao_in_pool"),
        "rank": None,
        "fear_and_greed_index": aggregate_row.get("sentiment_index"),
        "fear_and_greed_sentiment": aggregate_row.get("sentiment"),
    }
    for key in _AGGREGATE_KEYS:
        out[key] = aggregate_row.get(key)
    return out


def legacy_subnet(
    metrics_row: dict[str, Any] | None,
    hyper_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Old `/api/subnet/latest/v1` shape from metrics plus hyperparameters."""
    if not _present(metrics_row, "incentive_burn"):
        raise ValueError("incentive_burn missing")
    metrics_row = metrics_row or {}
    hyper_row = hyper_row or {}
    out = dict(metrics_row)
    out["recycled_24_hours"] = metrics_row.get("tao_from_neuron_registration_24_hours")
    out["max_neurons"] = hyper_row.get("max_allowed_uids")
    for key in _HYPER_KEYS:
        out[key] = hyper_row.get(key)
    out["net_flow_1_day"] = None
    out["net_flow_7_days"] = None
    out["net_flow_30_days"] = None
    return out


def legacy_metagraph_row(row: dict[str, Any]) -> dict[str, Any]:
    """Copy a metagraph row and restore the fields our parsers still read.

    ``daily_reward`` is ``emission * 20`` on SN21. Checked live on 2026-10-12
    for five UIDs from one metagraph snapshot, including a non-zero miner.
    """
    out = dict(row)
    if "is_immunity_period" not in out and "is_immune" in out:
        out["is_immunity_period"] = out.get("is_immune")
    axon = out.get("axon") if "axon" in out else None
    if isinstance(axon, str):
        ip, sep, port = axon.rpartition(":")
        if not sep:
            ip, port = axon, ""
        out["axon"] = {
            "ip": ip or None,
            "port": int(port) if port.isdigit() else (port or None),
            "block": None,
        }
    if out.get("daily_reward") in (None, ""):
        reward = _daily_reward(out.get("emission"))
        if reward is None:
            out.pop("daily_reward", None)
        else:
            out["daily_reward"] = reward
    return out


def _daily_reward(emission: Any) -> int | None:
    """RAO per day. Blank when emission is missing or not a whole number of RAO."""
    if emission in (None, ""):
        return None
    try:
        whole = int(emission)
    except (TypeError, ValueError):
        try:
            parsed = float(emission)
        except (TypeError, ValueError):
            return None
        if not parsed.is_integer():
            return None
        whole = int(parsed)
    return whole * 20


def legacy_account_ss58(row: dict[str, Any] | None, fallback: str) -> str:
    found = ss58((row or {}).get("address"))
    return found if found else fallback
