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
    lines.append("=" * min(40, len(title) + len(str(date)) + 3))

    # Price
    price = inputs.get("price") or {}
    if price:
        lines.append("")
        lines.append("PRICE")
        lines.append(
            f"  alpha: {_fmt_price(price.get('alpha_price_tao'))} τ "
            f"(1d {_fmt_pct(price.get('alpha_1d_pct'))}, 7d {_fmt_pct(price.get('alpha_7d_pct'))})"
        )
        if price.get("alpha_price_usd") is not None:
            lines.append(f"  alpha: ${_fmt_price(price.get('alpha_price_usd'))}")
        lines.append(
            f"  TAO:   ${_fmt_num(price.get('tao_price_usd'), 2)} "
            f"(1d {_fmt_pct(price.get('tao_1d_pct'))})"
        )

    # Volume / depth
    pool = inputs.get("pool") or {}
    if pool:
        lines.append("")
        lines.append("POOL · 24H")
        lines.append(
            f"  buys  {pool.get('buys_24h') or 0} from {pool.get('buyers_24h') or 0} buyers   "
            f"({_fmt_alpha(pool.get('alpha_buy_volume_24h'))} α / {_fmt_tao(pool.get('tao_buy_volume_24h'))} τ)"
        )
        lines.append(
            f"  sells {pool.get('sells_24h') or 0} from {pool.get('sellers_24h') or 0} sellers "
            f"({_fmt_alpha(pool.get('alpha_sell_volume_24h'))} α / {_fmt_tao(pool.get('tao_sell_volume_24h'))} τ)"
        )
        lines.append(
            f"  liquidity: {_fmt_tao(pool.get('liquidity_tao'))} τ   "
            f"market cap: {_fmt_tao(pool.get('market_cap_tao'))} τ"
        )

    # Holder activity
    movers = inputs.get("movers") or {}
    if movers:
        lines.append("")
        lines.append("HOLDERS · 24H")
        lines.append(
            f"  count: {movers.get('today_holder_count') or '—'} "
            f"(was {movers.get('prior_holder_count') or '—'}, "
            f"new {movers.get('new_positions') or 0}, exited {movers.get('exited_positions') or 0})"
        )
        lines.append(
            f"  inflows:  {_fmt_alpha(movers.get('inflows_alpha'))} α   "
            f"(house {_fmt_alpha(movers.get('house_inflows_alpha'))})"
        )
        lines.append(
            f"  outflows: {_fmt_alpha(movers.get('outflows_alpha'))} α   "
            f"(house {_fmt_alpha(movers.get('house_outflows_alpha'))})"
        )

        top_in = (movers.get("top_inflows") or [])[:3]
        if top_in:
            lines.append("  top inflows:")
            for r in top_in:
                lines.append(f"    + {_fmt_alpha(r.get('alpha_delta'))} α  {_label_for(r)}")
        top_out = (movers.get("top_outflows") or [])[:3]
        if top_out:
            lines.append("  top outflows:")
            for r in top_out:
                lines.append(f"    − {_fmt_alpha(abs(r.get('alpha_delta') or 0))} α  {_label_for(r)}")
        exits = (movers.get("notable_exits") or [])[:3]
        if exits:
            lines.append("  notable exits:")
            for r in exits:
                lines.append(f"    × {_fmt_alpha(abs(r.get('alpha_delta') or 0))} α  {_label_for(r)}")

    # Owner pool
    owner = inputs.get("owner_pool") or {}
    if owner:
        lines.append("")
        lines.append("OWNER POOL")
        lines.append(
            f"  alpha: {_fmt_alpha(owner.get('alpha_now'))} α   "
            f"24h Δ: {_fmt_alpha(owner.get('alpha_delta_24h'))}"
        )
        if owner.get("balance_total_tao") is not None:
            lines.append(
                f"  wallet: {_fmt_tao(owner.get('balance_total_tao'))} τ   "
                f"24h Δ: {_fmt_pct(owner.get('balance_change_24h_pct'))}"
            )

    # Trends — 7d / 30d for the metrics that matter
    trends = inputs.get("trends") or {}
    if trends:
        lines.append("")
        lines.append("TRENDS · 7D / 30D")
        for label, key, places in [
            ("alpha price τ", "alpha_price_tao", 6),
            ("TAO USD", "tao_price_usd", 2),
            ("holders", "holder_count", 0),
            ("liquidity τ", "liquidity_tao", 2),
            ("burn rate %", "burn_rate_pct", 2),
            ("our entitled α", "our_entitled_alpha", 4),
        ]:
            t = trends.get(key) or {}
            today = t.get("today")
            if today is None:
                continue
            lines.append(
                f"  {label:<14} {_fmt_num(today, places)}   "
                f"7d {_fmt_pct(t.get('7d_pct'))}   30d {_fmt_pct(t.get('30d_pct'))}"
            )

    # Multi-window movers
    for w_key, w_label in [("movers_7d", "MOVERS · 7D"), ("movers_30d", "MOVERS · 30D")]:
        w = inputs.get(w_key) or {}
        top = (w.get("top") or [])[:5]
        if not top:
            continue
        actual = w.get("actual_days")
        suffix = f" (since {w.get('from_date') or '—'}, ~{actual}d)"
        lines.append("")
        lines.append(f"{w_label}{suffix}")
        for r in top:
            sign = "+" if r.get("alpha_delta", 0) >= 0 else "−"
            mag = _fmt_alpha(abs(r.get("alpha_delta") or 0))
            ck = (r.get("coldkey") or "")[:10]
            names = ", ".join((r.get("hotkey_names") or [])[:2]) or ck + "…"
            tags = []
            if r.get("is_house"): tags.append("house")
            if r.get("is_new"): tags.append("NEW")
            if r.get("is_exited"): tags.append("EXITED")
            if r.get("brand"): tags.append(r["brand"])
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {sign} {mag} α  {names}{tag_str}")

    # Burn / emissions
    burn = inputs.get("burn") or {}
    if burn:
        lines.append("")
        lines.append("BURN / EMISSIONS")
        if burn.get("burn_rate_pct") is not None:
            lines.append(f"  burn rate: {_fmt_pct(burn.get('burn_rate_pct'))} of miner emissions")
        if burn.get("active_validators") is not None or burn.get("active_miners") is not None:
            lines.append(
                f"  active: {burn.get('active_validators') or '—'} validators, "
                f"{burn.get('active_miners') or '—'} miners"
            )
        if burn.get("recycled_24h_tao") is not None:
            lines.append(f"  recycled 24h: {_fmt_tao(burn.get('recycled_24h_tao'))} τ")

    # Tier
    tier = inputs.get("tier") or {}
    if tier and tier.get("next_tier_date"):
        lines.append("")
        lines.append("TIER")
        lines.append(
            f"  next flip: {tier.get('next_tier_date')} "
            f"(in {tier.get('days_to_next_tier')} days, → {_fmt_pct(tier.get('next_tier_rate_pct'))})"
        )

    # Anomalies / flags
    flags = inputs.get("flags") or []
    if flags:
        lines.append("")
        lines.append("FLAGS")
        for f in flags:
            lines.append(f"  ! {f}")

    # Stale data warning
    stale = inputs.get("stale_fields") or []
    if stale:
        lines.append("")
        lines.append(f"NOTE: stale data — {', '.join(stale)}")

    # Prior-digest pointer (memory). The fallback can't synthesize across days,
    # but it can at least name the dates it has on file.
    if prior_digests:
        dates = [e.get("date") for e in prior_digests if e.get("date")]
        if dates:
            lines.append("")
            lines.append(f"MEMORY: {len(dates)} prior digest(s) on file — {dates[0]} → {dates[-1]}")

    return "\n".join(lines).strip()


def _label_for(row: dict[str, Any]) -> str:
    name = row.get("hotkey_name") or ""
    coldkey = (row.get("coldkey") or "")[:10]
    is_house = " [house]" if row.get("is_house") else ""
    is_exit = " EXITED" if row.get("is_exited") else (" NEW" if row.get("is_new") else "")
    if name:
        return f"{name} · {coldkey}…{is_house}{is_exit}"
    return f"{coldkey}…{is_house}{is_exit}"
