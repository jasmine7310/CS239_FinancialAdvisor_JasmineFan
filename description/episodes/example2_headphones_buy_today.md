# Example 2: Do these headphones fit my budget? (buy today)

**Real episode**, recorded 2026-10-25 (`traces/phase1/headphones/`). Demo date: 2026-10-24. Same starting data as Example 1.

## Initial inputs

- **Receiving agent:** Financial Advisor.
- **User request:** "I want these headphones: https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1 Do they fit my budget?"

## Trajectory

1. **Financial Advisor** calls `lookup_product`, which returns **Wavelength Wireless Headphones, $89.99**. It also calls `list_wishlist(due_only=true)`, which returns `[]`.
2. **Financial Advisor → Payment Manager**: requests unpaid fee totals per scope. **Payment Manager** calls `get_upcoming_fees` three times and replies $850.39 / $1,312.06 / $3,950.39.
3. **Financial Advisor → Bank Agent**: requests projected totals. **Bank Agent** calls `get_projected_totals` and replies $10,776.32 / $12,428.65 / $14,087.61.
4. **Financial Advisor** calls `project_balances`, which gives remaining amounts of $9,835.94 / $11,026.60 / $10,047.23.
5. **Financial Advisor → Bank Agent**: sends the three remaining amounts. **Bank Agent** calls `check_savings_threshold` and replies above, above, above.
6. **Financial Advisor** answers with a table showing which agent supplied each figure.

## Expected outcome

**"You can buy the Wavelength Wireless Headphones ($89.99) today."** All three periods stay above the savings threshold. The run matched this, and nothing was added to the wishlist.

## Policy connection

P5, P6, P7 (only totals and numbers were exchanged), P9 (fresh figures with sources cited), P10 (all three scopes above, so buy today).
