# Example 10: A week later, the Financial Advisor reminds the user

**Hypothetical episode** (scenario `reminder`). It hasn't been recorded live yet. The tool results below are real: they come from running the tools at each date, and are checked by `tests/test_tools.py` (`test_wait_a_week_reminds_after_a_week`, `test_console_recheck_a_week_later`, the `Clock` tests) and by `python -m phase1.check_tools`. Starting data: `run_servers --reset`, then the `console` scenario (Example 1).

## Initial inputs

- **State after Example 1:** the wishlist holds the NovaPlay 5 Gaming Console (1TB), $499.99, saved on 2026-10-24 with the reminder date **2026-10-31**. The simulated clock reads 2026-10-24 09:00.
- **The user moves time forward**, with `python -m phase1.clock advance 7d`, the only way to move time (no agent can). The clock now reads **2026-10-31 09:00**, and the simulator settles the week that passed (P2, P15). The 10-30 paycheck ($1,650) is received, and bills P01–P07 ($1,272.07, due 10-24 to 10-29) are paid by autopay, mostly from checking; two of them (P04 $96.20 and P06 $245.00) came from savings, because before the paycheck checking could not cover them. P08 ($39.99, due 10-31) is still due.
- **Receiving agent:** Financial Advisor. **User request:** "Hi! Is there anything I should know about today?"

## Trajectory

1. **Financial Advisor** starts the new request with `list_wishlist(due_only=true)`. This returns `as_of: 2026-10-31` and the NovaPlay 5, because its reminder date has arrived. On 10-30 the same call returned nothing (P14).
2. **Financial Advisor → user:** before anything else, it reminds the user: "You saved the NovaPlay 5 Gaming Console (1TB), $499.99, on 2026-10-24 because buying it then would have dipped below your savings goal. Do you want me to check whether you can buy it now?" It does **not** call the item affordable yet: a reminder is not advice (P14, P9).
3. *(If the user says yes)* **Financial Advisor** runs the full purchase check with fresh figures as of 2026-10-31 (P9, P10, P15). Every number below is what the tools return on that date, starting from the seed data, after the simulator settled the week that passed:
   - **Payment Manager:** unpaid fees of $39.99 for the day (P08 only; no bill is overdue, since autopay paid the past week), $2,268.84 for the week (adding the **$1,850 rent due 11-01**) and $3,328.32 for the month.
   - **Bank Agent:** projected totals of $11,154.24 for the day, $11,156.54 for the week and $14,465.36 for the month. The current total is $11,153.86: the starting $10,775.93, plus the $1,650 paycheck, minus $1,272.07 of autopaid bills.
   - **`project_balances`:** remaining amounts of $10,614.26 for the day, $8,387.71 for the week and $10,637.05 for the month.
   - **`check_savings_threshold`:** above for the day, **below** for the week, above for the month.
4. **Financial Advisor** applies the timing rule and advises **waiting about a month**. Rent falls inside the new week window, before the 11-13 paycheck. It calls `add_to_wishlist` again with the same name and `reminder="month"`, which updates the entry to a reminder on **2026-11-30** instead of adding a second one, and tells the user.

## Expected outcome

The user is reminded of the console on their first request on or after 2026-10-31, not before. The reminder doesn't mean "buy now". A fresh check as of 10-31 gives **wait about a month**, because the week now includes the $1,850 rent due on 11-01. The original check on 10-24 couldn't see that rent: it falls one day after that check's week window. The wishlist entry is updated to 2026-11-30, and nobody but the user moved the clock.

## Policy connection

P14 (saved with a one-week reminder, reminded on the first request after it, updated rather than duplicated), P15 (shared simulated clock, moved only by the user's command; the paycheck counts once the clock reaches its date), P2 and P13 (the simulator, not an agent, pays the past week's bills, each exactly once), P9 and P10 (a reminder is not advice; fresh figures before any verdict).
