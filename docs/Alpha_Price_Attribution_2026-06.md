# SN21 Alpha-Price Attribution — June 2026 rally (baseline note)

**Author:** Engineering, for Rob
**Date:** 2026-06-29
**Question being tracked:** How much of an SN21 alpha-price move is **messaging** vs **mechanics**, and should we prioritise messaging? This note is the **first dated baseline** so the *next* SN21-specific move can be compared against it.
**Data sources:** taoflute Grafana→Postgres proxy (ohlc, materialized_news, discord_messages, materialized_overview_data); X Listen service (`map-listen-x.onrender.com`, own-post metrics + propagation); our market/holders tracking. All pulled 2026-06-29.

---

## 1. What actually happened (don't mis-frame it)

The "rise since mid-June" is a **late-June recovery rally, SN21-specific, measured in alpha/TAO** (not a TAO/USD artifact, not market beta).

| Window | SN21 | Field median | SN21 percentile |
|---|---|---|---|
| Jun 15 → 30 | +6.2% | +0.7% | 70th |
| **Jun 22 → 30** | **+24.2%** | **+1.7%** | **90th** |
| Jun 6 → 30 | +27.2% | +1.4% | 86th |

Shape: a mid-June bump (Jun 10–16, peak 0.00438) that **faded** to a Jun 22 low of 0.003615, then an 8-day climb to 0.00449 — back to late-May levels (recovery, not breakout). Field was flat (~+1.7% median, ~57% of subnets up), so the move is **idiosyncratic to SN21**. taoflute's own `month_price_change_perc` = **+19.4%** corroborates.

---

## 2. Mechanics: ruled out as the driver (mild headwind, if anything)

- `sno_staking` + `sno_alpha_transfer_in_tao` run a **constant 4×/day, every day** May→June (steady owner-share accrual). No step-change.
- Circulating alpha **+3.1%** over 30d (4.52M→4.66M) — **dilutive**. Burn continued (+12%; 1 manual burn/30d).
- `protocol_buy_pressure: −81.5` (**negative**); `alpha_out` 2.76M > `alpha_in` 1.87M.
- Only coincident on-chain event: `emissions_recovered` on **Jun 23** (rally start) — but that *adds* supply, so likely return-to-normal, not the cause.

**→ Price rose +24% *despite* mechanics. Mechanics did not cause this rally.**

---

## 3. The key blind spot: demand arriving off-protocol

taoflute shows `last_x_msg_days: 999`, `recent_tweet: None` for SN21 — it tracks **zero** of our tweets. So an attention/narrative-driven bid is **invisible** to every mechanics-based metric, while protocol buy pressure stays negative. The coherent read: **discretionary secondary-market accumulation / holder broadening** driven by narrative — corroborated by our own Jun 28 post ("wallets +8% to 2,183") and +140k circulating-alpha/30d distribution. This is exactly the gap the X Listen ingestion (Social tab) now fills.

---

## 4. Messaging: plausible catalyst, NOT yet a proven cause (low-to-moderate confidence)

- Only `@adtao_ppcrebel` active (10 June posts; `@RobWarner` dormant).
- **10-day posting silence Jun 12→22; posting resumed exactly Jun 22 = rally start**, with a new-customer announcement (50+-loc hair-salon franchise). A second customer announcement Jun 26 *precedes* the Jun 26→28 up-leg (genuine lead by dates).
- **Theme reach (June):** revenue/buyback/financials 63% of views (Jun 2/6/8; buyback 9.6k, financials 8k), new-customer announcements 27% (the rally-aligned ones, ~3k views each), community 6%, holders/hype 5%.
- **Counter-evidence (why not to over-claim):** early-June posts had *2–3× the reach* and did **not** hold the price (faded to Jun 22 low). The Jun 28 "price is rising, all aboard" post is explicitly **lagging**.
- **Discord:** spiked Jun 15–16 (126→181 msgs) around the bump that *faded*, then near-silent (1–14/day) through the real rally → attention noise, not driver (matches our movers backtest: discord is bidirectional attention).

---

## 5. Verdict (this rally)

The +24% late-June move is **SN21-specific demand that mechanics don't explain and partly oppose**. Best-supported explanation: a **fundamentals/narrative catalyst** — real-customer + revenue + buyback proof, surfaced on X from Jun 22 — pulling discretionary buyers into alpha and broadening the holder base. **Messaging is a credible contributing trigger** (Jun 22 date-alignment is the strongest single clue), but small measured reach + the early-June counter-example mean it is not provably *the* cause.

**Rough split, this rally (judgement, not measured):** mechanics ≈ 0 / slightly negative; narrative-driven discretionary demand ≈ the bulk; messaging = the most likely *trigger* of that demand but un-sized. Treat messaging as **"prioritise and instrument,"** not "proven lever," until §6 data exists.

---

## 6. Why we can't size message-vs-mechanics yet — and the fix is live

The blocker is **history**: X Listen only began sampling post views ~Jun 26 and has a single follower snapshot, so there is no intra-rally **view-velocity** or **follower-growth** curve to test lead/lag. Now that the Social tab ingests it, the **next** SN21-specific move is the one we can attribute properly.

**Attribution checklist for the next move (compare to this baseline):**
1. **Is it SN21-specific?** Re-run the field-median vs SN21 percentile table (§1). If field is up too, it's beta — stop.
2. **Mechanics changed?** Check `materialized_news` for a *step-change* (not the steady 4×/day), `protocol_buy_pressure` turning positive, circulating-alpha/burn shifts. If none, mechanics is out again.
3. **Messaging lead?** From X Listen: did **view-velocity** and **follower growth** on customer/revenue posts *rise before* the up-days? Did a high-authority account amplify (propagation `engager_authority_score` — was 0 this round)?
4. **Holder broadening?** Does wallet count keep rising while protocol buy pressure stays negative? That's the signature of attention-driven, off-protocol demand.
5. **Theme test:** does the up-move follow **revenue/customer-proof** posts specifically (vs generic hype)? June suggests proof > hype, but n is tiny.

**Decision rule for "prioritise messaging":** if across 2–3 future SN21-specific moves the **customer/revenue-proof posts repeatedly lead** up-days on view-velocity AND holder count broadens, messaging is a real lever → prioritise. If moves recur with flat/lagging messaging, the driver is elsewhere (whales, listings, external coverage) → instrument that instead.

---

## 7. Open data gaps to close
- No intra-day **view-velocity** series before ~Jun 26 (now accruing).
- Propagation **authority scores all 0.0** — X Listen isn't scoring amplifier reach yet; without it we can't tell a whale-RT from a bot.
- **Holder-count time series** not on the Social tab yet (only cited in our own posts). Overlaying holder count + buy pressure beside the posts would make the demand-broadening signal visible. (Candidate next build.)
