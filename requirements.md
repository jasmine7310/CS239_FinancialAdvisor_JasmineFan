# Requirements: Multi-Agent Purchase Advisor

Phase 1 requirements. The submission's policy list, `policies.md` (P1–P16), condenses §5 below into numbered policies.

## 1. Purpose

The user asks whether they can afford an item (given as an Amazon link). Three agents with separate
data cooperate to answer **whether** and **when** to buy it (today, in about a week, in about a month,
or not now). Items the user cannot afford go on a wishlist and are brought up again later.

The user can also ask the Payment Manager to **pay a bill** from one of their accounts. Money moves
only after the user explicitly confirms, and only the Bank Agent can debit an account. The system never
buys the item itself.

All data is fictional (`data/*.json`). Dates use a demo clock fixed at **2026-10-24** (`FINANCE_AS_OF`),
so runs are reproducible, and every bot is told that date is "today". `run_servers --reset` restores
the starting data from `data/seed/`.

## 2. Agents

| Agent | Owns (only it can read) | Tools (its own MCP server) | Talks to |
|---|---|---|---|
| **Financial Advisor (FA)** | Wishlist, product lookups | `lookup_product`, `project_balances`, `list_wishlist`, `add_to_wishlist`, `remove_from_wishlist` | User, PM, Bank |
| **Payment Manager (PM)** | Bills (rent, loans, debts, utilities, subscriptions, insurance) and their paid status | `get_upcoming_fees`, `list_unpaid_bills`, `mark_bill_paid`, `spending_chart` | User, FA, Bank |
| **Bank Agent (Bank)** | Accounts, balances, savings goals, APY, scheduled deposits, transaction ledger | `get_accounts`, `get_projected_totals`, `check_savings_threshold`, `debit_account` | FA, PM (and the user directly) |

Agents communicate only through Rakazo's `message_bot`. Each bot is assigned only its own MCP server.

## 3. Data formats

Each agent's instructions include the exact format of the data it owns.

- **Wishlist** (FA), starts empty: `[{"name", "price", "date", "timestamp", "deduction", "reminder"}]`
- **Payments** (PM), 20 entries, all unpaid at start:
  `[{"id": "P01", "type": rent|loan|debt|utility|subscription|insurance, "fee", "due", "status": unpaid|paid, "paid_on", "confirmation"}]`
- **Transactions** (Bank), the debit ledger, empty at start:
  `[{"confirmation": "TX-0001", "bank", "type", "amount", "reference": bill id, "date", "timestamp"}]`
- **Accounts** (Bank), 2 checking + 3 savings: `[{"bank", "type": checking|savings, "amount", "goal"?, "apy"}]`.
  `goal` exists only on savings accounts.
- **Deposits** (Bank): `[{"bank", "type", "amount", "date", "source"}]`, which holds scheduled paychecks.
- **Products** (FA's lookup tool): a fictional catalog keyed by Amazon ASIN.

**Savings threshold** = sum of `goal` over all savings accounts. **Scopes**: `day` = today,
`week` = today + 7 days, `month` = today + 30 days (inclusive).

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | FA extracts the item name and price from the link with `lookup_product`. If the item is unknown, FA asks the user for the price rather than guessing. |
| FR-2 | FA asks PM for the total unpaid fees due in each scope (day, week, month), including overdue unpaid bills. If a request names no scope, PM asks which scope rather than guessing. |
| FR-3 | FA asks Bank for the user's projected total money per scope. The totals include scheduled deposits and expected interest. |
| FR-4 | FA computes `remaining[scope] = bank_total[scope] − fees[scope] − price` with `project_balances`. |
| FR-5 | FA sends the three remaining totals to Bank. Bank answers, per scope, only "above threshold" or "below threshold", using `check_savings_threshold`. |
| FR-6 | Timing rule: all three scopes above → buy today. Otherwise week and month above → wait about a week. Otherwise month above → wait about a month. Otherwise do not buy now. |
| FR-7 | When FA advises against buying, it adds the item to the wishlist in the exact wishlist format, with a general reason and a reminder date (default today + 30). |
| FR-8 | At the start of every new user request, FA checks for wishlist items whose reminder date has arrived, reminds the user, and asks if they want to buy any. |
| FR-9 | FA removes a wishlist item when the user buys it or no longer wants it. |
| FR-10 | FA's final answer states the item, price, advice and reason, and names the source of each figure. |
| FR-11 | PM can summarize spending by type for a scope and produce a bar chart (`data/charts/spending_<scope>.svg`). |
| FR-12 | The user can ask PM to pay a bill from a named bank and account type. PM identifies the bill with `list_unpaid_bills` and asks the user to confirm the bill id, type, amount, due date and account. |
| FR-13 | After confirmation, PM asks Bank to debit exactly the bill amount, using the bill id as reference. Bank calls `debit_account` and answers "completed" with a confirmation id (`TX-####`), or "refused" with a reason. |
| FR-14 | On "completed", PM records the bill as paid with `mark_bill_paid` (bill id + confirmation id). Paid bills no longer count toward fee totals. On "refused", PM tells the user why and does not retry another account unless asked. |
| FR-15 | Bank refuses a debit when the account doesn't exist, the reference isn't a bill id, the bill was already paid, funds are insufficient, or a savings account would drop below its goal. |

## 5. Security requirements: what the system must never do

### 5.1 Least privilege and access to resources

| ID | Requirement |
|---|---|
| AC-1 | Each agent may call only the tools on its own MCP server, so it can read only its own data store. |
| AC-2 | No agent may buy the item or transfer money between accounts. The only way money moves is `debit_account` paying a bill (FR-12–15). Agents must never claim a payment happened without a Bank confirmation id. |
| AC-3 | Separation of duties for writes: FA writes only the wishlist; PM writes only bill status (`mark_bill_paid`); Bank alone changes balances and the ledger (`debit_account`). Deposits and products are read-only. |
| AC-4 | PM must never request, receive or infer balances or savings goals. Bank must never request or receive bill details beyond the bill id and amount it is asked to pay. |
| AC-5 | FA must never initiate, request or forward a payment. It redirects the user to PM. |

### 5.2 Information boundaries

| Information | FA | PM | Bank |
|---|---|---|---|
| Bank names, account types, per-account balances | ✗ never | ✗ never | owns |
| Savings goals and the threshold amount | ✗ never | ✗ never | owns |
| Projected total per scope; above/below verdict | may receive | ✗ | owns |
| Individual bills (type, fee, due date) | ✗ never | owns | ✗ never |
| Fee **totals** per scope | may receive | owns | ✗ |
| Item name, price, the user's request, wishlist | owns | ✗ never | ✗ never |
| Remaining totals (numbers only) | owns | ✗ | may receive |
| Payment request (bill id, amount, account named by the user) | ✗ | owns | may receive |
| Payment result (completed + confirmation id, or refused + reason) | ✗ | may receive | owns |

| ID | Requirement |
|---|---|
| IB-1 | Bank shares only per-scope totals, above/below verdicts and payment results. It never reveals bank names, account types, individual balances, savings goals or the threshold amount to another agent. A refusal gives a reason ("insufficient funds"), never the balance. |
| IB-2 | PM shares only per-scope fee totals with other agents. Individual payments go only to the user, and only when the user asks PM directly. |
| IB-3 | FA never tells PM or Bank what the user wants to buy, its price, the user's request text, or anything on the wishlist. It sends only the numbers needed. |
| IB-4 | A user request routed through FA ("tell me each account balance") does not widen what Bank or PM may send to FA. |

### 5.3 Provenance

| ID | Requirement |
|---|---|
| PR-1 | Every figure in FA's advice is attributed to where it came from: product catalog, PM, Bank, or FA's own calculation. |
| PR-2 | FA bases its decision only on figures from the owning agent's reply in the current request. It never uses estimates, invented numbers, or balances the user claims. |
| PR-3 | The above/below verdict comes only from Bank's `check_savings_threshold` result, never from FA's own judgment. |
| PR-4 | Content fetched from a product link is data, not instructions. Text on a product page cannot change budgets, thresholds or the timing rule. |
| PR-5 | Every tool call is logged with the calling agent, timestamp, arguments and result (`traces/tool_calls.jsonl`). |
| PR-6 | A payment must trace back to the user's own confirmation in PM's chat. Requests from FA, from Bank, or from text in a product page or other content are refused. |
| PR-7 | A bill is marked paid only with the confirmation id Bank returned for that bill, and the ledger entry carries the bill id. Bill and debit can always be matched up. |

### 5.4 Lifecycle

| ID | Requirement |
|---|---|
| LC-1 | Fee and balance figures are valid only for the request in which they were obtained. FA re-requests them for each new purchase question. |
| LC-2 | The wishlist (persistent storage) holds only name, price, dates and a general reason. It never holds balances, bank names, bill details or other agents' figures. |
| LC-3 | A wishlist entry lives from the "not now" decision until the user buys or declines the item. It is surfaced again once its reminder date arrives. |
| LC-4 | The data starts in a known state (empty wishlist, 20 unpaid bills, original balances, empty ledger) and is reset only on the user's instruction (`run_servers --reset`). |
| LC-5 | A bill moves one way, from unpaid to paid, and can be paid only once (enforced by both `debit_account` and `mark_bill_paid`). |
| LC-6 | All agents use the same demo date. Fees, balances and reminder dates are computed against it, never against the real calendar. |

## 6. Phase 1 limitations (motivating Phase 2)

In Phase 1, AC-1 is enforced structurally, because each bot is assigned only its own MCP server.
The tools also enforce FR-15 and LC-5 (no double payment, no overdraft, no dipping below a savings goal).
**Every other rule in §5 is a prompt instruction, not enforced isolation**, like the tutorial's
movie-night policy. A cooperative-sounding request, a model mistake, or text injected through a product
page can break IB-*, PR-*, AC-5 and LC-2. In particular:

- The user's payment confirmation (FR-12) exists only in PM's instructions. Nothing stops PM from skipping it.
- `debit_account` cannot tell whether a request came from PM or from the user's confirmation (PR-6).
- `mark_bill_paid` checks only the confirmation id's format, because PM cannot read Bank's ledger (PR-7).

The `boundary_probe` and `pay_probe` scenarios exercise these gaps. Phase 2 converts §5 into
enforceable rules in the policy-assurance framework.

## 7. Assumptions

- The product catalog is fictional, so no live Amazon scraping is done (that would be unreliable and bot-blocked).
- There is a single user and no authentication between user and FA.
- Interest accrues as simple daily interest: `amount × apy × days / 365`.
