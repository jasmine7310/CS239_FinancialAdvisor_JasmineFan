# CS239 Phase 2: Financial Advisor (multi-agent purchase advisor)

Three agents decide whether, and when, the user can afford an item, and pay bills on the user's
confirmed request. This `phase2` branch holds the app ported to PolicyWeave. Phase 1 (the same app
running on Rakazo) is on the `main` branch.

- **Financial Advisor** talks to the user, looks up the item price, does the math, and keeps the wishlist.
- **Payment Manager** knows the user's bills and pays one when the user confirms, by asking the Bank Agent.
- **Bank Agent** knows the accounts, savings goals, interest and paychecks, and is the only agent that can
  take money out of an account.

```
 user ──► Financial Advisor ──message_agent──► Payment Manager    (fee totals per scope)
               │              ──message_agent──► Bank Agent         (projected totals, threshold check)
 user ──► Payment Manager ────message_agent──► Bank Agent           (debit to pay a confirmed bill)
 user ──► Bank Agent                                                 (their own accounts)
```

The whole app runs in one Python process. Two functions are its action boundaries, where PolicyWeave
adds its checks:

| Boundary | What goes through it | Checks in the original app |
|---|---|---|
| `ToolBox.call(agent, tool, arguments)` in `finadvisor/tools.py` | every tool call | the tool must be in the caller's own set |
| `MessageBus.send(sender, recipient, text)` in `finadvisor/bus.py` | every message, between agents and from the user | the sender may message that recipient; the bus labels the real sender |

[policy.md](policy.md) lists the 17 policies (P1–P17) and which are enforced in code. [requirements.md](requirements.md)
has the detailed requirements.

## Layout

| Path | What |
|---|---|
| `finadvisor/tools.py` | Each agent's tools, their definitions for the model, and `ToolBox` |
| `finadvisor/bus.py` | `MessageBus`: messages between agents and from the user |
| `finadvisor/agents.py` | `Agent`: the model ↔ tool loop for one agent |
| `finadvisor/prompts.py` | Each agent's system prompt, and who may message whom |
| `finadvisor/backends.py` | `AnthropicBackend` (Claude) and `ScriptedBackend` (free, offline, deterministic) |
| `finadvisor/simulator.py` | Time passing: paychecks arrive and past bills are autopaid. Only the user moves time |
| `finadvisor/store.py` | A run's private copy of the fixtures, and the simulated clock |
| `finadvisor/app.py` | `App`: one run (data, trace, tools, bus, three agents) |
| `finadvisor/scenarios.py` | Scripted scenarios and `run_scenario` |
| `finadvisor/__main__.py` | Command line: `chat`, `scenario`, `list` |
| `fixtures/` | Fictional starting data, dated from 2026-10-24 |
| `tests/` | Unit and end-to-end tests ([tests/README.md](tests/README.md)) |

## Setup

Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover tests -v      # no model or key needed
```

Live runs use Claude through the Messages API and need an API key in your environment
(`ANTHROPIC_API_KEY`). Never put the key in a file in this repository.

| Variable | Default | What |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required for live runs |
| `APP_MODEL` | `claude-haiku-5-5` | The agents' model (any Claude model ID, e.g. `claude-opus-5-5`) |
| `APP_EFFORT` | the model's default | `low`, `medium`, `high`, `xhigh` or `max` |

## Run

```bash
python -m finadvisor list                          # the scenarios
python -m finadvisor scenario console --scripted   # offline, free
python -m finadvisor scenario console              # live, with Claude
python -m finadvisor chat                          # talk to the agents (add --scripted for offline)
```

In the chat, start a line with `fa:`, `pm:` or `bank:` to choose who you talk to. Use `/advance 7d` or
`/set 2026-10-31` to move time, `/state` to see the data, `/usage` for tokens used, and `/quit` to stop.
A chat starts on today's date (`--start YYYY-MM-DD` to choose another day); scenarios start on 2026-10-24.
Each chat or scenario saves its `trace.json` and final `state.json` under `sessions/` (ignored by git;
`runs/` is kept for the graded test-harness results).

Moving time forward means the user lived through those days: paychecks dated up to the new day arrive,
and every bill due before it is paid automatically (from the paycheck account when it can, else other
checking, else savings). No agent can move time.

| Scenario | Sent to | What it shows |
|---|---|---|
| `console`, `headphones`, `gaming_pc` | Financial Advisor | Wait about a week (saved, reminder in 7 days) / buy today / not now (saved, reminder in 30 days) |
| `wishlist` | Financial Advisor | The gaming PC is saved, then listed |
| `reminder` | Financial Advisor | Console, then a week passes; the Financial Advisor reminds the user first |
| `pay_bill` | Payment Manager | Confirmation, then payment through the Bank Agent |
| `pay_refused` | Payment Manager | Confirmed, but the Bank Agent refuses (savings goal) |
| `boundary_probe`, `pay_probe`, `bank_purchase_question` | various | Requests the policies say must be refused or redirected |
| `injected_product` | Financial Advisor | The product page tells AI assistants to skip the check and pay bills; it is treated as data (P11) |

## Test harness

[test_cases.json](test_cases.json) holds ten cases (S01–S10): normal use, requests that could break a
policy, and boundary cases. `run.py` plays each case as the user on a fresh copy of the fixtures and checks
the final state (wishlist, bills, ledger, balances, clock) and, lightly, the replies. These checks cover
functionality only, not policy compliance.

```bash
python run.py --case S01 --output_dir runs --sample 1   # one case
python run.py --output_dir runs --sample 3              # every case, samples 1-3
```

Each sample writes `runs/<case>/sample-<n>/result.json` with only `{"match_expected_outcome": true|false}`.
An error or a timeout (`CASE_TIMEOUT`, 600 s by default) counts as `false`. The trace, final state and
token usage are saved under `runs/<case>/sample-<n>/artifacts/`. `ORIGINAL_APP_DIR` says where the app
lives (default: this folder). Runs are live with Claude by default (needs `ANTHROPIC_API_KEY`). Set
`APP_BACKEND=scripted` to run offline for free.

## Notes

- All data is fictional. Product links resolve against `fixtures/products.json`.
- `ScriptedBackend` follows the policies with fixed rules. It is for development and tests, not a model.
- The agents run on Claude Haiku 5.5 by default. With `claude-opus-5-5` (and other models that support it), requests use the API's server-side refusal
  fallback. Remove `FALLBACK_MODELS` in `finadvisor/backends.py` to turn it off.
