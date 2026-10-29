"""Financial Advisor's MCP server: product lookup, balance math and the wishlist.

It has no bank or payment data. Those facts arrive only as messages from the other agents.
"""
import argparse
from datetime import date, datetime, timedelta
import re
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from .common import logged, read_json, today, write_json

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
    """Return wishlist items; due_only keeps items whose reminder date has arrived."""
    items = read_json('wishlist.json')
    if due_only:
        items = [i for i in items if date.fromisoformat(i['reminder']) <= today()]
    return {'as_of': today().isoformat(), 'items': items}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=False, open_world_hint=False))
@log
def add_to_wishlist(name: str, price: float, deduction: str, reminder: str = '') -> dict:
    """Save an item the user should not buy yet. reminder is YYYY-MM-DD (default: 30 days)."""
    if price < 0 or not name.strip() or not deduction.strip():
        raise ValueError('name, deduction and a nonnegative price are required')
    reminder_date = date.fromisoformat(reminder) if reminder else today() + timedelta(days=30)
    entry = {'name': name.strip(), 'price': price, 'date': today().isoformat(),
             'timestamp': datetime.now().isoformat(timespec='seconds'),
             'deduction': deduction.strip(), 'reminder': reminder_date.isoformat()}
    items = read_json('wishlist.json')
    items.append(entry)
    write_json('wishlist.json', items)
    return {'saved': entry, 'wishlist_size': len(items)}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         idempotent_hint=True, open_world_hint=False))
@log
def remove_from_wishlist(name: str) -> dict:
    """Remove an item (case-insensitive name) after the user buys it or no longer wants it."""
    items = read_json('wishlist.json')
    kept = [i for i in items if i['name'].lower() != name.strip().lower()]
    write_json('wishlist.json', kept)
    return {'removed': len(items) - len(kept), 'wishlist_size': len(kept)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    if args.http:
        server.run(transport='streamable-http', host='0.0.0.0', port=args.port)
    else:
        server.run(transport='stdio')
