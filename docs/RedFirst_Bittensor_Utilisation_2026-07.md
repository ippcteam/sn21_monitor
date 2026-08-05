<!-- expires: 2026-10-01 -->
<!-- ^ anti-drift working-doc expiry: by this date re-run the scan (method in §9), re-stamp fresh, or delete. -->
# Red First — Bittensor Subnet Utilisation Scan (supplier side)

_Compiled 2026-07-03. Question: which of the 128 live subnets could RedFirst **consume** as
infrastructure/service suppliers for RedOS (storage, compute, inference, data, security, media), and
where does consuming them add value back to the Bittensor ecosystem? Method: full catalog pull via
taoflute (`materialized_overview_data`), 30 candidate subnets short-listed by category, then
per-subnet due-diligence (site + docs + repo + third-party coverage) via parallel research agents.
Companions: `RedFirst_Competitive_Landscape_2026-07.md` (who attacks us),
`RedFirst_Mining_Competitive_Landscape_2026-07.md` (who contests the PoR proposition) — this doc is
the third leg: **who supplies us**._

## 0. Bottom line

**Bittensor today is a spot market, not an enterprise supply chain.** Across 30 candidates in six
categories, almost nothing publishes an SLA, a DPA, or a compliance artifact, and most route customer
data through anonymous, permissionless miner hardware — structurally incompatible with RedOS's
sovereignty promise for tenant data. But that still leaves a real, immediately actionable seam:
**workloads that carry no tenant data** — open-weight LLM calls on public/synthetic content, Red Net's
public-web signal gathering, scraping egress, judge/eval compute, encrypted third-copy backups.

Four suppliers are pilot-grade **today**: **SN64 Chutes** (30–70% cheaper open-weight inference,
drop-in via the existing OpenRouter integration), **SN22 Desearch + SN13 Data Universe** (live APIs
with published pricing, 10–40× cheaper than X API/SerpAPI — they directly fill Red Net's stub-only
X connector and its SERP cost line), **SN75 Hippius** (S3-compatible encrypted cold backup at
~$0.003/GB-mo, own keys mandatory), and **SN65 TPN** (free WireGuard scraping-egress rotation,
alpha). Two more are cheap, fiat-payable **ensemble signals** for the Red Cycle audit side: **SN34
BitMind** (deepfake detection, $100/mo) and **SN32 ItsAI** (AI-text detection, $95/mo) — usable
only as one voter among several, never sole evidence. One is strategically interesting but
pre-enterprise: **SN4 Targon** (the only real TEE/confidential-compute asset on the chain — the
same problem RedOS's L6 "code comes to the data" inversion must solve). Everything else is
watch-list or avoid.

The deeper read: RedFirst's value to Bittensor is not what it can extract — it is that a
production platform with 10k projected tenants is exactly the **revenue-legible external demand**
every one of these subnets is starving for. Consuming even two of them at modest scale, publicly,
makes RedFirst a marquee demand-side story on the chain it already owns a subnet on (SN21) — and
that reputation compounds directly into the PoR launch (§7).

## 1. What RedOS actually buys — the demand map

From `ARCHITECTURE.md` / `REDOS_DEPLOYMENT_ARCHITECTURE.md`, the platform's real external spend lines:

| # | Cost line | Today | Sensitivity | Bittensor category |
|---|---|---|---|---|
| C1 | **LLM API spend** — $50–200/client/mo, "the margin-sensitive variable" | OpenRouter, Anthropic, OpenAI, Google | Prompts may contain tenant data (Class 1–2) | Inference (§2) |
| C2 | **External data APIs** — Red Net monitoring (social, SERP, news); X connector is stub-only | Per-platform APIs, BYOK | Public data — low sensitivity | Data/signals (§4) |
| C3 | **GPU/CPU compute** — agent runtimes, evals, CI, judge models; 10k-client projections | GKE node pools | Mixed — evals/CI are non-sensitive | Compute (§3) |
| C4 | **Storage/backup** — Cloud SQL, GCS, FalkorDB cold tier (D2 lakehouse option) | GCP | Tenant data = GDPR-classified | Storage (§5) |
| C5 | **Voice/TTS** — Eve via ElevenLabs | ElevenLabs | Low | Media (§6) |
| C6 | **Security testing** — audit-first Red Cycle, platform hardening | Internal + consultants | Brand-adjacent | Security (§6) |

The rule that falls out of the whole scan: **sensitivity is the axis, not category.** Anything that
touches tenant data stays on GCP/Anthropic-class suppliers until a subnet can show attested TEE + a
DPA. Anything that doesn't is candidate spot-market spend.

## 2. LLM inference (C1) — the biggest prize, one usable supplier

### SN64 Chutes (chutes.ai, Rayon Labs) — **pilot now, non-sensitive tiers only**
- **Real product:** self-serve console + OpenAI-compatible endpoint (`llm.chutes.ai/v1`); serves
  current open-weight frontier models (DeepSeek-V3.2, Qwen3.5/3.6, Kimi K2.6, GLM-5.x, Gemma 4);
  private dedicated GPU deploys; ~4,400 H100-equivalents, #1 revenue subnet on the chain.
- **Price:** e.g. Gemma 4 31B $0.12/$0.37 per MTok; Qwen3.5-397B $0.45/$3.00 — roughly 10–50% below
  centralized aggregators; USD card AND crypto accepted; $10–20/mo subscription tiers.
- **Zero-integration trial path:** Chutes is a listed **provider on OpenRouter** — RedOS can pin
  provider preference to Chutes for selected routes with no code change.
- **Caveats:** in standard mode **miners see plaintext prompts** (mitigated by attestation + egress
  blocking, not hardware isolation); TEE mode exists (Intel TDX + NVIDIA CC, opt-in — coverage and
  premium unverified); model availability is not contractual (documented abrupt rate-limiting of
  OpenRouter free traffic, weekly model churn); no public SLA; revenue figures conflict wildly across
  sources.
- **Fit:** Red Net signal filtering (currently Qwen 3.5 9B / GPT-4o-mini — public external data, no
  tenant content), judge/eval calls, synthetic workloads. **Not** for Eve/Oracle prompts over tenant
  knowledge unless pinned to verified TEE. Cannot replace Anthropic/OpenAI closed models at all.

### SN4 Targon (targon.com, Manifold) — **strategic watch, not a supplier yet**
- **What it actually is now:** a confidential-compute marketplace (GPU/CPU rentals with SSH, serverless
  containers, confidential VMs "TVM" on Intel TDX + NVIDIA CC/PPCIE) — the old per-token inference HUB
  is gone. **No managed OpenAI-compatible API today**; you'd run your own vLLM on rented H200s.
- **Substance:** $10.5M Series A (OSS Capital, Tobi Lütke), joint Intel TDX whitepaper (2026-03),
  attestation genuinely in shipped code, claimed 1,500+ H200s, credible ex-Opentensor team.
- **Red flags:** no public pricing at all; self-reported unaudited ~$10.4M ARR; only named customers
  are Bittensor-ecosystem; the orchestration layer delivering the confidentiality promise is
  closed-source; no DPA/SOC2/ISO artifacts; no SLA; SEV-SNP (RedOS's planned substrate) is roadmap only.
- **Why it still matters:** Targon and RedOS's PoR L6 inversion are attacking the **same problem** —
  running untrusted code/models against data that must not leak, with hardware attestation. Worth a
  technical conversation and possibly a paid attestation-audit pilot; not a dependency for the
  sovereignty brand yet.

### The rest of the inference field — not usable
- **SN28 gm (saygm.com)** — the one candidate that could in principle carry *closed-model* (Claude/GPT/
  Gemini) traffic, so it got a hard look. Verdict: **not usable.** Closed beta behind a ~2.4k waitlist;
  gateway is literally `test-api.saygm.com`; miner repo is 10 days old with 0 stars. Pricing is *at*
  maker list rates (Sonnet 4.6 $3/$15 — no saving), with the discount mechanism being emission-
  subsidized miner spread. The TEE story (Intel TDX via Phala, RA-TLS attestation) is real engineering,
  but the supply model is confirmed in their own README: **miners bring their own Anthropic/OpenAI keys**
  — RedOS prompts would exit to model providers in cleartext under random anonymous miners' accounts,
  almost certainly violating upstream ToS and destroying the DPA/ZDR chain RedOS gets from direct
  Anthropic enterprise terms. Contractually *worse* than the status quo, whatever the enclave does.
  Revisit only on first-party provider agreements + GA + SLA.
- **SN95 Actual** — genuinely sovereign by design (inference on your own hardware, OpenAI/Anthropic-compatible
  local APIs) but it's a **self-host orchestrator, not a supplier**: nothing to buy, no pricing, no
  enterprise motion. Architecturally the only Bittensor inference pattern compatible with per-tenant
  sovereignty — file under tooling-watch, not procurement.
- **SN96 Verathos** — live OpenAI-compatible API but weeks old (v0.1.19 shipped today), 3 small Qwen
  models, crypto-only billing; its sumcheck verification proves **integrity, not confidentiality** —
  prompts go plaintext to anonymous miners. Skip.
- **SN110 Green Compute** — avoid. Claims SOC 2 Type II three months after mainnet with no named
  auditor, "enclaves" on consumer RTX 4090/5090s (no TEE mode exists on those parts), no public
  miner code. Every trust-critical claim implausible or unverifiable.

## 3. GPU / general compute (C3) — spot capacity for non-sensitive workloads

### SN51 Lium (lium.io, Datura) — **the one real marketplace**
- Docker-pod rentals (sysbox runtime) across B300/H200/H100 down to consumer 3090s; verified live
  marketplace prices (8× B300 ≈ $8/GPU-hr, RTX 3090 from $0.16/hr); ~$5.3M annualized run-rate
  claimed — highest rental revenue on the chain; genuinely good REST API + Python SDK + CLI + MCP
  endpoint (agent-first by design).
- Caveats: anonymous permissionless hosts (root on your workload), **no SLA** ("broken pods" is a
  normalized doc page), no compliance artifacts, crypto-topup billing (fiat only via Coinbase on-ramp),
  nodes in Russia/Ukraine with no region-pinning controls. Intel TDX CVM node tier exists but
  renter-side attestation verification is undocumented.
- **Fit:** burst/spot GPU for PoR harness runs, model evals, CI, load tests — anything with zero
  tenant data. At B200-class prices this is materially cheaper than GCP for bursty jobs.

### The rest — not procurable
- **SN12 ComputeHorde** — well-engineered but **validator-to-validator infrastructure**; capacity is
  allocated by TAO stake, no purchase path for an external buyer. Relevant later as *PoR validation
  infrastructure* (it exists to make other subnets' validation cheap), not as a RedOS supplier.
- **SN39 Basilica (Covenant)** — real CLI/SDK for SSH GPU machines, 88 releases, fast-moving; but
  TAO-credits-only, no price list, placeholder website, "secure cloud" tier with unspecified
  guarantees. Re-check in 2 quarters.
- **SN106 Nodexo** — published USD prices ($0.49–1.49/hr A6000→A100) and an interesting x402
  agent-payment angle, but rebranded/recycled lineage, anonymous team, near-bottom alpha valuation,
  attestation claims unverified. Below Lium on every axis that matters.
- **SN128 ByteLeap** — credible VM/VFIO isolation design, but no discoverable customer product, no
  pricing, 12-commit repo, self-reported "95.1% utilization." Pre-product.
- **SN48 Quantum Compute** — pass-through brokerage to third-party QPUs (plausibly simulator-heavy);
  free demo tier; curiosity only.

## 4. Data & signals (C2) — Red Net's supply side. **Best category fit of the scan.**

Red Net consumes exactly what these subnets produce — public social/web/news signals — at zero
tenant-data sensitivity, and Red Net's X connector is currently stub-only. Two suppliers are real,
priced, and integrable this week.

### SN22 Desearch (desearch.ai, Datura) — **pilot first**
- Live commercial API + console + Python/TS SDKs. Four endpoints: AI search (multi-source,
  cited), **X search**, web/SERP search, web crawl; sources span web, X, Reddit, HN, Wikipedia.
- **Published usage pricing:** X Search $0.15/1k posts (vs X API Pro ~$5/1k → **~30× cheaper**);
  web search ~$1/1k queries (vs SerpAPI $8–15/1k → **~10× cheaper**); $100 free credits. These two
  lines are precisely Red Net's most expensive connectors.
- Caveats: miner-scraped X data (ToS-violating at source — a conscious risk acceptance), no
  published compliance posture, self-reported relevance benchmarks, X archive depth undocumented
  (assume recent-window). Gate behind a relevance/dedup harness; keep incumbent fallbacks
  configurable per tenant.

### SN13 Data Universe / "Gravity" (Macrocosmos) — **pilot in parallel, bulk + history**
- Live self-serve product: on-demand scrape jobs delivered as CSV/Parquet, plus a real-time
  validator-checked query API for X/Reddit; Python SDK + MCP server; claims 55B+ historic rows.
- **Published tiers:** $0.05–0.10/1k records PAYG, $99/mo = 300k records, $499/mo = 4M — ~15–40×
  cheaper than the X API. Best-documented compliance posture of the group (published GDPR/anonymization
  policy), though the underlying X-scraping ToS risk is identical to Desearch's.
- Fits Red Net's Celery model cleanly (submit job → poll → ingest). The `set_desirabilities`
  steering API even lets Red Net bias the miner fleet toward tenant-relevant keywords — effectively
  a shared scraping fleet Red Net can direct.

### Not usable
- **SN45 AlphaRidge** — financial-markets signals, Phase 1 is crypto/Bittensor-centric, core product
  "rolling out Summer 2026." Wrong domain for brand/competitor monitoring; revisit only if Red Brief
  grows a financial-markets module.
- **SN33 ReadyAI** — enrichment/structuring (MCP-first, $0.001/query), not a data source; competes
  with "prompt an LLM yourself." Low priority.
- **SN101 Tag101** — pre-product (4-commit repo, site unreachable, whitelisted-accounts-only corpus). Skip.
- **SN71 Leadpoet** — interesting for RedFirst's **own consultancy GTM** (miner-fulfilled enriched
  leads), but zero GDPR/consent/provenance story on personal contact data — untouchable until the
  compliance answer exists in writing. Park.

## 5. Storage & network (C4)

### SN75 Hippius (hippius.com) — **encrypted third-copy archive only**
- **Real S3-compatible storage, live today:** `s3.hippius.com` + EU/US gateways, AWS SigV4, works with
  rclone; Reed-Solomon 10+20 erasure coding across permissionless miners; **$0.003/GB-mo** (~30×
  cheaper than S3), Stripe fiat or TAO. The taoflute "dev stalled" signal is a false alarm — active
  daily commits live under `github.com/thenervelab` (checked 2026-07-03).
- **Hard limits:** key custody unspecified (assume the gateway encrypts = platform holds keys), no
  DPA/GDPR/residency story (the `eu-central-1` endpoint is a latency gateway, not residency), no
  durability SLA, pricing likely emission-subsidized. Gateway is a centralized chokepoint.
- **Fit:** third-copy off-site backup / cold archive **behind rclone-crypt with RedFirst-held keys
  only**. Never primary, never unencrypted, never Class 1–2 data without legal review. At these
  prices, backing up every tenant's Postgres dumps costs pocket change — a cheap way to become a
  visible paying customer of the chain.

### SN65 TAO Private Network (tpn.taofu.xyz) — **free scraping egress, use now**
- Working no-auth API: `GET /api/lease/new` returns WireGuard configs for chosen countries/durations;
  free in alpha (payment/auth explicitly disabled). Country-selectable exits — useful for Red Net
  UK/EU-geo SERP and public-web scraping rotation.
- Rules: **public-web scraping only** — never tenant data, never authenticated tenant sessions (exit
  operators are anonymous). Control plane is plain HTTP on bare IPs; budget zero reliability; pair
  with a commercial proxy. Re-evaluate when payment ships.

### Not suppliers
- **SN105 Beam** — pre-product bandwidth coordination (~7 real miners vs claimed 1,247); SOC2/HIPAA
  explicitly future-tense. Revisit only if bulk cross-cloud dataset movement ever becomes a need.
- **SN19 blockmachine** — irrelevant to RedOS, but a tidy $9–25/mo fiat-payable Bittensor RPC for
  **RedFirst's own SN21 chain ops** (weights_scan/market_sync currently hit public finney endpoints).
  The one trivially actionable purchase in this doc.

## 6. Media & security services (C5, C6)

### Media — keep paying ElevenLabs
- **SN78 Vocence** (TTS marketplace): pre-product — no API, no pricing, 2-star repo, acknowledged
  prior deregistration history; the −59%/30d alpha collapse tracks real relaunch risk. Re-check Q4.
- **SN59 Babelbit** (live speech-to-speech translation): credible named team, real browser demo,
  first broadcast-captioning reseller — but nothing integrable (no API), FR→EN only. Light watch;
  irrelevant to the TTS cost line.
- **SN56 Gradients** (AutoML fine-tuning, Rayon): real self-serve console + REST API, weights
  delivered via HuggingFace, self-published benchmark paper claims 100% win-rate vs Vertex-class
  AutoML (vendor claim, no independent replication). **Disqualifier today: training datasets are
  distributed to anonymous miners** — fine for public-data experiments, not for judge models trained
  on anything customer-derived (TEE "enterprise 5.0" mode announced, unshipped). Worth one throwaway
  public-data pilot job to price the quality claim.
- **SN44 Score** — football-vision infrastructure; no public API; irrelevant.
- **SN67 Harnyx** (deep research): **do not touch.** Waitlist-only API, fully anonymous team on a
  netuid whose predecessor (Tenex) was exploited and allegedly rugged in Jan 2026, "backed by DCG"
  claim corroborated nowhere, benchmark page doesn't load. Use OpenAI o3-deep-research / Perplexity
  Sonar for Red Brief synthesis. (Also downgrades Harnyx's standing in the PoR miner-poaching table
  in the mining landscape doc — an anonymous team on a rugged slot is a weaker talent pool than §8.3
  there assumed.)

### Security (Layer A adjacency) — two cheap ensemble signals now, three partnership seams, one skip

**Usable now (fiat, self-serve, as ensemble inputs only — never sole evidence):**
- **SN34 BitMind** (bitmind.ai) — deepfake/synthetic-media detection: real hosted REST API
  (image+video), free tier + **$100/mo Pro (10k reqs)**, USD-billed, active repo (70 releases),
  enterprise on-prem offered. Reality check: independent evaluation measured **68% accuracy / 52%
  recall, 0% on HeyGen-class commercial fakes** vs the marketed "95%" — wire it into Red Cycle
  evidence-gathering and RedOS synthetic-media checks as *one voter among several*. Bonus: their
  generative GAS track is a fresh-deepfake supply line — usable as **attack material** for Red Team
  exercises, arguably the more differentiated tie-up. Counterparty: Cayman entity, $750k raised,
  alpha −77% from ATH.
- **SN32 ItsAI** (its-ai.org) — AI-generated-text detection: real REST API + batch (2k texts/min),
  **Enterprise $95/mo** includes API, USD SaaS billing, verified top-tier RAID benchmark entry
  (94–97% at 1–5% FPR — below the "99%" headline). The API is exactly the shape for **Red Cycle
  shadow-AI sweeps** over client corpora. Category-level caution: detectors are paraphrase-evadable
  and biased against non-native prose — RedFirst must own false-positive governance; never
  single-source an accusation. One-man-band depth (Dubai FZCO); marketing outruns evidence.

**Partnership seams, not purchases:**
- **SN61 RedTeam / Innerworks** — the name-collision fear is **low-to-moderate and mostly moot**:
  the subnet sells nothing (miner-facing evasion challenges only), and the commercial wrapper —
  Innerworks Ltd (London, ~$4M seed, AlbionVC + DCG, board incl. Egress co-founder) — sells
  bot/fingerprint/synthetic-actor detection under the *Innerworks* brand, not "RedTeam"; zero
  enterprise-security-media footprint for the subnet name. Mitigation is hygiene: always brand
  house-mark-first ("RedFirst Red Team Certification"), £15 UKIPO check, defensive domains. The
  flip side is the real story: Innerworks' evasion telemetry as evidence-grade input to Red Cycle
  ("our audits are stress-tested against a live global evasion marketplace") and their bot-detection
  in RedOS tenant governance (human vs synthetic actor). Approach as an Innerworks partnership;
  ignore the token.
- **SN23 Trishool** (trishool.ai, Astroware — the +63%/30d mover, explained by Google-for-Startups
  acceptance, a Chutes guard-model integration, and Kraken alpha listings, not revenue) — a
  continuous jailbreak/prompt-injection mining loop that retrains guard models. Nothing purchasable
  (Guard API is item 7 of a 7-phase roadmap) and its own measured contribution is +0.78pp F1 over
  stock Qwen3Guard (the circulating "86%→<1%" number is Anthropic's Constitutional Classifiers
  result, which they merely adapt). But: the **Halo guard models are Apache-2.0 on HuggingFace** —
  a zero-cost RedOS input-guard experiment today — and their five-layer runtime-guardian design
  maps ~1:1 onto RedOS per-tenant governance. Their narrative ("a decentralized swarm out-red-teams
  any single red team") implicitly devalues human audit shops — better inside the tent:
  "RedFirst certifies; the swarm pressure-tests 24/7." Open the conversation while they're small.
- **SN60 Bitsec** (bitsec.ai) — AI security-audit agents over real codebases; V2 pivot to paid
  audits with one published paid engagement + one named reference; **free triage reports on all
  ~128 subnets are usable today at zero cost** (including as due-diligence input on any subnet in
  this doc). The +63%/30d is narrative/recovery speculation. Conditional: pilot one paid audit as a
  Red Cycle pre-screen feed before any deeper integration; the "$275M vulns found" claim is
  unverified.

**Skip:** **SN26 Perturb** — 8 weeks old, image-classifier adversarial examples only, 3 validators,
no product, no pricing, pseudonymous repo; the "on-chain robustness certificate / EU AI Act" idea is
directionally interesting but unshipped. 2-quarter watchlist at most.

## 7. What RedFirst gives back — the ecosystem story

The chain's chronic weakness (documented across all three landscape docs) is **demand**: nearly every
subnet is an emission-subsidized game with no external paying customers — "no named customers" was
the single most repeated finding in this scan. RedFirst can be the counter-example:

1. **Revenue-legible consumption.** A platform with a 10k-tenant target routing even its
   non-sensitive inference (C1 low tier) and Red Net data spend (C2) through subnets is among the
   largest *external* demand stories on the chain. This is precisely the demand-side substance that
   the flow-event study and qualitative-drivers work showed actually moves subnet valuations —
   revenue, not narrative.
2. **The PoR flywheel.** Consuming subnets builds the operational muscle (wallets, payment rails,
   miner-quality evaluation, attestation verification) that launching PoR requires anyway — and makes
   RedFirst a known, credible buyer before it becomes a subnet operator asking miners to trust it.
3. **SN21 synergy.** RedFirst already owns a netuid. Every TAO spent consuming other subnets, and
   every public write-up of that consumption, raises RedFirst's standing as an ecosystem operator —
   context that matters when SN21's own story is told.
4. **The enterprise bridge.** RedOS's sovereignty stack (per-tenant isolation, SEV-SNP plans, GDPR
   4-class discipline) is exactly what every compute subnet here lacks. There is a genuine
   partnership/consulting seam — e.g. helping Targon or Lium productize an attested, DPA-backed tier
   — where RedFirst's Layer A expertise is the product. That is "adding value to the ecosystem" in
   the most literal sense: teaching the chain's best infra how to pass an enterprise audit.

## 8. Recommended actions (ranked)

| # | Action | Cost | Risk | When |
|---|---|---|---|---|
| 1 | **Desearch** pilot for Red Net: X-search + SERP connectors behind a relevance/dedup harness ($100 free credits; ~30×/10× cheaper than X API/SerpAPI) | ~$0 to start | X-ToS provenance (accepted) | Now |
| 2 | Pin an OpenRouter route to **Chutes** for Red Net signal filtering (public data, open-weight) and measure quality/latency/cost vs GPT-4o-mini for 2 weeks | ~$0 setup | Low — public data only | Now |
| 3 | Stand up **TPN** WireGuard rotation for Red Net public-web scraping (alongside commercial proxy) | $0 (alpha) | Low | Now |
| 4 | **Data Universe/Gravity** $99 tier for bulk/historic social + the `set_desirabilities` steering experiment | $99/mo | Same X-ToS risk | This month |
| 5 | **Hippius** third-copy encrypted backup via rclone-crypt (RedFirst keys) for non-tenant repo/ops data first | ~$5/mo | Low | Now |
| 6 | **blockmachine** Standard tier for SN21 chain ops RPC | $9/mo | Trivial | Now |
| 7 | **BitMind + ItsAI** as a two-detector ensemble prototype for Red Cycle shadow-AI/synthetic-media sweeps (RedFirst-owned false-positive governance on top) | ~$195/mo | Medium — recall limits documented in §6 | This month |
| 8 | Pull **Bitsec's free subnet triage reports** into Red Cycle pre-screen tooling; consider one paid audit pilot | $0 | Low | This month |
| 9 | Self-host **Trishool Halo guard** (Apache-2.0) as a RedOS input-guard experiment; open the "certify + swarm pressure-test" partnership conversation | GPU time | Low | This quarter |
| 10 | One throwaway **Gradients** fine-tune job on a public dataset to price the judge-model claim | ~$100–500 | Low | This month |
| 11 | Technical conversations: **Targon** (TDX attestation, SEV-SNP roadmap — substrate option + PoR L6 design input) and **Innerworks** (bot-detection for RedOS governance; defuses the SN61 name question as a side effect) | Time | — | This quarter |
| 12 | **Lium** spot pods for PoR harness/eval burst compute when Phase 2 starts | Usage | Medium (no SLA) | With PoR |

Hard rule across all of it: **no tenant data leaves the GCP boundary to any subnet** until one of
them produces verifiable TEE attestation + a signed DPA. Today none can. Second rule: everything
above is spot-market spend — keep incumbent fallbacks configured and treat any subnet supplier as
capable of degrading or repricing within weeks (Chutes' documented OpenRouter rate-limit episode is
the canonical example).

## 9. Reproduce / refresh this scan

Catalog pull (client: `movers_attribution.tf_query`):

```sql
select sn_id, subnet_name, subnet_url, repo_url, twitter, summary, description,
       tao_in, price, month_price_change_perc, dereg_place,
       last_discord_msg_days, avg_code_lines_30d, registered_on
from materialized_overview_data order by sn_id::int
```

Bucket by category keywords (compute|gpu|storage|inference|search|scrap|data|vpn|voice|security),
then verify each candidate against its live site/docs/repo — taoflute summaries routinely lag
pivots (Targon's HUB removal, SN39's Basilica relaunch, SN67's rug-and-rebrand were all invisible
in the catalog). Re-check the four "pilot now" names first; spot-market suppliers can degrade in
weeks. taoflute is an accidental open proxy and may lock down — degrade to taostats if so.
