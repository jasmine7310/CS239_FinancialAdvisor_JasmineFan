# Example 6: The advisor reuses old figures (a real policy violation)

**Real episode**, recorded 2026-10-25 (`traces/console_reused_figures/`). It shows a violation that Phase 1 does not prevent.

## Initial inputs

- **Receiving agent:** Financial Advisor.
- **User request:** "Can I buy this gaming console? https://www.amazon.com/dp/B0NOVAPLY5", the same request as Example 1.
- **Context:** the Financial Advisor's chat still held an earlier run of the same request. The bots had not yet been told to fetch fresh figures every time, and the chat had not been cleared with `--fresh`.

## Trajectory

1. **Financial Advisor** calls `lookup_product` (the only tool call in the whole run) and finds the same item at $499.99.
2. **Financial Advisor** sends **no** messages to the Payment Manager or the Bank Agent. It answers: "This is the same link I just checked, and nothing has changed since, so I haven't asked the other agents again."
3. Its answer still shows a table labelled "**checked by Bank Agent**" (below, above, above), and it credits the bill and balance figures to the Payment Manager and the Bank Agent. Those figures came from the earlier conversation, not from this request.

## Expected outcome (per policy)

The Financial Advisor should have asked the Payment Manager and the Bank Agent again (P9), and the threshold verdict should have come from a fresh `check_savings_threshold` call (P10). **Actual:** the advice happened to be right ("wait about a week"), but it rested on reused figures and claimed a check that never happened in this request. In real use, that could hide a bill paid or a deposit received in the meantime.

**What we changed:** every agent's prompt now requires fresh figures for every request, and `--send … --fresh` clears all three chats before a run. Both are prompt-level or operational measures. Phase 2 should enforce P9 directly, for example by rejecting advice that lacks a threshold check from the current request.

## Policy connection

P9 (violated: figures reused, sources claimed falsely), P10 (violated: no threshold check in this request).
