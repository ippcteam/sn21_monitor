"""
Chain access layer for the bittensor 11 SDK + spec-430 runtime.

The v430-v432 runtime train (finney, 2026-07-13..16) broke bittensor 9.x's
decoders (typed currency units, tuple-wrapped NetUid, Swap.AlphaSqrtPrice
removed), and bittensor 11.0.0 is a full SDK rewrite (one Rust core, namespace
reads — PR #2846): `bt.Subtensor(network)` only, no `log_verbose`, no
`all_subnets()`, no fetch-and-sync `bt.Metagraph`. This module is the single
place that knows the new API, exposing:

  - `bal(x)`          — float out of a v11 typed Balance / fixed-point / tuple
  - `get_subtensor()` — a v11 client (`st.subnets.metagraph(n)`, `st.weights.…`)
  - `fetch_metagraph(netuid, block=None)` — a LegacyMetagraph adapter with the
    9.x-shaped attributes our sync jobs were written against (plain lists, no
    numpy): uids/emission/dividends/incentive/stake(S)/hotkeys/coldkeys/
    validator_permit/block/tempo/pool/hparams/price/moving_price
  - `substrate()` + `unwrap`/`bits`/`qmap` — raw storage reads via
    async-substrate-interface for storage-shaped pulls (pool reserves,
    MinerBurned, …); raw decode is unaffected by SDK rewrites, which is why
    conviction_watch.py and lab/chain_pull.py's fallback survived the upgrade.

Semantics verified live @ block ~8,668,982 (spec 432): metagraph neuron
emission sums to 295.2 alpha/tempo (the 82% miner+validator slice, same as
9.x), incentive is ~1.0-normalized, price/moving_price are floats.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

NETWORK = os.environ.get("SN21_NETWORK", "finney")
SUBTENSOR_WS_URL = os.environ.get(
    "SUBTENSOR_WS_URL", "wss://entrypoint-finney.opentensor.ai:443"
)
RAO = 1_000_000_000
U96F32_SCALE = 2 ** 32


def configure_chain_ssl() -> None:
    """Point SSL at certifi so WebSocket chain connections verify on minimal
    images (e.g. Render). Same fix collector.py has always applied."""
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass


def bal(x: Any) -> float | None:
    """Float out of any chain value shape: plain number, v11 typed Balance
    (unit-guarded: .tao raises on alpha balances — try .decimal/.alpha/.tao),
    fixed-point {'bits': N} dicts (returned RAW — caller applies the scale),
    or the spec-430 newtype 1-tuples/lists."""
    if x is None:
        return None
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    while isinstance(x, (list, tuple)) and len(x) == 1:
        x = x[0]
    if isinstance(x, dict):
        x = x.get("bits")
        return float(x) if x is not None else None
    for attr in ("decimal", "alpha", "tao", "amount", "rao"):
        try:
            v = getattr(x, attr)
        except Exception:  # noqa: BLE001 — v11 Balance raises UnitMismatch on wrong unit
            continue
        if v is not None:
            f = float(v)
            return f / RAO if attr == "rao" else f
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def unwrap(x: Any) -> Any:
    """Unwrap substrate decode artifacts: ScaleObj.value and newtype 1-tuples."""
    x = getattr(x, "value", x)
    while isinstance(x, (list, tuple)) and len(x) == 1:
        x = x[0]
    return x


def bits(x: Any) -> float | None:
    """Numeric out of an unwrapped raw storage value; fixed-point dicts give
    their raw bits (caller divides by the scale)."""
    x = unwrap(x)
    if isinstance(x, dict):
        x = x.get("bits")
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def substrate():
    """Raw sync substrate connection (context-manageable). Caller closes or
    uses `with`."""
    configure_chain_ssl()
    from async_substrate_interface.sync_substrate import SubstrateInterface

    return SubstrateInterface(SUBTENSOR_WS_URL)


def qmap(sub, storage: str, scale: float = 1.0, params: list | None = None) -> dict[int, float]:
    """query_map a per-netuid SubtensorModule storage into {netuid: value/scale}."""
    out: dict[int, float] = {}
    for k, v in sub.query_map("SubtensorModule", storage, params or [], page_size=500):
        key = unwrap(k)
        val = bits(v)
        if key is None or val is None:
            continue
        out[int(key)] = val / scale
    return out


def get_subtensor(network: str = NETWORK):
    """A bittensor 11 client. Namespace reads: st.subnets / st.weights /
    st.prices / st.locks / ... ; historical: st.at(block).subnets.metagraph(n)."""
    configure_chain_ssl()
    import bittensor as bt

    return bt.Subtensor(network)


class _HParams:
    def __init__(self, tempo: int):
        self.tempo = tempo


class _Pool:
    def __init__(self, tao_in: float | None, alpha_in: float | None):
        self.tao_in = tao_in
        self.alpha_in = alpha_in


class LegacyMetagraph:
    """9.x-shaped view over a v11 Metagraph: plain-list vectors indexed by uid.

    Only the attributes our jobs actually consume. Vectors are plain lists —
    `.tolist()` is provided on them via _ListWithTolist for drop-in reads.
    v11 dropped the per-neuron validator_trust field, so it is passed in
    separately (read from ValidatorTrust storage).
    """

    def __init__(self, mg, pool: _Pool, validator_trust: list[float] | None = None):
        n = mg.num_uids
        by_uid = {int(neu.uid): neu for neu in mg.neurons}

        def vec(attr: str) -> "_ListWithTolist":
            out = []
            for uid in range(n):
                neu = by_uid.get(uid)
                out.append(bal(getattr(neu, attr, None)) or 0.0 if neu else 0.0)
            return _ListWithTolist(out)

        self.netuid = mg.netuid
        self.name = mg.name
        self.block = int(mg.block)
        self.tempo = int(mg.tempo)
        self.hparams = _HParams(int(mg.tempo))
        self.pool = pool
        self.price = bal(mg.price)
        self.moving_price = bal(mg.moving_price)
        self.owner_hotkey = mg.owner_hotkey
        self.owner_coldkey = mg.owner_coldkey
        self.uids = _ListWithTolist(list(range(n)))
        self.hotkeys = [str(by_uid[u].hotkey) if u in by_uid else "" for u in range(n)]
        self.coldkeys = [str(by_uid[u].coldkey) if u in by_uid else "" for u in range(n)]
        self.validator_permit = [
            bool(getattr(by_uid.get(u), "validator_permit", False)) for u in range(n)
        ]
        self.emission = vec("emission")        # alpha/tempo, 82% uid slice (as 9.x)
        self.dividends = vec("dividends")
        self.incentive = vec("incentive")
        self.stake = vec("total_stake")
        self.S = self.stake                     # 9.x aliases used by weights_scan
        self.I = self.incentive
        self.E = self.emission
        self.D = self.dividends
        self.last_update = _ListWithTolist([
            int(getattr(by_uid.get(u), "last_update", 0) or 0) for u in range(n)
        ])
        vt = list(validator_trust or [])
        self.validator_trust = _ListWithTolist(
            [float(vt[u]) if u < len(vt) else 0.0 for u in range(n)]
        )


class _ListWithTolist(list):
    def tolist(self) -> list:
        return list(self)

    def item(self) -> Any:  # scalar-style access parity for stray .item() calls
        if len(self) == 1:
            return self[0]
        raise ValueError("item() on non-scalar list")


def fetch_metagraph(netuid: int, network: str = NETWORK, block: int | None = None,
                    st=None) -> LegacyMetagraph:
    """Fetch a LegacyMetagraph at the tip (or a historical block via st.at)."""
    st = st or get_subtensor(network)
    view = st.at(block) if block is not None else st
    mg = view.subnets.metagraph(netuid)
    # mg.raw carries the pool at the SAME block as the metagraph (works for
    # historical snapshots too) — no separate storage round-trip needed.
    # Values are raw rao ints (verified live), so scale to decimal units here.
    raw = mg.raw if isinstance(getattr(mg, "raw", None), dict) else {}
    tao_in = bal(raw.get("tao_in"))
    alpha_in = bal(raw.get("alpha_in"))
    pool = _Pool(
        tao_in / RAO if tao_in is not None else None,
        alpha_in / RAO if alpha_in is not None else None,
    )
    vt = _fetch_validator_trust(netuid, block=block)
    return LegacyMetagraph(mg, pool, validator_trust=vt)


def _fetch_validator_trust(netuid: int, block: int | None = None) -> list[float]:
    """Per-uid validator trust (u16/65535 vector) from ValidatorTrust storage —
    v11's neuron model no longer carries it."""
    try:
        with substrate() as sub:
            bh = sub.get_block_hash(block) if block is not None else None
            raw = unwrap(sub.query("SubtensorModule", "ValidatorTrust", [netuid],
                                   block_hash=bh)) or []
        return [(bits(x) or 0.0) / 65535.0 for x in raw]
    except Exception as e:  # noqa: BLE001 — vtrust is auxiliary; don't kill the fetch
        logger.warning("ValidatorTrust query failed: %s", e)
        return []
