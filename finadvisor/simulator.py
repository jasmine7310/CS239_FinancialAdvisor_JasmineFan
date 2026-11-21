"""The world outside the agents: time passing. Only the user moves time; no agent has a tool for it.

Moving the clock forward stands for the user living through those days: paychecks count as
received once the clock reaches their date (tools.current_accounts adds them), and every bill due
before the new date is paid by autopay - from the paycheck account when it can cover it, otherwise
other checking, then savings (keeping savings goals when possible). Each payment is recorded in the
ledger like any other debit, with source "autopay". This is the simulator acting for the user,
not an agent: agents move money only through the Bank Agent's debit_account.
"""
from datetime import date, datetime, timedelta
import re
from .store import Store

UNITS = {'w': 'weeks', 'd': 'days', 'h': 'hours', 'm': 'minutes'}


def parse_step(text: str) -> timedelta:
    """'7d', '2w', '12h', '1d6h' -> timedelta."""
    parts = re.findall(r'(\d+)\s*([wdhm])', text.lower())
    if not parts or ''.join(n + u for n, u in parts) != re.sub(r'\s+', '', text.lower()):
        raise ValueError('use a step like 7d, 2w, 12h or 1d6h')
    return timedelta(**{UNITS[u]: int(n) for n, u in parts})


def autopay_account(store: Store) -> tuple[str, str]:
    """The (bank, type) the user's paychecks are deposited into."""
    first = store.read('deposits.json')[0]
    return first['bank'], first['type']


def paying_order(store: Store, accounts: list[dict]) -> list[dict]:
    """The paycheck account, then other checking, then savings (most cushion above goal first)."""
    home_key = autopay_account(store)
    home = [a for a in accounts if (a['bank'], a['type']) == home_key]
    checking = [a for a in accounts if a['type'] == 'checking' and a not in home]
    savings = sorted((a for a in accounts if a['type'] == 'savings'), key=lambda a: a.get('goal', 0) - a['amount'])
    return home + checking + savings


def settle(store: Store, until: date) -> list[dict]:
    """Pay every unpaid bill due before `until`, oldest first. Returns the ledger entries written."""
    payments = store.read('payments.json')
    due = sorted((p for p in payments if p['status'] == 'unpaid' and date.fromisoformat(p['due']) < until),
                 key=lambda p: (p['due'], p['id']))
    if not due:
        return []
    accounts, deposits, ledger = store.read('accounts.json'), store.read('deposits.json'), store.read('transactions.json')
    entries = []
    for bill in due:
        # Balances as of the bill's due date: paychecks that arrived by then count.
        balance = lambda a: a['amount'] + sum(d['amount'] for d in deposits if d['date'] <= bill['due']
                                              and (d['bank'], d['type']) == (a['bank'], a['type']))
        order = paying_order(store, accounts)
        account = next((a for keeps_goal in (True, False) for a in order
                        if balance(a) - bill['fee'] >= (a.get('goal', 0) if keeps_goal and a['type'] == 'savings' else 0)),
                       order[0])
        account['amount'] = round(account['amount'] - bill['fee'], 2)
        entry = {'confirmation': f'TX-{len(ledger) + 1:04d}', 'bank': account['bank'], 'type': account['type'],
                 'amount': bill['fee'], 'reference': bill['id'], 'date': bill['due'],
                 'timestamp': f'{bill["due"]}T09:00:00', 'source': 'autopay'}
        ledger.append(entry)
        entries.append(entry)
        bill.update(status='paid', paid_on=bill['due'], confirmation=entry['confirmation'])
    store.write('accounts.json', accounts)
    store.write('transactions.json', ledger)
    store.write('payments.json', payments)
    return entries


def move_clock(store: Store, when: datetime) -> dict:
    """Set the clock. Moving forward also settles the days that passed; moving back changes only the clock."""
    previous = store.now()
    result = store.set_now(when)
    paid = settle(store, when.date()) if when.date() > previous.date() else []
    deposits = store.read('deposits.json')
    received = [d for d in deposits if previous.date() < date.fromisoformat(d['date']) <= when.date()]
    accounts = store.read('accounts.json')
    balances = {f'{a["bank"]} {a["type"]}': round(a['amount'] + sum(
        d['amount'] for d in deposits if (d['bank'], d['type']) == (a['bank'], a['type'])
        and date.fromisoformat(d['date']) <= when.date()), 2) for a in accounts}
    goals = {f'{a["bank"]} {a["type"]}': a['goal'] for a in accounts if 'goal' in a}
    return {**result,
            'bills_paid': [{'bill': e['reference'], 'amount': e['amount'], 'due': e['date'],
                            'from': f'{e["bank"]} {e["type"]}'} for e in paid],
            'paid_total': round(sum(e['amount'] for e in paid), 2),
            'paychecks': [{'amount': d['amount'], 'date': d['date']} for d in received],
            'received_total': round(sum(d['amount'] for d in received), 2),
            'overdrawn': [name for name, amount in balances.items() if amount < 0],
            'below_goal': [name for name, goal in goals.items() if balances[name] < goal],
            'went_back': when < previous}
