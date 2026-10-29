# Financial Advisor: a multi-agent purchase advisor

## Purpose

A user asks whether they can afford an item, given as an Amazon link. Three LLM-based agents, each
holding its own slice of the user's (fictional) finances, cooperate to answer **whether** and
**when** to buy it: today, in about a week, in about a month, or not now. Items the user can't
afford yet go on a wishlist and come up again later. The user can also ask to **pay a bill**
from one of their accounts. Money moves only after the user confirms, and only the Bank Agent can
take money out of an account.

The application is built on Rakazo/grokbot (as in the CS239 tutorial). Each agent is a Rakazo bot
with its own MCP tool server, and the agents talk to each other through Rakazo's `message_bot`.
Coordination is centralized for purchases (the Financial Advisor drives the workflow) and
user-initiated for payments (the user talks to the Payment Manager). There are two entry points:
the Financial Advisor's chat and the Payment Manager's chat.

## Agents

| Agent | Owns | Role |
|---|---|---|
| Financial Advisor | Wishlist, product lookups | Talks to the user, looks up the price, asks the other agents for figures, applies the timing rule, keeps the wishlist |
| Payment Manager | Bills (rent, loans, debts, utilities, subscriptions, insurance) and their paid status | Reports unpaid fee totals per period; pays a bill on the user's confirmed request by asking the Bank Agent to debit an account |
| Bank Agent | Accounts, balances, savings goals, interest, scheduled paychecks, transaction ledger | Reports projected totals; checks remaining totals against the savings threshold (sum of savings goals); debits an account to pay a bill |

No agent can read another agent's data. The Financial Advisor never sees balances or individual
bills, and neither the Payment Manager nor the Bank Agent ever sees the wishlist or what the user
wants to buy.

## Supported tasks

1. **Purchase timing advice.** "Can I buy this? <link>"
   1. The Financial Advisor looks up the price.
   2. It gets the unpaid fee totals for the day, week and month from the Payment Manager.
   3. It gets the projected totals for the same periods from the Bank Agent.
   4. It computes what would be left after the bills and the item.
   5. It asks the Bank Agent whether each amount stays above the savings threshold.
   6. It advises buying today, waiting about a week, waiting about a month, or not buying now.
2. **Wishlist.** Items the user should not buy now are saved with a general reason and a
   reminder date. When a reminder date arrives, the Financial Advisor brings the item up again.
3. **Bill payment.** "Pay my debt bill from my Sunset Federal checking."
   1. The Payment Manager finds the bill and asks the user to confirm it.
   2. It asks the Bank Agent to debit the account.
   3. The Bank Agent pays or refuses (unknown account, insufficient funds, savings below goal,
      already paid).
   4. The Payment Manager records the bill as paid, using the Bank Agent's confirmation id.
4. **Spending summary.** The Payment Manager summarizes bills by type and draws a bar chart.

All data is fictional (`data/*.json`). Dates use a fixed demo date (2026-10-24), so runs are
reproducible. The requirements and the 16 policies are in `policy.md`.
