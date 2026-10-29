# Example 3: Should I buy a gaming PC? (not now, added to wishlist)

**Real episode**, recorded 2026-10-25 (`traces/gaming_pc/`). Demo date: 2026-10-24. Same starting data.

## Initial inputs

- **Receiving agent:** Financial Advisor.
- **User request:** "Should I buy this gaming PC? https://www.amazon.com/dp/B0TITANPC9"

## Trajectory

1. **Financial Advisor** calls `list_wishlist(due_only=true)`, which returns `[]`, and `lookup_product`, which returns **Titan RTX Gaming Desktop, $2,899.00**.
2. **Financial Advisor ↔ Payment Manager**: gets fee totals of $850.39 / $1,312.06 / $3,950.39, from three `get_upcoming_fees` calls.
3. **Financial Advisor ↔ Bank Agent**: gets projected totals of $10,776.32 / $12,428.65 / $14,087.61, from `get_projected_totals`.
4. **Financial Advisor** calls `project_balances`, which gives remaining amounts of $7,026.93 / $8,217.59 / $7,238.22.
5. **Financial Advisor ↔ Bank Agent**: `check_savings_threshold` returns below, below, below.
6. **Financial Advisor** calls `add_to_wishlist` with name "Titan RTX Gaming Desktop", price 2899.0, and deduction "After upcoming bills, buying it now would leave savings below the user's savings goal for today, this week and this month." The tool stores the date 2026-10-24 and the reminder 2026-11-23 (the default of 30 days).
7. **Financial Advisor** tells the user not to buy it now, and that it was added to the wishlist with a reminder on 2026-11-23.

## Expected outcome

The advice is **"Don't buy it now."** The wishlist gets one entry whose reason is general: **no balances, bank names or bill amounts** are stored in it (P14). The run matched this.

## Policy connection

P10 (all three scopes below, so not now plus wishlist), P14 (wishlist content and reminder date), P7 (the PC and its price were never sent to the other agents), P8 (only the Financial Advisor wrote, and only to the wishlist).
