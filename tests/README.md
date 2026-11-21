# Tests

```bash
python -m unittest discover tests -v
```

Run from the repository root. No model, network or API key: the tests use the free `ScriptedBackend`,
and each test runs on its own fresh copy of `fixtures/`.

| Group | What it checks | Policy |
|---|---|---|
| StoreAndClock | Fixtures start on 2026-10-24; a run can start on another day with every date shifted and the same answers; runs don't share data; time steps like `1d6h` parse | P15 |
| Tools | The three purchase outcomes; wishlist reminders (week, month, update instead of duplicate, no past dates); every debit refusal; `mark_bill_paid` needs a `TX-####` id | P10, P12, P13, P14 |
| Boundaries | `ToolBox.call` refuses another agent's tool; only the Bank Agent can debit, and no agent can move time; `MessageBus.send` enforces who may message whom (the Bank Agent only replies); the bus labels the real sender; every prompt carries its policy | P1, P2, P3, P15 |
| TimePassing | A week passes: the paycheck arrives, P01–P07 are autopaid, and nothing is overdue; rent comes from savings without overdraft; moving back pays nothing | P2, P13, P15 |
| Scenarios | Every scenario end to end, including no item or price sent to other agents, confirmation before payment, refusals and redirects, and every run traced | P3, P4, P5, P7, P10, P14, P17 |
| Harness (`test_harness.py`) | `test_cases.json` matches `run.py`; all ten cases pass; `--case` and `--sample` write the right folders; a wrong outcome, an error and a timeout each give `false` | — |

The scripted agents follow the policies by construction, so these tests check the app's mechanics and the
code-enforced rules. Whether a live model follows the prompt-only policies shows in live runs and their
traces.
