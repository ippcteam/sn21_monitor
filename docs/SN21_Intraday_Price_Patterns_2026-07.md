# SN21 Alpha — Intraday (Time-of-Day) Price Pattern Check — July 2026

**Author:** Engineering, for Rob
**Date:** 2026-07-10
**Question:** Rob's observation: *"SN21 alpha takes a reduction in price every morning and builds up later during the day."* Is that a real, consistent time-of-day pattern, or an observed-pattern illusion?

**Data:** 60 days (2026-05-11 → 2026-07-10) of hourly SN21 pool snapshots read directly from the Bittensor archive chain (`SubtensorModule.SubnetTAO / SubnetAlphaIn` at ~300-block steps — the same `tao_in/alpha_in` price Taostats displays). 1,440 samples, 1,439 hourly returns. Control series: hourly TAO/USD (CoinGecko) over the identical window, so the alpha/TAO view (SN21-specific flow) can be separated from the USD view (which folds in TAO's own daily cycle). The Taostats API key lives only on the Render deployment, so the chain archive was used as the equivalent source; prices reconcile with our daily ledger.

---

## Verdict: the "morning dip, afternoon build" is NOT a reliable pattern

Direct test of the hypothesis (UK morning = 05:00–11:00 UTC in summer; afternoon = 12:00–18:00 UTC), per calendar day over 60 days:

| Event | Days | Share | Chance baseline |
|---|---|---|---|
| Morning was down | 30 / 60 | **50%** | 50% |
| Afternoon was up | 32 / 60 | 53% | ~50% |
| Full dip-then-build shape | 18 / 60 | **30%** | 27% if independent |

Mornings are a coin flip. The full shape Rob describes happens on ~3 days in 10 — indistinguishable from chance.

**Hour-of-day regression:** across all 24 UTC hourly buckets of alpha/TAO returns, **zero** buckets are statistically significant (|t| > 2); pure chance would produce ~1. Half-day windows (00–12 vs 12–24 UTC): +2bp vs +11bp mean, t ≈ 0. Nothing.

**Stability check (the decisive one):** splitting the 60 days in half, the hour-by-hour means don't replicate — they flip sign:

| Hour (UTC) | First 30d | Last 30d |
|---|---|---|
| 09:00 (the "morning dip") | −35 bp | **+1 bp** |
| 10:00 | −25 bp | **+36 bp** |
| 15:00 (the "afternoon build") | +75 bp | **+8 bp** |

A real daily rhythm survives a split-half test. This doesn't.

## Why the pattern *feels* real (it's not pure imagination)

1. **The average-day silhouette does match the story.** Averaged over 60 days, the cumulative intraday profile sags to −29bp by 14:00 UTC and recovers to +28bp by 17:00 UTC. If you glance at the average chart, "down in the morning, builds in the afternoon" is what it looks like.
2. **But that silhouette is a handful of outlier days, not a rhythm.** The 15:00 UTC "build" totals +2,485bp over 60 days — and just two days (Jun 2, Jun 6: +859bp and +767bp single-hour pumps) contribute 65% of it. The 09:00 UTC "dip" (−1,019bp total) is 84% two days (Jun 2 −557bp, Jun 29 −297bp). Median return at 15:00 is only +2.4bp. Remove a few memorable days and the shape evaporates.
3. **Confirmation bias does the rest:** a −0.1bp median drift most hours (the mechanical bleed when no buys arrive) means a morning glance often catches red, and the occasional big afternoon pump is what gets remembered.

## What IS (weakly) visible

- **Late-morning house buys leave a fingerprint — upward, not downward.** `sno_staking` ops cluster 08:00–15:00 UTC, peaking 10:00–11:00. Hour 11 UTC has the **highest median** hourly return of the day (+23bp, 57% of hours positive). If anything, SN21's scheduled flow supports the price late morning — the opposite of a morning dip.
- **In USD terms**, 18:00 UTC is the single weakest hour (−46bp, t = −2.5) — but it's 1 significant bucket out of 72 tested (≈ chance), and TAO/USD itself is weak at 18:00 (−26bp), so most of it is TAO's cycle, not SN21.
- **Day-of-week (n=8–9 each, anecdotal only):** Tuesdays strong (+298bp avg, 7/9 up), Fri/Sat weak (−148/−113bp). Too few weeks to act on; worth re-checking with 6 months of data.

## Bottom line

There is no consistent, exploitable time-of-day movement in SN21 alpha over the last 60 days. The morning-dip perception is an averaging artifact of a few large idiosyncratic move-days (which our attribution work already tracks event-by-event) plus the slow ever-present mechanical drift. Don't time entries/exits by clock hour; keep attribution focused on the event-driven moves (customer/revenue news, whale flows) per `Alpha_Price_Attribution_2026-06.md`.

**Method note for re-runs:** sampler + analysis were one-off scripts against `wss://archive.chain.opentensor.ai:443` (2 pipelined RPCs per sample: `chain_getBlockHash`, then `state_queryStorageAt` for Timestamp.Now / SubnetTAO / SubnetAlphaIn). ~35 min for 60d hourly. Re-run after a few more months if the day-of-week hint is worth confirming.
