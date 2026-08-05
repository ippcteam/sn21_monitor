<!-- expires: 2026-10-01 -->
<!-- ^ anti-drift working-doc expiry: by this date re-run the scan (method in §7), re-stamp fresh, or delete. -->
# Red First — Mining Competitive Landscape (Proof-of-Recall vs the field)

_Compiled 2026-07-02. Scope: does any Bittensor subnet already occupy — or credibly neighbour — the
Proof-of-Recall proposition (`BITTENSOR_SUBNET_DESIGN_PROOF_OF_RECALL.md`)? Method: full 128-subnet catalog
scan via taoflute (`materialized_overview_data` summaries/descriptions + `materialized_news` event history),
cross-checked against taostats. Companion: `RedFirst_Competitive_Landscape_2026-07.md` (business-layer
challengers — different question; this doc is subnet-proposition only)._

_**Mining/validation + alpha-price scan added 2026-07-02** (see §8): repos located and read for every
competitor, incentive mechanics summarised, current alpha price + 30d trend captured via taoflute. Two
reclassifications resulted (Ditto, SOMA — flagged inline in §3)._

## 0. Bottom line

**The proposition is unoccupied.** No live subnet runs a private-corpus context-assembly competition —
inverted evaluation ("code comes to the data"), temporal-validity scoring, recall@token-budget, or a
beat-the-production-baseline gate. One dormant netuid (SN31 "rec4ll") squats the *narrative and the name*;
several live subnets each overlap exactly **one leg** of PoR; and the miners-submit-code *mechanism* is
already proven elsewhere on the chain (which de-risks the design without contesting the proposition).
One prior pure-RAG-component subnet (Chunking) died — a cautionary datapoint on scoping, not on demand.
The 2026-07-02 mechanics scan (§8) *tightens* one gap: DittoBench (SN118) now runs a submit-code,
validator-executed competition that scores memory-retrieval quality — the closest live thing to PoR's
game — but still misses the temporal-validity leg, the token-budget leg, the private-tenant inversion,
and production-consumption revenue attribution. The composite proposition remains unoccupied; the margin
is thinner than it looked.

## 1. The comparison frame

PoR is distinctive on five axes. Every subnet below is scored against these:

| Axis | Proof-of-Recall's position |
|---|---|
| **Commodity** | A *function* (context-assembly module), not data, inference, or a hosted service |
| **Data topology** | Inverted — miner code runs sandboxed inside our infra; tenant data never leaves; only scores exit |
| **Scoring** | Deterministic composite: needle recall@budget × temporal correctness × groundedness × token efficiency, hard latency gate, beat-the-baseline margin |
| **Consumption path** | Winning module ships into a production `ContextAssembler` behind a canary; `oracle_query` metering gives per-module revenue attribution |
| **Temporal validity** | First-class scored leg (Stack D `valid_from`/`valid_to`) — nobody on the chain benchmarks this |

## 2. Direct collision — SN31 "rec4ll" (dormant)

**Their pitch (on-chain description):** "Recall provides decentralized retrieval-augmented generation to
Bittensor. Miners serve embedding models, vector search, and LLM inference. Validators independently
evaluate retrieval accuracy and answer quality. The subnet discovers the best RAG pipeline through open
competition and routes user queries to the top performers."

**Similarities:** the *story* is nearly identical — open competition over retrieval quality, validators
scoring retrieval accuracy + answer quality, "best RAG pipeline wins." If a journalist summarized both in
one sentence, they'd collide. The name collides too ("Recall" / "rec4ll" vs "Proof-of-Recall").

**Differences (topology is the opposite):**
- rec4ll miners **host** generic RAG infrastructure and queries are routed *out* to them → data leaves the
  querier. PoR inverts this: code comes to the data; nothing leaves the tenant boundary. rec4ll structurally
  cannot serve a private-corpus customer; PoR is built for exactly that.
- rec4ll scores a *service* (uptime + answers); PoR scores a *module* against a pinned, replayable harness.
- No temporal-validity leg, no token-budget leg, no production baseline, no revenue attribution.

**Vitals (2026-07-02, taoflute + taostats):** no website, no repo, no X, Discord never seen (999d);
30d avg code lines **2.3**; reserve ~**1,951 TAO**; taostats emission share ~0.47%; alpha price
**0.00468 TAO, +9.1% 30d** — the *only* narrative-squat in this scan that is *up* on the month while
the rest of the cohort bleeds market beta (−10% to −23%). A price bid with zero shipped artifacts is
exactly the "narrative wakes up cheaply" risk flagged below; keep it on the watch-list. Event history: netuid
re-registered 2025-12-25 (previously CANDLES), coldkey changed 2026-03-20, renamed naschain → Halftime →
**Recall (2026-05-24)** → **rec4ll (2026-06-11)**. Four renames in six months on a recycled netuid with
zero public artifacts = narrative-squat, or at best a pre-launch team with nothing shipped.

**So what:** not a competitor today, but two live risks — (a) the **name is contested** on-chain, and
off-chain by recall.network (unrelated crypto agent-memory project): run a naming pass before anything
public; (b) the owner can wake the narrative up cheaply: re-run this scan before ratifying D1.

## 3. Adjacent live subnets — one-leg overlaps

| Subnet | Reserve / activity (2026-07-02) | Overlapping leg | Why it is not PoR |
|---|---|---|---|
| **SN118 Ditto** ([heyditto.ai](https://heyditto.ai)) | ~8.6k TAO in; Discord+X active | ⚠ **Closest live neighbour — reclassified, see §8.** DittoBench scores *memory-retrieval quality* directly | **Not "just a product workspace."** DittoBench ([dittobench-starter-kit](https://github.com/ditto-assistant/dittobench-starter-kit)) is a submit-code, validator-executed competition that rebuilds miner containers and scores memory-retrieval quality + tool-calling + latency via an LLM judge on a rotating held-out set. Still not PoR: no temporal-validity leg, no token-budget leg, no *private-tenant* inversion (its data is a seeded benchmark, not a customer corpus), no production-consumption/revenue attribution. |
| **SN114 SOMA** ([thesoma.ai](https://thesoma.ai)) | ~3.8k TAO; active dev (~432 lines/30d) | *Token efficiency*: MCP-task competition featuring context compression | **Mechanism is closer than "sells tools":** SOMA is submit-code (validator-executed) — miners submit code solving a rotating MCP task, scored on solution quality (see §8). Still no recall/temporal/groundedness composite; efficiency is one axis, not the scored competition leg |
| **SN22 Desearch** ([desearch.ai](https://desearch.ai)) | ~8.4k TAO; heavy dev (~528 lines/30d) | *Search for AI agents* | Public web/social data only — the opposite corpus. No private-tenant story, no assembly scoring |
| **SN67 Harnyx** ([harnyx.ai](https://harnyx.ai)) | ~3.0k TAO; very heavy dev (~1,440 lines/30d) | *Retrieval + ranking as internal stages* of a deep-research swarm | Scores the end report, not the retrieval seam; miners are research agents, not assembly modules |
| **SN24 Quasar** | — | Attacks the same user pain (context) | From the *model* side: long-context architectures. Complementary, not competitive — a world with cheap 10M-token models shrinks (but doesn't kill) the assembly-quality premium; PoR's efficiency leg is the hedge |
| **SN116 "Memo"** | ~2.2k TAO; zero code; no identity | *Name only* | Renamed from "hard_sign" 2026-06-15; no site/repo/social. Second apparent squat on the memory narrative — watch-list |

**Pattern:** each neighbour holds one leg (memory narrative, token efficiency, search, retrieval-as-stage,
long context). Nobody holds the composite, and none of them *can* serve the private-corpus case without
rebuilding their topology.

## 4. Mechanism precedents — same machinery, different commodity

These don't contest the proposition; they prove the design assumptions have already survived contact with
real miners:

- **SN14 Cacheon** ([cacheon.ai](https://cacheon.ai)) — miners submit **containerized inference servers**
  scored on speed + correctness vs a **vllm baseline**. Mechanically the closest thing on the chain to PoR:
  sandboxed executable submissions, hard latency gate, beat-the-baseline margin. Validates that miners will
  compete on exactly this shape of game.
- **SN62 Ridges** ([ridges.ai](https://www.ridges.ai)) — SWE agents as code submissions, validator-executed
  on benchmarks. Largest live code-mining community; a design-partner candidate for L5(c).
- **SN15 ORO** — Python shopping agents evaluated on a fixed benchmark of tasks. Same submit-code shape.
- **SN1 Apex** (Macrocosmos) and **SN100 BASE** — hosted **competition platforms** ("launch open or private
  competitions around measurable objectives" / multi-challenge routing under one validator network). A
  possible *launch-without-a-netuid* path: run PoR round 1 as a hosted competition to price the market and
  battle-test the harness before paying for a netuid. Worth a design conversation before Phase 2.

**Cautionary precedent — the old SN40 "Chunking" (VectorChat) is dead** (netuid recycled to Ralph, a
training-recipes subnet). The one prior pure-RAG-component subnet didn't survive. Read: a single scored
component (chunking alone) is too thin a game; PoR's composite (recall + temporal + groundedness +
efficiency vs a *revenue-attributed production baseline*) is materially thicker than what Chunking or
rec4ll ever specced. Keep it thick.

## 5. Whitespace — what nobody on the chain does

1. **Inverted evaluation over private corpora** — every retrieval-ish subnet routes data out to miners;
   none brings code to the data. This is PoR's structural moat *and* its L6 verification burden.
2. **Temporal-validity scoring** — no subnet benchmarks "surfaces the currently-valid fact." Stack D makes
   it nearly free for us; it is genuinely novel on the chain.
3. **Recall@token-budget** — efficiency exists as a product feature (SOMA) but nowhere as a scored,
   descending-budget competition leg.
4. **Revenue-legible consumption** — `oracle_query` metering ("this module served N real queries") beats
   every neighbour's demand story; only Cacheon's baseline-beat comes close in consumption discipline.

## 6. Strategic read

- **Clear field, contested name.** Ratifying D1 does not run into an incumbent — but "Recall" is taken
  twice over (SN31 on-chain, recall.network off-chain). Naming pass before any public artifact.
- **The threat model is a wake-up, not an incumbent.** SN31's owner (or any competition platform) could
  occupy the narrative in weeks. Our defense is the part they can't copy: a production platform that
  consumes the winner and the tenant corpora that make the game real. Speed on Phase 0 matters more than
  secrecy.
- **Cacheon is the design comp; Ridges is the partner comp; Apex/BASE are the cheap-launch comp.** Steal
  Cacheon's baseline-beat discipline, talk to Ridges about validator ops (L5), and price the hosted-
  competition route before committing to a netuid (L8).
- **Chunking's death is the scoping lesson:** never let the game collapse to one component. The composite
  and the production-consumption story are what make PoR a subnet rather than a benchmark.

## 7. Reproduce / refresh this scan

One read-only query against taoflute's open Grafana proxy (client: `movers_attribution.tf_query` in the
sn21-monitor repo):

```sql
select sn_id, subnet_name, subnet_url, repo_url, twitter, summary, description,
       tao_in, dereg_place, last_discord_msg_days, avg_code_lines_30d, registered_on
from materialized_overview_data order by sn_id::int
```

Keyword-sweep `summary`+`description` for `retriev|rag|memory|context|recall|search|index|embed|chunk|
knowledge|semantic|vector|graph`, then eyeball the full name list for narrative squats (this pass caught
Cacheon and Memo, which the keywords missed). Check renames/re-registrations via
`materialized_news (subnet_id, key in ('name_change','registrations','coldkey_change'))` — the rec4ll story
was only visible there. Cross-check vitals on [taostats.io/subnets/&lt;id&gt;](https://taostats.io/subnets).
taoflute is an accidental open proxy and may lock down — degrade to taostats API if it does.

**Watch-list for the re-run:** SN31 rec4ll (any repo/site/X appearing = act), SN116 Memo (same), SN114 SOMA
(context compression scope creep toward assembly), SN118 Ditto (memory narrative), new registrations
matching the keyword set.

## 8. Mining/validation mechanics + alpha-price scan (added 2026-07-02)

_Method: located each competitor's GitHub repo via taoflute (`repo_url` in `materialized_overview_data`),
read the README + validator/miner docs for the incentive mechanism, and captured current alpha price +
30d trend (`price`, `month_price_change_perc`). Prices are alpha-in-TAO; the whole cohort except three
names sits in a **−10% to −23% / 30d** band, which reads as chain-wide alpha beta (a market drawdown),
not subnet-specific weakness — so *relative* trend matters more than the absolute minus sign._

### 8.1 Vitals table

| SN | Name | Alpha price (TAO) | 30d trend | Reserve (TAO in) | Repo | Mining/validation model |
|---|---|---|---|---|---|---|
| 1 | Apex (Macrocosmos) | 0.008662 | −10.7% | ~26,180 | [macrocosm-os/apex](https://github.com/macrocosm-os/apex) | Submit-code, validator-executed, winner-takes-all competition host |
| 14 | Cacheon | 0.010745 | −13.0% | ~26,875 | [latent-to/cacheon](https://github.com/latent-to/cacheon) | Submit **container image**, validator-hosted, latency-beats-vLLM-baseline |
| 15 | ORO | 0.028193 | −10.7% | ~9,063 | [ORO-AI/oro](https://github.com/ORO-AI/oro) | Submit-code shopping agents, Docker-sandboxed, ShoppingBench scoring |
| 22 | Desearch | 0.003863 | −13.8% | ~8,440 | [datura-ai/desearch](https://github.com/datura-ai/desearch) | **Serve-a-service**: miners host search axons, validators verify + LLM-judge |
| 24 | Quasar | 0.009155 | −10.0% | ~12,779 | [SILX-LABS/QUASAR-SUBNET](https://github.com/SILX-LABS/QUASAR-SUBNET) | **Serve-a-service**: distributed training, signed fragment claims, merge-ledger scoring |
| 31 | rec4ll | 0.004684 | **+9.1%** | ~1,951 | _none_ | Dormant narrative-squat — no repo, 2.3 code lines/30d |
| 40 | Ralph (ex-Chunking) | 0.038465 | **+1050%** | ~4,006 | [RalphLabsAI/ralph](https://github.com/RalphLabsAI/ralph) | Submit-code training-recipe diffs, attested + hidden-eval ladder (**not RAG**) |
| 62 | Ridges | 0.012342 | −23.3% | ~31,451 | [ridgesai/ridges](https://github.com/ridgesai/ridges) | Submit-code SWE agents (`agent.py`), validator-executed on Harbor tasks |
| 67 | Harnyx | 0.010652 | +2.3% | ~3,005 | [harnyx/harnyx](https://github.com/harnyx/harnyx) | Submit-code research agents, sandboxed, LLM-judge vs reference answer |
| 100 | BASE | 0.008299 | −21.1% | ~3,497 | [BaseIntelligence/base](https://github.com/BaseIntelligence/base) | Validator-executed multi-challenge orchestration platform |
| 114 | SOMA | 0.011204 | −20.4% | ~3,802 | [DendriteHQ/SOMA](https://github.com/DendriteHQ/SOMA) | Submit-code MCP-task competition, sandbox-executed, layered-weight scoring |
| 116 | Memo | 0.014279 | −10.4% | ~2,218 | _none_ | Dormant squat — no repo, 0 code lines/30d |
| 118 | Ditto | 0.018899 | −6.1% | ~8,616 | [dittobench-starter-kit](https://github.com/ditto-assistant/dittobench-starter-kit) | **Submit-code, validator-rebuilt container; scores memory-retrieval quality** |

### 8.2 Mining/validation summaries

**Mechanism precedents (submit-code, validator-executed — the shape PoR uses):**

- **SN14 Cacheon** — Miners build and submit a containerized inference server (Docker image ≤20 GB, weights
  mounted at runtime) serving `Qwen2.5-72B-Instruct` over an OpenAI-compatible endpoint. Validators pull the
  image, run it on standardized 8-GPU pods, and score end-to-end latency improvement over a **vLLM baseline**,
  gated by a correctness check (fail = zero). Winner-take-most (80/20 split); a challenger must beat the
  incumbent's fresh score by a **fixed 1% margin**. Closest mechanical comp to PoR: sandboxed executable,
  hard latency gate, beat-the-baseline discipline.
- **SN62 Ridges** — Miners submit a SWE agent as a single `agent.py` (`agent_main(input) -> str`) via
  `ridges upload`. Validators execute the code against standardized "Harbor" benchmark tasks; the single
  highest-scoring agent earns emissions. Largest live code-mining community → the L5(c) validator-ops
  partner comp.
- **SN15 ORO** — Miners submit Python shopping agents (`agent_main()` + provided product tools) scored in an
  isolated Docker sandbox against "ShoppingBench" on accuracy / format compliance / field matching. Emissions
  proportional to validator stake; a **decaying score threshold** enforces a challenge margin (anti-churn).
- **SN1 Apex** — General competition host: each competition = task + dataset/environment + scoring function
  `f(x)→ℝ`. Solvers submit via CLI, validators run every submission in an isolated sandbox on identical terms,
  winner-takes-all leaderboard rewards that shift on-chain as ranks change. _(Repo now describes a generic
  competition platform, not the older LLM-inference framing.)_ → the cheap "launch-without-a-netuid" comp.
- **SN100 BASE** — Multi-challenge orchestration: validators are decentralized executors that pull assignments,
  run evaluation in their own Docker, route external LLM calls through a master gateway (validators hold no
  provider keys), and report results; a submitter service posts normalized weights on-chain. "No path produces
  weights without validator evaluation." → the other cheap-launch comp.

**Adjacent live subnets:**

- **SN118 Ditto / DittoBench — the reclassification.** Contrary to the §3 "product workspace" read, DittoBench
  is a **submit-code, validator-executed competition**. Miners edit a Rust baseline (model choice, system
  prompts, memory-retrieval tuning, tool impls), package the buildable crate + Dockerfile + fixtures into a
  `.tgz`, and upload it (paying an eval fee). The validator **rebuilds the container in Docker** (won't
  compile → rejected), runs it against a **fresh per-submission rotating seeded dataset** (anti-overfit), and
  scores three dimensions via an **LLM judge**: tool-calling accuracy, **memory-retrieval quality**, and
  latency. This is the closest live analogue to PoR's game — code-to-validator, held-out set, quality+latency
  scoring. It is *still not PoR*: no temporal-validity leg, no descending token-budget leg, no private-tenant
  inversion (the corpus is a seeded benchmark, not a customer's private data), no production-consumption /
  revenue attribution. **Bumped to top of the watch-list.**
- **SN114 SOMA** — Also submit-code, not "sells tools." Miners submit a Python solution (`main()` + OpenRouter
  keys) to a rotating MCP task; two-week cycles run submission → automated screening → live competition, with
  code executed in a `sandbox_service/` sandbox. Validators score solution quality against the task; rewards
  use a hierarchical layered weighting (`W(Lᵢ)=1/2ⁱ`, split across elements and tied winners). Winning
  solutions become MCP servers. Closer to PoR mechanically than credited, but no recall/temporal/groundedness
  composite.
- **SN22 Desearch** — **Serve-a-service.** Miners run live Bittensor axons answering AI / X / web-search
  synapses. Validators issue synthetic + organic queries, verify returned results against independent
  providers, and score via multi-source content-relevance scorers + a performance component + an LLM judge
  (default `gpt-4.1-nano`). Data routes *out* to miners — the opposite corpus topology to PoR.
- **SN67 Harnyx** — Submit-code deep-research. Miners submit Python agents (`query` entrypoint,
  `{"text":…}`→`{"text":…}`) competing under a tight tool budget. Validators execute each in a sandbox and
  score `comparison_score` = pairwise LLM judge vs a stronger reference answer (run twice with swapped order
  for position bias; ties favour lower tool cost). Champion emission (incumbent, replaced only on a margin or
  efficiency win) + tiered participant emission (top 10% → 2×, top 50% → 1×, else 0). Scores the end report,
  not the retrieval seam.
- **SN24 Quasar** — **Serve-a-service** distributed model training. An orchestrator leases each miner a model
  fragment (tensor portion); miners train continuously and upload cryptographically signed "live fragment
  claims." Validators verify signatures / tensor contracts / hashes / GPU proofs / checkpoint lineage, run an
  independent eval against the frozen prior state, and emit a signed verdict; only validator-approved fragments
  are merged into a "live merge ledger." Scoring counts only merge-accepted work under a recency-decay window
  (~1800s); self-reported speed/loss/GPU are ignored. Long-context / model-side, not assembly-side.

**Cautionary precedent — netuid 40 status confirmed.** The dead SN40 "Chunking" (VectorChat) netuid is now
**Ralph** (RalphLabs) — a **model-pretraining-recipe** subnet, and the scan's standout mover at
**0.038 TAO, +1050% / 30d** with ~1,900 code-lines/30d (relaunched ~2026-06, repo + site stamped 2026-07-01).
Miners submit **code patches** (LR schedules, initializations, data-mix changes) as PRs to a canonical recipe
plus a proof bundle; validation runs diff-scan → NVIDIA-Confidential-Computing hardware attestation → training-
log plausibility → **hidden multi-scale eval ladder** (up to ~124M params, public CORE-22 + a held-out
private-hard slice) before merging. **It has nothing to do with RAG / retrieval / memory / context** — the
Chunking territory is vacant, and the netuid's revival into an unrelated, thriving subnet reinforces the
scoping lesson: a single thin component (chunking alone) didn't survive, but the submit-code-validator-executed
*machinery* is clearly thriving on the chain.

### 8.3 Strategic read — miner labour market, product positioning, IM imports

**Frame correction.** PoR is *not* a standalone product — it is the supply mechanism that feeds RedOS's
`ContextAssembler` (`BITTENSOR_SUBNET_DESIGN_PROOF_OF_RECALL.md`). So the subnets in this doc contest us on
**two surfaces only**: (i) *proposition-adjacency* (the §0–§6 analysis — does anyone occupy the composite),
and (ii) the **miner labour market** — the skills are shared and portable, so we compete for the same builders.
They do **not** compete in our *product* market. A subnet is an open, commodity miner/validator competition;
it cannot sell a sovereign, governed, per-tenant business OS delivered by a certified human network. Our
product challengers live entirely in the companion `RedFirst_Competitive_Landscape_2026-07.md` (Microsoft
Copilot, Relevance/Lindy/Stack AI, GoHighLevel, the consultancies) — the same "Tier 3 is tech-watch, not a
challenger" logic that doc already applies to Ditto and Sundae_bar.

**(A) Where our best-fit miners already are.** PoR's ideal miner writes a *code module* that is rebuilt and
run sandboxed against a pinned harness, and optimises retrieval quality under latency + token-budget gates.
Ranked by how directly today's skill transfers:

| Pool | Miner skill today | Transfer to PoR | Poach priority |
|---|---|---|---|
| **SN118 Ditto** | Tunes memory-retrieval + tool-calling + latency in a Dockerised submission, scored on a held-out set by an LLM judge | **Near-identical** — same submission shape, same three scored axes, same anti-overfit discipline | **Highest — direct** |
| **SN67 Harnyx** | Submit-code research agents optimising retrieval + ranking under a **tool budget**, judged vs a reference answer | Tool-budget → our **token-budget leg**; LLM-judge-vs-reference maps to groundedness scoring | **High — direct** |
| **SN62 Ridges** | Writes agents to a fixed `agent.py` contract; **largest code-mining community on the chain** | Domain (SWE) differs, but the submit-to-contract + local-replay muscle is exactly ours; best *volume* pool | **High — for depth of field** |
| **SN14 Cacheon** | Submits containerised servers, tuned to **beat a baseline on latency behind a correctness gate** | Engineering shape is our exact shape (sandbox + latency gate + beat-baseline margin); retrieval domain is new to them | **Medium — engineering talent** |
| **SN114 SOMA / SN15 ORO** | Sandboxed submit-code; SOMA on **token/context efficiency**, ORO on multi-dim benchmark accuracy | Efficiency-optimisation and Docker-sandbox fluency transfer; domain is adjacent | **Medium** |
| **SN22 Desearch** | Retrieval/search *domain* experts — but operate live **axons**, not code submissions | Domain knowledge is gold; would need to re-tool from serve-a-service to submit-code | **Low — retrain required** |
| **SN24 Quasar / SN40 Ralph** | Distributed-training / ML-pretraining researchers | Wrong domain and mechanics | **Not a target** |
| **SN1 Apex / SN100 BASE** | Heterogeneous general competition solvers | No targeted pool — but a **cheap launch path** (run PoR round 1 as a hosted competition, L8) | **Not a pool; a channel** |

*Recruitment wedge:* every subnet above is an **emission-only** game. PoR uniquely ships the winning module
into production with `oracle_query` metering — the miner gets real usage signal and a revenue-attribution
story, not just alpha emissions. That is the pitch to pull top builders off Ditto/Harnyx/Ridges: *"your module
earns from real customer queries, not just from the emission curve."*

**(B) Product-market positioning (unchanged by this scan).** Nothing here moves our product line. Against the
subnets we are not selling into the same market at all; against the *real* product field we remain differentiated
by the bundle (sovereign governed OS + certified human delivery + audit-first entry). PoR's role in that story
is a **defensibility multiplier**, not a product: it is the part a Copilot or a Relevance can't cheaply copy,
because it is fed by tenant corpora and consumed by a production assembler — the moat the business doc says we
must weld shut before Microsoft commoditises the OS layer.

**(C) IM structures worth importing** (leaving the §8.2 mechanics as-documented; these are candidate imports
into PoR's own incentive mechanism):

| Import | Source | What it buys PoR |
|---|---|---|
| **Rotating per-submission held-out corpus slices** | Ditto (rotating seeded set) + Ralph (public + private-hard split) | The single most important import. Our harness is *pinned and replayable* — great for reproducibility, dangerous for overfitting. Rotate held-out needle/corpus slices per submission so a module must generalise, not memorise the harness |
| **Correctness gate before efficiency scoring** (fail = 0) + **fixed beat-the-incumbent margin** | Cacheon (correctness gate, 1% margin) | Don't score token-efficiency on a module that fails recall/groundedness; require a defined margin over the live baseline to flip the leader (anti-churn) |
| **Decaying score threshold** | ORO | Complements the fixed margin — challengers need a *meaningful* improvement early, easing over time, so the top slot doesn't thrash |
| **Position-bias-controlled LLM judging + efficiency tie-break** | Harnyx (dual-order judge, ties → lower tool cost) | Our groundedness leg leans on an LLM judge; run it dual-order to kill position bias, and break ties toward the token-budget leg (reinforces the efficiency incentive for free) |
| **Champion + tiered participant emission** (top 10% → 2×, top 50% → 1×) | Harnyx | Keeps a *deep field* of miners engaged rather than a winner-take-all cliff — matters for recruiting against established pools |
| **Difficulty-tiered / layered weighting** (`W(Lᵢ)=1/2ⁱ`) + **screening phase** | SOMA | Reward across easy→hard needle tiers (not just top-line), and pre-screen junk submissions before the expensive graded eval |
| **Centralised judge-model gateway** (validators hold no provider keys) | BASE | Consistent, cost-controlled, key-safe LLM-judge scoring across validators — directly relevant since our composite uses judged legs |
| **Ignore all miner self-reported metrics; only validator-measured results count** + attestation | Quasar, Ralph | If PoR ever executes miner code near tenant data (the L6 inversion), hardware attestation + zero-trust of self-reported stats is the precedent to copy |

**Trend footnote (not a threat signal):** the cohort's −10% to −23% / 30d is chain-wide alpha beta; the only
bid-ups are rec4ll (+9%, artifact-free = narrative pump) and Ralph (+1050%, a genuine relaunch). Neither
contests PoR — but rec4ll's pump-on-nothing confirms how cheaply the "Recall" narrative can be re-lit.
