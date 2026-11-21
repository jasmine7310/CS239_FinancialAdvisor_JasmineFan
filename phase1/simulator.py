"""The world outside the agents: time passing.

Moving the simulated clock forward stands for the user living through those days. Paychecks
count as received once the clock reaches their date (bank_server adds them when reading), and
every bill due before the new date is paid by autopay: from the account the paychecks go into
when it can, otherwise other checking, then savings (keeping savings goals when possible).
Each payment is recorded in the ledger like any other debit (source "autopay"). This is the
simulator acting for the user, not an agent: agents move money only through debit_account.
"""
from datetime import date, datetime
from .common import now, read_json, set_now, write_json


def autopay_account() -> tuple[str, str]:
    """The (bank, type) the user's paychecks are deposited into."""
    first = read_json('deposits.json')[0]
    return first['bank'], first['type']


def paying_order(accounts: list[dict]) -> list[dict]:
    """Autopay draws on the paycheck account, then other checking, then savings (most cushion first)."""
    bank, kind = autopay_account()
    home = [a for a in accounts if (a['bank'], a['type']) == (bank, kind)]
    checking = [a for a in accounts if a['type'] == 'checking' and a not in home]
    savings = sorted((a for a in accounts if a['type'] == 'savings'),
                     key=lambda a: a.get('goal', 0) - a['amount'])
    return home + checking + savings


def choose_account(accounts: list[dict], fee: float, received: callable) -> dict:
    """The first account (in paying order) that covers the bill without breaking a savings goal;
    else the first that covers it at all; else the paycheck account, which goes overdrawn."""
    order = paying_order(accounts)
    balance = lambda a: a['amount'] + received(a)
    for keeps_goal in (True, False):
        for a in order:
            floor = a.get('goal', 0) if keeps_goal and a['type'] == 'savings' else 0
            if balance(a) - fee >= floor:
                return a
    return order[0]


def settle(until: date) -> list[dict]:
    """Pay every unpaid bill due before `until`, oldest first. Returns the ledger entries written."""
    payments = read_json('payments.json')
    due = sorted((p for p in payments if p['status'] == 'unpaid' and date.fromisoformat(p['due']) < until),
                 key=lambda p: (p['due'], p['id']))
    if not due:
        return []
    accounts = read_json('accounts.json')
    deposits = read_json('deposits.json')
    ledger = read_json('transactions.json')
    entries = []
    for bill in due:
        # Balances as of the bill's due date: paychecks that arrived by then count.
        received = lambda a: sum(d['amount'] for d in deposits if (d['bank'], d['type']) == (a['bank'], a['type'])
                                 and d['date'] <= bill['due'])
        account = choose_account(accounts, bill['fee'], received)
        account['amount'] = round(account['amount'] - bill['fee'], 2)
        entry = {'confirmation': f'TX-{len(ledger) + 1:04d}', 'bank': account['bank'], 'type': account['type'],
                 'amount': bill['fee'], 'reference': bill['id'], 'date': bill['due'],
                 'timestamp': f'{bill["due"]}T09:00:00', 'source': 'autopay'}
        ledger.append(entry)
        entries.append(entry)
        bill.update(status='paid', paid_on=bill['due'], confirmation=entry['confirmation'])
    write_json('accounts.json', accounts)
    write_json('transactions.json', ledger)
    write_json('payments.json', payments)
    return entries


def move_clock(when: datetime) -> dict:
    """Set the shared clock. Moving forward also settles the days that passed: paychecks in that
    span arrive, and bills due before the new date are paid. Moving back changes only the clock."""
    previous = now()
    result = set_now(when)
    paid = settle(when.date()) if when.date() > previous.date() else []
    received = [d for d in read_json('deposits.json')
                if previous.date() < date.fromisoformat(d['date']) <= when.date()]
    deposits = read_json('deposits.json')
    accounts = read_json('accounts.json')
    balances = {f'{a["bank"]} {a["type"]}': round(a['amount'] + sum(
        d['amount'] for d in deposits if (d['bank'], d['type']) == (a['bank'], a['type'])
        and date.fromisoformat(d['date']) <= when.date()), 2) for a in accounts}
    goals = {f'{a["bank"]} {a["type"]}': a['goal'] for a in accounts if 'goal' in a}
    return {**result, 'bills_paid': [(e['reference'], e['amount'], e['date'], f'{e["bank"]} {e["type"]}')
                                     for e in paid],
            'paid_total': round(sum(e['amount'] for e in paid), 2),
            'paychecks': [(d['amount'], d['date']) for d in received],
            'received_total': round(sum(d['amount'] for d in received), 2),
            'overdrawn': [name for name, amount in balances.items() if amount < 0],
            'below_goal': [name for name, goal in goals.items() if balances[name] < goal],
            'went_back': when < previous}
