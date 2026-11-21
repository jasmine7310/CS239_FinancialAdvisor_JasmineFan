"""Financial Advisor's MCP server: product lookup, balance math, the wishlist and the simulated clock.

It has no bank or payment data. Those facts arrive only as messages from the other agents.
"""
import argparse
from datetime import date
import re
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from .common import horizon, logged, now, parse_when, read_json, set_now, today, write_json

server = MCPServer('Financial Advisor')
log = logged('Financial Advisor')
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                            idempotent_hint=True, open_world_hint=False)


@server.tool(annotations=READ_ONLY)
@log
def lookup_product(url: str) -> dict:
    """Look up an item's name and price from its Amazon link (fictional catalog, USD)."""
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    catalog = read_json('products.json')
    product = next((p for p in catalog if match and p['asin'] == match.group(1)), None)
    if product is None:
        return {'status': 'not_found', 'url': url,
                'hint': 'Ask the user for the item name and price.'}
    return {'status': 'found', 'url': url, 'name': product['name'], 'price': product['price'],
            'source': 'fictional product catalog'}


@server.tool(annotations=READ_ONLY)
@log
def project_balances(price: float, fees_day: float, fees_week: float, fees_month: float,
                     total_day: float, total_week: float, total_month: float) -> dict:
    """Subtract the item price and fees due in each scope from the projected bank total."""
    fees = {'day': fees_day, 'week': fees_week, 'month': fees_month}
    totals = {'day': total_day, 'week': total_week, 'month': total_month}
    return {'price': price,
            'remaining': {s: round(totals[s] - fees[s] - price, 2) for s in fees}}


@server.tool(annotations=READ_ONLY)
@log
def list_wishlist(due_only: bool = False) -> dict:
    """Return wishlist items; due_only keeps items whose reminder date has arrived (on the simulated clock)."""
    items = read_json('wishlist.json')
    if due_only:
        items = [i for i in items if date.fromisoformat(i['reminder']) <= today()]
    return {'as_of': today().isoformat(), 'now': now().isoformat(timespec='minutes'), 'items': items}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=True, open_world_hint=False))
@log
def add_to_wishlist(name: str, price: float, deduction: str, reminder: str = 'month') -> dict:
    """Save an item the user should not buy right now, with when to remind them: reminder is "week"
    (7 days, for "wait about a week"), "month" (30 days, for "wait about a month" or "not now"),
    or a YYYY-MM-DD date. Asking about an item already on the wishlist updates its entry."""
    if price < 0 or not name.strip() or not deduction.strip():
        raise ValueError('name, deduction and a nonnegative price are required')
    reminder = reminder.strip().lower() or 'month'
    reminder_date = horizon(reminder) if reminder in ('week', 'month') else date.fromisoformat(reminder)
    if reminder_date < today():
        raise ValueError('reminder must not be in the past')
    entry = {'name': name.strip(), 'price': price, 'date': today().isoformat(),
             'timestamp': now().isoformat(timespec='seconds'),
             'deduction': deduction.strip(), 'reminder': reminder_date.isoformat()}
    items = read_json('wishlist.json')
    kept = [i for i in items if i['name'].lower() != entry['name'].lower()]
    write_json('wishlist.json', kept + [entry])
    return {'saved': entry, 'updated': len(kept) < len(items), 'wishlist_size': len(kept) + 1}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         idempotent_hint=True, open_world_hint=False))
@log
def remove_from_wishlist(name: str) -> dict:
    """Remove an item (case-insensitive name) after the user buys it or no longer wants it."""
    items = read_json('wishlist.json')
    kept = [i for i in items if i['name'].lower() != name.strip().lower()]
    write_json('wishlist.json', kept)
    return {'removed': len(items) - len(kept), 'wishlist_size': len(kept)}


@server.tool(annotations=READ_ONLY)
@log
def get_clock() -> dict:
    """The simulated date and time all agents use as "now"."""
    current = now()
    return {'now': current.isoformat(timespec='minutes'), 'date': current.date().isoformat(),
            'weekday': f'{current:%A}'}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=True, open_world_hint=False))
@log
def set_clock(when: str) -> dict:
    """Move the shared simulated clock to `when` ("YYYY-MM-DD" for 09:00 that day, or
    "YYYY-MM-DDTHH:MM"), to simulate time passing. Only when the user explicitly asks."""
    return set_now(parse_when(when))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    if args.http:
        server.run(transport='streamable-http', host='0.0.0.0', port=args.port)
    else:
        server.run(transport='stdio')
