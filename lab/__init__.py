"""
SN21 Emission/Mechanism Lab
===========================
Models proposed Bittensor emission-mechanism changes against SN21's real chain
state, reproduces today before predicting tomorrow, and logs every run.

See docs/Root_Reborn_SN21_Risk_Assessment_v0.9.md §4 for the spec this package
implements. Built inside sn21-monitor (not a separate repo) so it reuses the
live data layer, AMM model, scheduler, dashboard and Telegram channel.

Package layout
--------------
  chain_pull.py   §4.1 data layer — one all_subnets() call + TaoWeight + root stake
  amm.py          shared constant-product math (also used by root_reborn_model.py)
  mechanisms/     versioned, reviewed emission_share functions (incumbent + proposals)
  scenarios.py    S1..S5 — pure functions over a ChainState
  runner.py       pull state -> reproduction gate -> run scenarios -> append to log
  store.py        versioned results log (data/lab_runs.json)
  watcher.py      poll subtensor GitHub for new releases; notify + draft a stub
"""
