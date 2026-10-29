"""Payment Manager's MCP server: upcoming bills, bill status and a spending-habits chart.

It has no bank data and no wishlist. It cannot move money: it only records a bill as paid
after the Bank Agent reports a confirmation id.
"""
import argparse
from collections import defaultdict
from datetime import date
import re
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from .common import DATA_DIR, horizon, logged, read_json, today, write_json

server = MCPServer('Payment Manager')
log = logged('Payment Manager')
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                            idempotent_hint=True, open_world_hint=False)


def due_within(scope: str) -> list[dict]:
    """Bills due from today through the end of scope, paid or not (spending habits)."""
    end = horizon(scope)
    return sorted((p for p in read_json('payments.json')
                   if today() <= date.fromisoformat(p['due']) <= end), key=lambda p: p['due'])


def owed_within(scope: str) -> list[dict]:
    """Unpaid bills due by the end of scope, including overdue ones (what is still owed)."""
    end = horizon(scope)
    return sorted((p for p in read_json('payments.json')
                   if p['status'] == 'unpaid' and date.fromisoformat(p['due']) <= end),
                  key=lambda p: p['due'])


def totals_by_type(payments: list[dict]) -> dict:
    by_type = defaultdict(float)
    for p in payments:
        by_type[p['type']] += p['fee']
    return {t: round(v, 2) for t, v in sorted(by_type.items(), key=lambda kv: -kv[1])}


@server.tool(annotations=READ_ONLY)
@log
def get_upcoming_fees(scope: str) -> dict:
    """Unpaid fees due by the end of scope: "day" (today), "week" (7 days) or "month" (30 days).
    Overdue unpaid bills are included; paid bills are not."""
    payments = owed_within(scope)
    overdue = [p for p in payments if date.fromisoformat(p['due']) < today()]
    return {'scope': scope, 'as_of': today().isoformat(), 'through': horizon(scope).isoformat(),
            'total': round(sum(p['fee'] for p in payments), 2), 'count': len(payments),
            'overdue_count': len(overdue), 'by_type': totals_by_type(payments), 'payments': payments}


@server.tool(annotations=READ_ONLY)
@log
def list_unpaid_bills() -> dict:
    """Every unpaid bill with its id, type, fee and due date, soonest first."""
    bills = sorted((p for p in read_json('payments.json') if p['status'] == 'unpaid'),
                   key=lambda p: p['due'])
    return {'as_of': today().isoformat(), 'bills': bills}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=False, open_world_hint=False))
@log
def mark_bill_paid(bill_id: str, confirmation: str) -> dict:
    """Record a bill as paid, using the confirmation id (TX-####) the Bank Agent returned for it.
    Call this only after the Bank Agent reports the payment completed."""
    if not re.fullmatch(r'TX-\d{4,}', confirmation.strip()):
        raise ValueError('confirmation must be the Bank Agent\'s id, e.g. TX-0001')
    payments = read_json('payments.json')
    bill = next((p for p in payments if p['id'] == bill_id.strip().upper()), None)
    if bill is None:
        raise ValueError(f'no bill with id {bill_id}')
    if bill['status'] == 'paid':
        raise ValueError(f'bill {bill["id"]} is already paid ({bill["confirmation"]})')
    bill.update(status='paid', paid_on=today().isoformat(), confirmation=confirmation.strip())
    write_json('payments.json', payments)
    return {'paid': bill}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=True, open_world_hint=False))
@log
def spending_chart(scope: str = 'month') -> dict:
    """Summarize bills by type for a scope and save an SVG bar chart of the user's spending habits."""
    by_type = totals_by_type(due_within(scope))
    total = round(sum(by_type.values()), 2)
    width, bar_h, label_w = 560, 26, 110
    biggest = max(by_type.values(), default=1)
    rows = []
    for i, (kind, amount) in enumerate(by_type.items()):
        y = 40 + i * (bar_h + 8)
        w = (width - label_w - 90) * amount / biggest
        rows.append(f'<text x="{label_w - 8}" y="{y + 18}" text-anchor="end">{kind}</text>'
                    f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="#4a78c2"/>'
                    f'<text x="{label_w + w + 6:.1f}" y="{y + 18}">${amount:,.2f}</text>')
    height = 60 + len(by_type) * (bar_h + 8)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'font-family="sans-serif" font-size="13">'
           f'<rect width="100%" height="100%" fill="white"/>'
           f'<text x="10" y="22" font-weight="bold">Bills due {today()} to {horizon(scope)} '
           f'(total ${total:,.2f})</text>' + ''.join(rows) + '</svg>')
    path = DATA_DIR / 'charts' / f'spending_{scope}.svg'
    path.parent.mkdir(exist_ok=True)
    path.write_text(svg, encoding='utf-8')
    return {'scope': scope, 'total': total,
            'share': {k: round(v / total, 3) if total else 0 for k, v in by_type.items()},
            'by_type': by_type, 'chart': str(path)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--port', type=int, default=8772)
    args = parser.parse_args()
    if args.http:
        server.run(transport='streamable-http', host='0.0.0.0', port=args.port)
    else:
        server.run(transport='stdio')
