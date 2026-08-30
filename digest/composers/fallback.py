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


def _display_or(v: Any) -> str:
    return str(v) if v else "—"


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
                f"  burn: {_fmt_num(oe.get('burn_rate_pct'), 2)}% — {oe.get('burn_regime') or '—'}"
            )
        days_to_tier = oe.get("days_to_next_tier")
        if days_to_tier is not None and days_to_tier <= 14:
            lines.append(
                f"  next tier: {oe.get('next_tier_date')} "
                f"({days_to_tier}d → {_fmt_pct(oe.get('next_tier_rate_pct'))})"
            )

    # TAPE — 24h AMM pulse (sentiment + buy/sell τ).
    tape = inputs.get("tape") or {}
    if tape.get("available"):
        lines.append("")
        lines.append("TAPE")
        sent = tape.get("sentiment_index")
        sent_s = "—" if sent is None else _fmt_num(sent, 0)
        label = tape.get("sentiment_label") or ""
        sent_7d = tape.get("sentiment_7d_delta")
        swing = f" (7d {_fmt_num(sent_7d, 0)})" if sent_7d is not None else ""
        lines.append(f"  sentiment {sent_s} {label}{swing}".rstrip())
        lines.append(
            f"  {tape.get('buys_24h') or '—'} buys / {tape.get('sells_24h') or '—'} sells · "
            f"{tape.get('buyers_24h') or '—'} buyers / {tape.get('sellers_24h') or '—'} sellers"
        )
        net = tape.get("net_tao_24h")
        net_s = "—" if net is None else f"{float(net):+.2f}"
        lines.append(
            f"  +{_fmt_num(tape.get('tao_buy_volume_24h'), 2)} τ bought / "
            f"−{_fmt_num(tape.get('tao_sell_volume_24h'), 2)} τ sold · net {net_s} τ"
        )
        if tape.get("verdict_plain"):
            lines.append(f"  {tape['verdict_plain']}")

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
        h24 = flows.get("house_net_alpha_24h")
        if h24 is not None and abs(float(h24)) >= 500:
            lines.append(f"  house: net {_fmt_alpha(h24)} α (24h)")
        net_movers = flows.get("net_movers") or []
        if net_movers:
            lines.append("  net movers (7d, rotation removed):")
            for m in net_movers:
                sign = "+" if (m.get("net_alpha_7d") or 0) >= 0 else "−"
                lines.append(
                    f"    {sign} {_fmt_alpha(abs(m.get('net_alpha_7d') or 0))} α  {m.get('name')}"
                )
        if flows.get("rotations_suppressed"):
            lines.append(
                f"  rotation suppressed: {flows['rotations_suppressed']} validator(s) "
                f"rotated coldkeys, net ≈ 0"
            )

    # ROOT BASKETS — V450 curated dividend stream. Adds/drops first.
    rb = inputs.get("root_baskets") or {}
    if rb.get("available"):
        if rb.get("is_baseline"):
            lines.append("")
            lines.append("ROOT BASKETS")
            lines.append(
                f"  baseline: {rb.get('n_included') or rb.get('n_curating') or 0} included · "
                f"{rb.get('n_excluded') or 0} excluded · "
                f"{rb.get('n_no_vector') or 0} no vector · "
                f"{_fmt_num(rb.get('realizable_tao_21'), 2)} τ in 21. No Δ yet."
            )
        elif rb.get("n_significant"):
            lines.append("")
            lines.append("ROOT BASKETS")
            lines.append(
                f"  included 21: {rb.get('n_included') or rb.get('n_curating') or 0} · "
                f"excluded: {rb.get('n_excluded') or 0} · "
                f"no vector: {rb.get('n_no_vector') or 0} · "
                f"{_fmt_num(rb.get('realizable_tao_21'), 2)} τ"
            )
            adds = rb.get("adds") or []
            drops = rb.get("drops") or []
            if adds:
                lines.append(f"  ADD: {', '.join(adds)}")
            if drops:
                lines.append(f"  DROP: {', '.join(drops)}")
            for c in rb.get("significant") or []:
                reasons = c.get("reasons") or []
                if "curated_add" in reasons or "curated_drop" in reasons:
                    continue
                label = _display_or(c.get("name"))
                if "share_move" in reasons:
                    lines.append(
                        f"  {label}: share {c.get('share_pp')} "
                        f"({_fmt_num(c.get('share_pp_delta'), 2)} pp)"
                    )
                elif "position_move" in reasons:
                    lines.append(
                        f"  {label}: pos {_fmt_num(c.get('sn21_tao'), 2)} τ "
                        f"({_fmt_num(c.get('sn21_tao_delta'), 2)})"
                    )
                elif "leftover_new" in reasons:
                    lines.append(
                        f"  leftover {label}: {_fmt_num(c.get('sn21_tao'), 2)} τ"
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
