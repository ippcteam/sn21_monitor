"""
Deterministic fallback composer. Used when the LLM is disabled, missing a key,
or errors out. Produces a tight plain-text digest from the structured inputs.
"""

from __future__ import annotations

from typing import Any


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v: Any, places: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{places}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_alpha(v: Any) -> str:
    return _fmt_num(v, 2)


def _fmt_tao(v: Any) -> str:
    return _fmt_num(v, 4)


def _fmt_price(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.6f}"
    except (TypeError, ValueError):
        return "—"


def compose(inputs: dict[str, Any], title: str,
            prior_digests: list[dict[str, Any]] | None = None) -> str:
    lines: list[str] = []
    date = inputs.get("date") or "today"
    lines.append(f"{title} · {date}")

    # Stale-data warning up top (mirrors the LLM prompt's NOTE line).
    stale = inputs.get("stale_fields") or []
    if stale:
        lines.append(f"NOTE: stale data — {', '.join(stale)}")
    lines.append("=" * min(40, len(title) + len(str(date)) + 3))

    # OWNER — why we hold the subnet. Lead with it.
    oe = inputs.get("owner_economics") or {}
    if oe:
        lines.append("")
        lines.append("OWNER")
        lines.append(
            f"  entitled α: {_fmt_alpha(oe.get('entitled_alpha_today'))} "
            f"(7d {_fmt_pct(oe.get('entitled_7d_pct'))}, 30d {_fmt_pct(oe.get('entitled_30d_pct'))})"
        )
        lines.append(
            f"  owner pool: {_fmt_alpha(oe.get('owner_pool_alpha'))} α "
            f"(24h {_fmt_alpha(oe.get('owner_pool_delta_24h'))})   "
            f"wallet: {_fmt_tao(oe.get('wallet_balance_tao'))} τ "
            f"(24h {_fmt_pct(oe.get('wallet_change_24h_pct'))})"
        )
        if oe.get("burn_rate_pct") is not None:
            lines.append(
                f"  burn: {_fmt_num(oe.get('burn_rate_pct'), 2)}% — {oe.get('burn_regime') or '—'} "
                f"(7d {_fmt_pct(oe.get('burn_7d_pct_change'))})"
            )
        days_to_tier = oe.get("days_to_next_tier")
        if days_to_tier is not None and days_to_tier <= 14:
            lines.append(
                f"  next tier: {oe.get('next_tier_date')} "
                f"({days_to_tier}d → {_fmt_pct(oe.get('next_tier_rate_pct'))})"
            )

    # MARKET — is it us or the field?
    market = inputs.get("market") or {}
    price = inputs.get("price") or {}
    if market.get("available") or price:
        lines.append("")
        lines.append("MARKET")
        lines.append(
            f"  alpha {_fmt_price(price.get('alpha_price_tao'))} τ "
            f"(1d {_fmt_pct(price.get('alpha_1d_pct'))}, 7d {_fmt_pct(price.get('alpha_7d_pct'))}) "
            f"≈ ${_fmt_price(price.get('alpha_price_usd'))}"
        )
        if market.get("available"):
            b = market.get("breadth") or {}
            s = market.get("sn21") or {}
            lines.append(
                f"  {market.get('verdict_plain') or market.get('verdict') or '—'}"
            )
            lines.append(
                f"  field median {_fmt_num(b.get('median_move_24h_tao_pct'), 2)}% in TAO · "
                f"SN21 move pctile {s.get('move_24h_percentile') or '—'}"
            )

    # FLOWS — net, brand-aggregated, churn removed.
    flows = inputs.get("flows") or {}
    if flows.get("available"):
        lines.append("")
        lines.append("FLOWS")
        hd = flows.get("holder_delta")
        lines.append(
            f"  holders: {flows.get('holder_count') or '—'} "
            f"({_fmt_num(hd, 0) if hd is not None else '—'}) · "
            f"new {flows.get('new_positions') or 0} · exited {flows.get('exited_positions') or 0}"
        )
        lines.append(f"  house: net {_fmt_alpha(flows.get('house_net_alpha_7d'))} α (7d)")
        net_movers = flows.get("net_movers") or []
        if net_movers:
            lines.append("  net movers (7d, churn removed):")
            for m in net_movers:
                tag = " [SUSTAINED]" if m.get("sustained") else ""
                sign = "+" if (m.get("net_alpha_7d") or 0) >= 0 else "−"
                lines.append(
                    f"    {sign} {_fmt_alpha(abs(m.get('net_alpha_7d') or 0))} α  {m.get('name')}{tag}"
                )
        else:
            lines.append("  net movers: none above threshold")
        if flows.get("rotations_suppressed"):
            lines.append(
                f"  rotation suppressed: {flows['rotations_suppressed']} validator(s) "
                f"rotated coldkeys, net ≈ 0"
            )

    # RISKS / WATCH — only real flags.
    flags = inputs.get("flags") or []
    if flags:
        lines.append("")
        lines.append("RISKS / WATCH")
        for f in flags:
            lines.append(f"  ! {f}")

    # Prior-digest pointer (memory). The fallback can't synthesize across days,
    # but it can at least name the dates it has on file.
    if prior_digests:
        dates = [e.get("date") for e in prior_digests if e.get("date")]
        if dates:
            lines.append("")
            lines.append(f"MEMORY: {len(dates)} prior digest(s) on file — {dates[0]} → {dates[-1]}")

    return "\n".join(lines).strip()
