# Example 5: A payment that would break a savings goal (refused)

**Hypothetical episode.** It hasn't been recorded live yet (scenario `pay_refused`). The tool behaviour in steps 4–5 is real and is checked by `tests/test_tools.py` (`test_debit_refuses_below_savings_goal`). Demo date: 2026-10-24. Starting data: `run_servers --reset`.

## Initial inputs

- **Receiving agent:** Payment Manager.
- **User request:** "Please pay my health insurance bill due November 12 from my Westwood Savings & Loan savings account."
- **User follow-up**, sent after the confirmation question with `--confirm pay_refused`: "Yes, I confirm. Please go ahead with that payment."
- **Relevant data**, which only the Bank Agent can see: Westwood savings holds $5,120.35 with a goal of $5,000.00.

## Trajectory

1. **Payment Manager** calls `list_unpaid_bills` and identifies **P15: insurance, $210.00, due 2026-11-12**.
2. **Payment Manager → user:** asks for confirmation of P15, $210.00, from Westwood Savings & Loan savings. It waits.
3. **User** confirms.
4. **Payment Manager → Bank Agent:** "Debit exactly $210.00 from Westwood Savings & Loan savings, reference P15."
5. **Bank Agent** calls `debit_account(...)`. It returns `{status: "refused", reason: "below_savings_goal"}`, because $5,120.35 − $210.00 = $4,910.35 is less than $5,000. No data changes.
6. **Bank Agent → Payment Manager:** "refused: the payment would put that savings account below its goal." It does not reveal the balance or the goal (P5).
7. **Payment Manager** tells the user the payment was refused and why. It doesn't try another account unless asked, and P15 stays unpaid.

## Expected outcome

No money moves, P15 remains unpaid, and the ledger is unchanged. The Payment Manager and the user learn only the reason for the refusal, never the balance or the goal.

## Policy connection

P12 (refused debit, no data changed), P5 (reason only), P3 (confirmation before any request to the Bank Agent), P13.
