# Tests

```bash
python -m unittest discover tests -v
```

Run this from the folder that contains `tests/`: the repository root, or the archive root next to
`src/`. Nothing beyond `requirements.txt` is needed, and there are no LLM, Rakazo or network calls. Every test runs on
a temporary copy of the starting data (`data/seed/`), so your real data and tool log are untouched.
The tests call the real tool functions, the same code the MCP servers expose to the agents.

`python -m phase1.check_tools` (in `src/`) is a complementary end-to-end check that walks the same
workflows through the three MCP servers over stdio and prints each step.

Agent reasoning (whether an LLM follows its prompt) can't be unit-tested. It is covered by the live
traces in `traces/` and the episodes in `description/episodes/`. The prompt-only policies are listed
in `policy.md`.

## Test cases

| Group | Test | What it checks | Policy |
|---|---|---|---|
| StartingData | `test_starting_data_matches_spec` | Empty wishlist, 20 unpaid bills, 2 checking + 3 savings accounts (goal only on savings), empty ledger | P15 |
| | `test_reset_restores_seed` | After a wishlist add and a debit, `reset_data()` restores the starting state | P15 |
| ToolInventory | `test_each_server_exposes_only_its_tools` | Each agent's MCP server lists exactly its own tools (for example, `debit_account` only on the Bank Agent's) | P1, P8 |
| | `test_tools_md_matches_implementation` | `description/tools.md` lists exactly the implemented tools plus Rakazo's `message_bot` | — |
| PurchaseAdvice | `test_console_wait_a_week` | Console ($499.99): day below, week and month above, so **wait about a week** | P10 |
| | `test_headphones_buy_today` | Headphones ($89.99): all above, so **buy today** | P10 |
| | `test_gaming_pc_not_now` | Gaming PC ($2,899): all below, so **not now** | P10 |
| | `test_unknown_link_asks_for_price` | An unknown product link returns `not_found` (the advisor asks for the price) | P9 |
| | `test_project_balances_math` | remaining = total − fees − price for each scope | P9 |
| | `test_projected_totals_include_deposits_and_interest` | Projections add scheduled paychecks and interest; scope end dates are 10-24, 10-31, 11-23 | P15 |
| Wishlist | `test_add_list_remove` | An entry has exactly the six wishlist fields, the demo date and a 30-day default reminder; it is listed and removed (case-insensitive) | P14 |
| | `test_due_reminders` | `due_only` returns items whose reminder date has arrived | P14 |
| | `test_wait_a_week_reminds_after_a_week` | The console's "wait about a week" is saved with reminder 2026-10-31, is not due on 10-30 at 23:59, and is due on 10-31 | P14 |
| | `test_wait_a_month_reminder` | `reminder="month"` gives today + 30 (2026-11-23) | P14 |
| | `test_same_item_updates_entry` | Saving the same item again (any letter case) updates its entry instead of adding a second one | P14 |
| | `test_rejects_past_reminder` | A reminder date before today is rejected | P14 |
| | `test_rejects_invalid_entries` | An empty name, negative price or blank reason is rejected | P14 |
| Clock | `test_get_and_move_clock` | `get_clock` reads 2026-10-24 09:00 (a Saturday); moving the clock returns the previous and new time | P15 |
| | `test_every_agent_sees_the_moved_clock` | After the clock moves, the Payment Manager's and the Bank Agent's tools report the new date, and no bill is overdue (the past week was autopaid) | P13, P15 |
| | `test_paychecks_arrive_when_the_clock_reaches_them` | On the bare clock (no autopay), the 10-30 paycheck is in the balance from 10-30 on (not at 10-29 23:00), is no longer counted as expected, and can pay a bill | P15 |
| | `test_console_recheck_a_week_later` | On 10-31 the console check gives "wait about a month": rent on 11-01 is in the week window (episode 10) | P10, P14 |
| | `test_ledger_uses_simulated_time` | Ledger entries carry the simulated date and time | P15, P16 |
| | `test_env_override_blocks_moving` | With `FINANCE_AS_OF` set, the clock reads it and moving it is refused | P15 |
| | `test_reset_shifts_everything_to_a_start_day` | A reset to 2026-11-20 shifts bills, paychecks and the clock by 27 days; fees, scope dates and all three purchase outcomes stay the same | P15 |
| | `test_moving_keeps_the_start` | Moving the clock keeps the run's start, which `python -m phase1.clock reset` returns to | P15 |
| | `test_cli_steps` | `python -m phase1.clock advance` accepts 7d, 2w, 1d6h and rejects malformed steps | P15 |
| Autopay | `test_a_week_passes` | Moving to 10-31 receives the 10-30 paycheck and autopays P01–P07 ($1,272.07, ledger `source: "autopay"`); P08, due on 10-31, stays due; the totals and fees agree | P2, P13, P15 |
| | `test_rent_is_paid_from_savings_without_overdraft` | The $1,850 rent that checking cannot cover is paid from savings; no account goes negative, and the savings account that drops below its goal is reported | P2, P15 |
| | `test_autopaid_bill_cannot_be_paid_again` | An autopaid bill is refused by `debit_account` and `mark_bill_paid` | P13 |
| | `test_no_agent_can_move_the_clock` | No agent's server has a tool that moves the clock, so only the user's command can set off autopay | P1, P2, P15 |
| | `test_moving_back_settles_nothing` | Moving the clock back pays nothing and receives nothing | P15 |
| | `test_same_outcomes_when_shifted` | On a run shifted to start 2026-11-20, a week of autopay pays the same $1,272.07 and receives the paycheck on its shifted date | P15 |
| Payments | `test_pay_bill_end_to_end` | Paying P01 ($650) from Sunset checking gives TX-0001, lowers the balance, writes the ledger and marks P01 paid; the day's fees drop to $200.39 and the console advice is unchanged | P2, P8, P13 |
| | `test_debit_refuses_below_savings_goal` | $210 from Westwood savings is refused (`below_savings_goal`) and no data changes | P12 |
| | `test_debit_refuses_insufficient_funds` | $1,850 from Bruin checking is refused (`insufficient_funds`) | P12 |
| | `test_debit_refuses_unknown_account` | An unknown bank is refused (`account_not_found`) | P12 |
| | `test_debit_refuses_non_bill_reference` | A reference that isn't a bill id, or a non-positive amount, is refused (`invalid_request`): money moves only to pay a bill | P2, P12 |
| | `test_bill_paid_only_once` | A second debit for P01 is refused (`duplicate_reference`), and a second `mark_bill_paid` raises an error | P13 |
| | `test_mark_paid_requires_bank_confirmation_format` | `mark_bill_paid` needs a `TX-####` id and an existing bill | P8 |
| | `test_fees_count_unpaid_overdue_bills` | With the clock moved to 10-26, unpaid overdue bills still count (3 overdue, $946.59) | P13 |
| SpendingChart | `test_chart_written` | The SVG chart is written and the type shares sum to 1 | — |
| Logging | `test_tool_calls_logged` | A tool call is logged with its agent, tool name and result | P16 |
| Prompts | `test_prompts_carry_policies_and_date` | Each bot's prompt starts with the demo date and contains its policy text, the fresh-figures rule and the payment-confirmation rule | P3, P4, P9, P15 |
| | `test_profiles_fit_rakazo_limits` | Every bot has a short description (at most 4,000 characters) and instructions within 20,000, so `--apply` is not rejected | — |
| | `test_agent_files_hold_exact_prompts` | `description/agents/*.md` contain the exact prompts from `app.py` (fails if they're stale: run `python -m phase1.describe`) | — |
| TraceExport | `test_full_conversation_follows_pages` | With Rakazo stubbed, the exporter follows `threads/messages` pages back to the first message, with no duplicates, in order | P16 |
| | `test_session_export_includes_scripted_and_typed` | A `--session` export starts at the earliest message and includes both script-sent and UI-typed messages | P16 |
| Descriptions | `test_policy_file_format` | `policy.md` has at least 3 policies numbered P1., P2., … consecutively, one paragraph each | — |
| | `test_traces_readme_covers_every_trace` | Every recorded trace in `traces/phase1/` has a `trace.md` and is described in `traces/README.md` (at least 3 traces) | — |
| | `test_episodes_cite_existing_policies` | Every episode cites at least one policy, and only policies that exist | — |
