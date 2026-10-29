# CS239 Project: Financial Advisor (multi-agent purchase advisor)

Three Rakazo bots decide whether, and when, the user can afford an item, and pay bills on the
user's confirmed request:

- **Financial Advisor** talks to the user, looks up the item price, does the math, and keeps the wishlist.
- **Payment Manager** knows the user's bills (rent, loans, debts, utilities, subscriptions, insurance)
  and pays one when the user confirms, by asking the Bank Agent to debit an account.
- **Bank Agent** knows the accounts, savings goals, interest and scheduled paychecks, and is the only
  agent that can take money out of an account.

```
 User ──► Financial Advisor ──message_bot──► Payment Manager   (fee totals per scope)
              │   ▲          ──message_bot──► Bank Agent        (projected totals, threshold check)
 User ──► Payment Manager ───message_bot──► Bank Agent          (debit to pay a confirmed bill)

   MCP :8771 wishlist/products   MCP :8772 bills        MCP :8773 accounts/deposits/ledger
```

Each bot is assigned **only its own MCP server**, so it can read only its own data. The app follows
the CS239 tutorial's pattern (`examples/movie_night`): MCP tool servers, Rakazo bot profiles and `message_bot`.

| Document | What it covers |
|---|---|
| [description/app.md](description/app.md) | Purpose and supported tasks |
| [policies.md](policies.md) | The 16 policies (P1–P16) and which ones the code enforces |
| [description/tools.md](description/tools.md) | Every tool's inputs and outputs |
| [description/agents/](description/agents/) | Each agent's tools and exact system prompt |
| [description/episodes/](description/episodes/) | Example episodes, real and hypothetical |
| [requirements.md](requirements.md) | Detailed requirements (FR-*, AC-*, IB-*, PR-*, LC-*) |
| [traces/README.md](traces/README.md) | Recorded traces and scenarios |
| [tests/README.md](tests/README.md) | Test cases |

## Layout

| Path | What |
|---|---|
| `phase1/advisor_server.py`, `payments_server.py`, `bank_server.py` | One MCP server per agent (the tools) |
| `phase1/app.py` | Bot profiles (system prompts and policies), scenarios, `--apply` / `--send` / `--confirm` |
| `phase1/run_servers.py` | Starts all three MCP servers |
| `phase1/export_traces.py` | Saves a scenario's trace (Rakazo conversations and tool-call log) |
| `phase1/check_tools.py` | Walks the workflows through the MCP servers with no LLM |
| `phase1/describe.py` | Regenerates `description/agents/*.md` from `app.py` |
| `phase1/rakazo.py` | The tutorial's Rakazo API helper, with small additions |
| `data/` | Fictional data: `wishlist.json` (empty), `payments.json` (20 unpaid bills), `accounts.json` (2 checking, 3 savings), `transactions.json` (empty ledger), `deposits.json`, `products.json` |
| `data/seed/` | Starting copies of the files agents can change, restored by `run_servers --reset` |
| `tests/` | Unit tests (no LLM needed) |
| `make_submission.py` | Builds the two submission archives |

In the submission archive, the code is in `src/` and the tests are in `tests/` next to it. Run the
app commands from `src/`, and the tests from the archive root.

## External requirements

| Requirement | Why |
|---|---|
| Python 3.13+ | Runs the MCP servers and scripts (`requirements.txt`: mcp, a2a-sdk, httpx, uvicorn, pydantic, starlette) |
| Docker Desktop (or Docker Engine + Compose) | Runs Rakazo/grokbot locally |
| Rakazo/grokbot, installed with the CS239 tutorial's `setup-rakazo.sh` | Hosts the three bots and `message_bot` (see the setup notes below) |
| A tool-capable LLM | We used **Claude Opus 5.5** through a Claude Pro/Max sign-in in Rakazo. An OpenAI-compatible API key also works |

| Environment variable | Needed for | Example |
|---|---|---|
| `RAKAZO_URL` | All Rakazo commands | `http://127.0.0.1:5173` |
| `RAKAZO_EMAIL` | All Rakazo commands | your Rakazo account email |
| `RAKAZO_PASSWORD` | Optional; otherwise you're prompted, and only when the saved session expired | — |
| `MCP_HOST` | `--apply` | `host.docker.internal` (how Rakazo's containers reach the MCP servers) |
| `MODEL_PROVIDER`, `MODEL_ID` | `--apply` with a Claude sign-in | `anthropic`, `claude-opus-5-5` |
| `MODEL_BASE_URL`, `MODEL_ID`, `MODEL_API_KEY` | `--apply` with an OpenAI-compatible key | `https://api.openai.com/v1`, `gpt-4.1`, your key |
| `FINANCE_AS_OF` | Optional demo date (default `2026-10-24`); set it in both terminals | `2026-10-24` |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
                                   # (if blocked: Set-ExecutionPolicy -Scope Process Bypass)
python -m pip install -r requirements.txt
python -m unittest discover tests -v    # 29 tests, no LLM needed
python -m phase1.check_tools            # walks the workflows through the MCP servers
```

### Rakazo setup notes (one time)

Install Rakazo from the **tutorial** folder with `bash setup-rakazo.sh` (in WSL on Windows). Then open
http://localhost:5173, create an account, connect a model, and set English in the language settings. Two
problems with the current upstream `edge` images need fixing:

1. **`setup-rakazo.sh` stops with "Unexpected upstream Compose layout; startup refused."** Its patch
   looks for `"  api:\n"`, which also matches the more deeply indented `api:` lines under `depends_on`.
   Add the same `extra_hosts` entry by hand, under the top-level `api:` and `worker:` services in
   `.rakazo-runtime/docker-compose.images.yml`:

   ```yaml
       extra_hosts:
         - "host.docker.internal:host-gateway"
   ```

   Then finish the install from `.rakazo-runtime/`:

   ```bash
   COMPOSE_PROJECT_NAME=cs239-tutorial-rakazo RAKAZO_API_PORT=23100 bash install-images.sh --local
   ```

2. **`--apply` fails at `mcp/servers/create` (HTTP 400)** because Rakazo refuses `http://` and private
   MCP endpoints such as `host.docker.internal`. In `.rakazo-runtime/.env`, uncomment
   `MCP_ALLOW_PRIVATE_ENDPOINT=true`, then recreate the two containers:

   ```bash
   COMPOSE_PROJECT_NAME=cs239-tutorial-rakazo RAKAZO_API_PORT=23100 \
     docker compose --env-file .env -f docker-compose.images.yml up -d --no-deps --force-recreate api worker
   ```

   This is safe here because Rakazo listens only on `127.0.0.1` and the data is fictional. Leave it unset on public installs.

To connect Claude with a Pro/Max subscription: in Rakazo's model settings, choose "Sign in with
Claude Pro/Max". After signing in, the browser shows a "can't connect" page at `localhost:53692/callback?...`.
That's expected: paste that whole URL into Rakazo's "Authorization code or callback URL" box.

After the first install, just start Docker Desktop. The containers restart on their own.

## Run

1. Start the three MCP servers and leave them running (Terminal 1):

   ```bash
   python -m phase1.run_servers --reset
   ```

2. In Terminal 2, set the environment variables. For example, with a Claude sign-in in PowerShell:

   ```powershell
   $env:RAKAZO_URL = "http://127.0.0.1:5173"
   $env:RAKAZO_EMAIL = "YOUR_ACCOUNT_EMAIL"
   $env:MODEL_PROVIDER = "anthropic"
   $env:MODEL_ID = "claude-opus-5-5"
   $env:MCP_HOST = "host.docker.internal"
   ```

   With bash and an OpenAI-compatible key, use `export RAKAZO_URL=...` and so on, with
   `MODEL_BASE_URL`, `MODEL_ID` and `MODEL_API_KEY` instead of `MODEL_PROVIDER`.

3. Preview the bots' prompts, then create the bots, or update them after a prompt change. Re-running is safe:

   ```bash
   python -m phase1.app
   python -m phase1.app --apply
   ```

4. Run a scenario, wait for the final answer in the receiving bot's chat in Rakazo, then export its trace:

   ```bash
   python -m phase1.app --send console --fresh
   python -m phase1.export_traces console
   ```

   `--fresh` first deletes the three bots' chat history, so a run can't reuse an earlier one's answers.
   It lists runs you haven't exported and asks you to type `yes`. Export each trace before the next
   send, and don't type in the bots' chats during a run.

5. To save **everything** currently in the three chats, including messages you typed in Rakazo's UI
   (for example during a live demo), export the whole session:

   ```bash
   python -m phase1.export_traces --session            # traces/session_<date>-<time>/
   python -m phase1.export_traces --session demo_dec3  # or pick the folder name
   ```

   It covers every message since the chats were last cleared with `--fresh`, plus the tool calls from
   that time on. Export before the next `--fresh`, because clearing deletes the chats in Rakazo.

### Example usage

```bash
python -m phase1.app --send console --fresh      # Financial Advisor: "Can I buy this gaming console? <link>"
# ...expected answer: "wait about a week" (traces/console/trace.md)
python -m phase1.export_traces console

python -m phase1.app --send pay_bill --fresh     # Payment Manager: "Please pay my debt bill that is due today..."
# ...Payment Manager asks you to confirm P01, $650.00, Sunset Federal Bank checking
python -m phase1.app --confirm pay_bill          # sends "Yes, I confirm. Please go ahead with that payment."
# ...expected answer: "P01 is paid, confirmation TX-0001"
python -m phase1.export_traces pay_bill
```

| Scenario | Sent to | What it shows |
|---|---|---|
| `console`, `headphones`, `gaming_pc` | Financial Advisor | The three purchase outcomes (wait a week / buy today / not now and add to wishlist) |
| `wishlist` | Financial Advisor | Wishlist reminder (run after `gaming_pc`) |
| `pay_bill` | Payment Manager | Confirmed bill payment through the Bank Agent (needs `--confirm`) |
| `pay_refused` | Payment Manager | Payment refused: it would take savings below the goal (needs `--confirm`) |
| `boundary_probe`, `pay_probe` | Financial Advisor | Probes of the prompt-only policies (Phase 2 baselines) |

## Submission archives

```bash
python make_submission.py --name <name> --uid <uid>
```

This regenerates the agent files, runs the tests, and writes `dist/<name>-financial-advisor-<uid>-requirements.tar.gz`
and `dist/<name>-financial-advisor-<uid>-whole.tar.gz`. The second archive ships the starting data.

## Notes

- The data uses a fixed demo date, 2026-10-24, so every run gives the same answers, and each bot is
  told this is "today". To move the clock, set `FINANCE_AS_OF` in both terminals and re-run `--apply`.
- Payments change only the fictional JSON files. `run_servers --reset` restores them from `data/seed/`.
- The scripts save your Rakazo login session in `~/.cs239-financial-advisor/rakazo-session.json`
  (outside this repo) and ask for the password only when it expires. Rakazo allows just 10 sign-ins
  per 15 minutes. Delete that file to log out.
- Product links resolve against a fictional catalog (`data/products.json`). Unknown links make the advisor ask for the price.
- The MCP servers bind to `0.0.0.0` (as in the tutorial) so the Docker containers can reach them.
- Phase 1 enforces tool access (P1), debit refusals (P12), single payment (P13) and logging (P16) in
  code. The other policies are prompt instructions only (see `policies.md`). Phase 2 enforces them.
