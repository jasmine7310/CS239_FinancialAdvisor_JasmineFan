"""Each agent's tools, and ToolBox.call: the one place every tool call goes through.

Each agent owns its data and may call only its own tools:
  Financial Advisor - wishlist.json, products.json (read-only), reads the clock
  Payment Manager   - payments.json
  Bank Agent        - accounts.json, deposits.json (read-only), transactions.json
Tool functions take the run's Store first; the rest are the arguments the model supplies.
"""
from collections import defaultdict
from datetime import date
import re
from .store import SCOPES, Store

ADVISOR, PAYMENTS, BANK = 'Financial Advisor', 'Payment Manager', 'Bank Agent'
AGENTS = (ADVISOR, PAYMENTS, BANK)


# --- Financial Advisor ------------------------------------------------------------------

def lookup_product(store: Store, url: str) -> dict:
    """Look up an item's name and price from its Amazon link (fictional catalog, USD)."""
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    product = next((p for p in store.read('products.json') if match and p['asin'] == match.group(1)), None)
    if product is None:
        return {'status': 'not_found', 'url': url, 'hint': 'Ask the user for the item name and price.'}
    # The description is page text from outside the app: data to report, never instructions (P11).
    return {'status': 'found', 'url': url, 'name': product['name'], 'price': product['price'],
            'description': product.get('description', ''), 'source': 'fictional product catalog'}


def project_balances(store: Store, price: float, fees_day: float, fees_week: float, fees_month: float,
                     total_day: float, total_week: float, total_month: float) -> dict:
    """Subtract the item price and the fees due in each scope from the projected bank total."""
    fees = {'day': fees_day, 'week': fees_week, 'month': fees_month}
    totals = {'day': total_day, 'week': total_week, 'month': total_month}
    return {'price': price, 'remaining': {s: round(totals[s] - fees[s] - price, 2) for s in fees}}


def list_wishlist(store: Store, due_only: bool = False) -> dict:
    """Wishlist items; due_only keeps items whose reminder date has arrived."""
    items = store.read('wishlist.json')
    if due_only:
        items = [i for i in items if date.fromisoformat(i['reminder']) <= store.today()]
    return {'as_of': store.today().isoformat(), 'now': store.now().isoformat(timespec='minutes'), 'items': items}


def add_to_wishlist(store: Store, name: str, price: float, deduction: str, reminder: str = 'month') -> dict:
    """Save an item the user should not buy right now. reminder: "week" (7 days), "month" (30 days)
    or a YYYY-MM-DD date. Saving an item already on the wishlist updates its entry."""
    if price < 0 or not name.strip() or not deduction.strip():
        raise ValueError('name, deduction and a nonnegative price are required')
    reminder = reminder.strip().lower() or 'month'
    reminder_date = store.horizon(reminder) if reminder in ('week', 'month') else date.fromisoformat(reminder)
    if reminder_date < store.today():
        raise ValueError('reminder must not be in the past')
    entry = {'name': name.strip(), 'price': price, 'date': store.today().isoformat(),
             'timestamp': store.now().isoformat(timespec='seconds'), 'deduction': deduction.strip(),
             'reminder': reminder_date.isoformat()}
    items = store.read('wishlist.json')
    kept = [i for i in items if i['name'].lower() != entry['name'].lower()]
    store.write('wishlist.json', kept + [entry])
    return {'saved': entry, 'updated': len(kept) < len(items), 'wishlist_size': len(kept) + 1}


def remove_from_wishlist(store: Store, name: str) -> dict:
    """Remove an item (case-insensitive name) after the user buys it or no longer wants it."""
    items = store.read('wishlist.json')
    kept = [i for i in items if i['name'].lower() != name.strip().lower()]
    store.write('wishlist.json', kept)
    return {'removed': len(items) - len(kept), 'wishlist_size': len(kept)}


def get_clock(store: Store) -> dict:
    """The simulated date and time all agents use as "now". Only the user can move it."""
    current = store.now()
    return {'now': current.isoformat(timespec='minutes'), 'date': current.date().isoformat(),
            'weekday': f'{current:%A}'}


# --- Payment Manager --------------------------------------------------------------------

def due_within(store: Store, scope: str) -> list[dict]:
    """Bills due from today through the end of scope, paid or not (spending habits)."""
    end = store.horizon(scope)
    return sorted((p for p in store.read('payments.json')
                   if store.today() <= date.fromisoformat(p['due']) <= end), key=lambda p: p['due'])


def owed_within(store: Store, scope: str) -> list[dict]:
    """Unpaid bills due by the end of scope, including overdue ones (what is still owed)."""
    end = store.horizon(scope)
    return sorted((p for p in store.read('payments.json')
                   if p['status'] == 'unpaid' and date.fromisoformat(p['due']) <= end), key=lambda p: p['due'])


def totals_by_type(payments: list[dict]) -> dict:
    by_type = defaultdict(float)
    for p in payments:
        by_type[p['type']] += p['fee']
    return {t: round(v, 2) for t, v in sorted(by_type.items(), key=lambda kv: -kv[1])}


def get_upcoming_fees(store: Store, scope: str) -> dict:
    """Unpaid fees due by the end of scope: "day" (today), "week" (7 days) or "month" (30 days).
    Overdue unpaid bills are included; paid bills are not."""
    payments = owed_within(store, scope)
    overdue = [p for p in payments if date.fromisoformat(p['due']) < store.today()]
    return {'scope': scope, 'as_of': store.today().isoformat(), 'through': store.horizon(scope).isoformat(),
            'total': round(sum(p['fee'] for p in payments), 2), 'count': len(payments),
            'overdue_count': len(overdue), 'by_type': totals_by_type(payments), 'payments': payments}


def list_unpaid_bills(store: Store) -> dict:
    """Every unpaid bill with its id, type, fee and due date, soonest first."""
    bills = sorted((p for p in store.read('payments.json') if p['status'] == 'unpaid'), key=lambda p: p['due'])
    return {'as_of': store.today().isoformat(), 'bills': bills}


def mark_bill_paid(store: Store, bill_id: str, confirmation: str) -> dict:
    """Record a bill as paid with the confirmation id (TX-####) Bank Agent returned for it."""
    if not re.fullmatch(r'TX-\d{4,}', confirmation.strip()):
        raise ValueError("confirmation must be Bank Agent's id, e.g. TX-0001")
    payments = store.read('payments.json')
    bill = next((p for p in payments if p['id'] == bill_id.strip().upper()), None)
    if bill is None:
        raise ValueError(f'no bill with id {bill_id}')
    if bill['status'] == 'paid':
        raise ValueError(f'bill {bill["id"]} is already paid ({bill["confirmation"]})')
    bill.update(status='paid', paid_on=store.today().isoformat(), confirmation=confirmation.strip())
    store.write('payments.json', payments)
    return {'paid': bill}


def spending_chart(store: Store, scope: str = 'month') -> dict:
    """Summarize bills by type for a scope and save an SVG bar chart of the user's spending habits."""
    by_type = totals_by_type(due_within(store, scope))
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
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{60 + len(by_type) * (bar_h + 8)}" '
           f'font-family="sans-serif" font-size="13"><rect width="100%" height="100%" fill="white"/>'
           f'<text x="10" y="22" font-weight="bold">Bills due {store.today()} to {store.horizon(scope)} '
           f'(total ${total:,.2f})</text>' + ''.join(rows) + '</svg>')
    path = store.root / 'charts' / f'spending_{scope}.svg'
    path.parent.mkdir(exist_ok=True)
    path.write_text(svg, encoding='utf-8')
    return {'scope': scope, 'total': total,
            'share': {k: round(v / total, 3) if total else 0 for k, v in by_type.items()},
            'by_type': by_type, 'chart': path.name}


# --- Bank Agent -------------------------------------------------------------------------

def savings_threshold(accounts: list[dict]) -> float:
    return round(sum(a.get('goal', 0) for a in accounts if a['type'] == 'savings'), 2)


def current_accounts(store: Store) -> list[dict]:
    """Stored balances plus every scheduled deposit the simulated clock has reached."""
    accounts = store.read('accounts.json')
    for d in store.read('deposits.json'):
        if date.fromisoformat(d['date']) <= store.today():
            for a in accounts:
                if (a['bank'], a['type']) == (d['bank'], d['type']):
                    a['amount'] = round(a['amount'] + d['amount'], 2)
    return accounts


def get_accounts(store: Store) -> dict:
    """Every account with its current balance (received paychecks included), savings goal and APY,
    plus the savings threshold (sum of savings goals)."""
    accounts = current_accounts(store)
    return {'as_of': store.today().isoformat(), 'accounts': accounts,
            'current_total': round(sum(a['amount'] for a in accounts), 2),
            'savings_threshold': savings_threshold(accounts)}


def get_projected_totals(store: Store) -> dict:
    """Total money across all accounts at the end of each scope (day, week, month),
    including scheduled deposits still to come and expected interest."""
    accounts = current_accounts(store)
    deposits = [d for d in store.read('deposits.json') if date.fromisoformat(d['date']) > store.today()]
    current = sum(a['amount'] for a in accounts)
    result = {'as_of': store.today().isoformat(), 'current_total': round(current, 2),
              'through': {s: store.horizon(s).isoformat() for s in SCOPES},
              'expected_deposits': {}, 'expected_interest': {}, 'projected_total': {}}
    for scope, days in SCOPES.items():
        incoming = sum(d['amount'] for d in deposits if date.fromisoformat(d['date']) <= store.horizon(scope))
        interest = sum(a['amount'] * a.get('apy', 0) * max(days, 1) / 365 for a in accounts)
        result['expected_deposits'][scope] = round(incoming, 2)
        result['expected_interest'][scope] = round(interest, 2)
        result['projected_total'][scope] = round(current + incoming + interest, 2)
    return result


def check_savings_threshold(store: Store, day: float, week: float, month: float) -> dict:
    """Whether each remaining total (after purchase and fees) stays at or above the savings threshold."""
    threshold = savings_threshold(store.read('accounts.json'))
    return {'savings_threshold': threshold,
            'checks': {s: {'remaining': v, 'above_threshold': v >= threshold}
                       for s, v in {'day': day, 'week': week, 'month': month}.items()}}


def debit_account(store: Store, bank: str, account_type: str, amount: float, reference: str) -> dict:
    """Pay one bill by debiting one account; reference is the bill id (e.g. P01). Refuses an unknown
    account, a non-bill reference, a bill already paid, insufficient funds, or a debit that would drop
    a savings account below its goal."""
    reference = reference.strip().upper()
    refused = lambda reason: {'status': 'refused', 'reason': reason, 'reference': reference}
    amount = round(amount, 2)
    if amount <= 0 or not re.fullmatch(r'P\d{2,}', reference):
        return refused('invalid_request: amount must be positive and reference a bill id like P01')
    ledger = store.read('transactions.json')
    if any(t['reference'] == reference for t in ledger):
        return refused('duplicate_reference: this bill was already paid')
    accounts = store.read('accounts.json')
    find = lambda rows: next((a for a in rows if a['bank'].lower() == bank.strip().lower()
                              and a['type'] == account_type.strip().lower()), None)
    account, balance = find(accounts), find(current_accounts(store))
    if account is None:
        return refused('account_not_found')
    if amount > balance['amount']:
        return refused('insufficient_funds')
    if account['type'] == 'savings' and balance['amount'] - amount < account.get('goal', 0):
        return refused('below_savings_goal')
    account['amount'] = round(account['amount'] - amount, 2)
    entry = {'confirmation': f'TX-{len(ledger) + 1:04d}', 'bank': account['bank'], 'type': account['type'],
             'amount': amount, 'reference': reference, 'date': store.today().isoformat(),
             'timestamp': store.now().isoformat(timespec='seconds')}
    store.write('accounts.json', accounts)
    store.write('transactions.json', ledger + [entry])
    return {'status': 'completed', 'confirmation': entry['confirmation'], 'reference': reference, 'amount': amount}


# --- Tool definitions (what each agent's model sees) ------------------------------------

def _schema(properties: dict, required: list[str]) -> dict:
    return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}


NUMBER, STRING, BOOLEAN = {'type': 'number'}, {'type': 'string'}, {'type': 'boolean'}
SCOPE = {'type': 'string', 'enum': list(SCOPES)}

TOOLS = {
    ADVISOR: {
        'lookup_product': (lookup_product, _schema({'url': STRING}, ['url'])),
        'project_balances': (project_balances, _schema(
            {k: NUMBER for k in ('price', 'fees_day', 'fees_week', 'fees_month', 'total_day', 'total_week',
                                 'total_month')},
            ['price', 'fees_day', 'fees_week', 'fees_month', 'total_day', 'total_week', 'total_month'])),
        'list_wishlist': (list_wishlist, _schema({'due_only': BOOLEAN}, [])),
        'add_to_wishlist': (add_to_wishlist, _schema(
            {'name': STRING, 'price': NUMBER, 'deduction': STRING,
             'reminder': {'type': 'string', 'description': '"week", "month" or YYYY-MM-DD'}},
            ['name', 'price', 'deduction'])),
        'remove_from_wishlist': (remove_from_wishlist, _schema({'name': STRING}, ['name'])),
        'get_clock': (get_clock, _schema({}, [])),
    },
    PAYMENTS: {
        'get_upcoming_fees': (get_upcoming_fees, _schema({'scope': SCOPE}, ['scope'])),
        'list_unpaid_bills': (list_unpaid_bills, _schema({}, [])),
        'mark_bill_paid': (mark_bill_paid, _schema({'bill_id': STRING, 'confirmation': STRING},
                                                   ['bill_id', 'confirmation'])),
        'spending_chart': (spending_chart, _schema({'scope': SCOPE}, [])),
    },
    BANK: {
        'get_accounts': (get_accounts, _schema({}, [])),
        'get_projected_totals': (get_projected_totals, _schema({}, [])),
        'check_savings_threshold': (check_savings_threshold, _schema(
            {'day': NUMBER, 'week': NUMBER, 'month': NUMBER}, ['day', 'week', 'month'])),
        'debit_account': (debit_account, _schema(
            {'bank': STRING, 'account_type': {'type': 'string', 'enum': ['checking', 'savings']},
             'amount': NUMBER, 'reference': {'type': 'string', 'description': 'bill id, e.g. P01'}},
            ['bank', 'account_type', 'amount', 'reference'])),
    },
}


def definitions(agent: str) -> list[dict]:
    """The agent's tool definitions for the Messages API."""
    return [{'name': name, 'description': (fn.__doc__ or '').strip(), 'input_schema': schema}
            for name, (fn, schema) in TOOLS[agent].items()]


class ToolBox:
    """Runs tool calls for agents. An agent may call only its own tools."""

    def __init__(self, store: Store, trace):
        self.store, self.trace = store, trace

    def call(self, agent: str, tool: str, arguments: dict) -> dict:
        call_id = self.trace.add('tool_call', agent, tool=tool, arguments=arguments)
        entry = TOOLS.get(agent, {}).get(tool)
        try:
            if entry is None:
                raise PermissionError(f'{agent} has no tool named {tool}')
            result = entry[0](self.store, **arguments)
        except (PermissionError, ValueError, TypeError, KeyError) as exc:
            result = {'error': f'{type(exc).__name__}: {exc}'}
        self.trace.add('tool_result', agent, tool=tool, call=call_id, result=result)
        return result
