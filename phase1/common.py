"""Shared helpers: data paths, the simulated clock, JSON formats and the tool-call log.

All financial data is fictional. Each agent's MCP server reads only its own files.
"""
from datetime import date, datetime, timedelta
import functools
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get('FINANCE_DATA_DIR', ROOT / 'data'))
TOOL_LOG = Path(os.environ.get('FINANCE_TOOL_LOG', ROOT / 'traces' / 'tool_calls.jsonl'))

# The mock data is anchored to this date so demos stay reproducible.
# Set FINANCE_AS_OF=YYYY-MM-DD (or "today") to move the clock.
DEFAULT_AS_OF = '2026-10-24'
SCOPES = {'day': 0, 'week': 7, 'month': 30}


def today() -> date:
    value = os.environ.get('FINANCE_AS_OF', DEFAULT_AS_OF)
    return date.today() if value == 'today' else date.fromisoformat(value)


def horizon(scope: str) -> date:
    """Last day (inclusive) covered by a scope."""
    if scope not in SCOPES:
        raise ValueError(f'scope must be one of {list(SCOPES)}')
    return today() + timedelta(days=SCOPES[scope])


def clock_note() -> str:
    """Bots must use the demo date, not the real calendar, or they flag the data as stale."""
    return (f'Today is {today().isoformat()}. This is the system\'s demo date (tools report it as as_of); '
            'use it as today and do not compare it with the real calendar. ')


def read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding='utf-8'))


def write_json(name: str, value):
    path = DATA_DIR / name
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def reset_data():
    """Restore every file the agents can change (wishlist, bills, balances, ledger) from data/seed."""
    for seed in sorted((DATA_DIR / 'seed').glob('*.json')):
        (DATA_DIR / seed.name).write_text(seed.read_text(encoding='utf-8'), encoding='utf-8')


def logged(agent: str):
    """Append each tool call (agent, tool, arguments, result) to the shared JSONL log."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            entry = {'ts': datetime.now().isoformat(timespec='milliseconds'),
                     'agent': agent, 'tool': fn.__name__, 'arguments': kwargs}
            try:
                result = fn(*args, **kwargs)
                entry['result'] = result
                return result
            except Exception as exc:
                entry['error'] = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                TOOL_LOG.parent.mkdir(parents=True, exist_ok=True)
                with TOOL_LOG.open('a', encoding='utf-8') as log:
                    log.write(json.dumps(entry, default=str) + '\n')
        return wrapper
    return decorate


# Each agent is told the exact shape of the data it owns, so it never invents a format.
WISHLIST_FORMAT = (
    'Wishlist (data/wishlist.json) is a JSON list of entries: '
    '{"name": item name, "price": number in USD, '
    '"date": "YYYY-MM-DD" the user asked about it, '
    '"timestamp": ISO-8601 time of the user\'s message, '
    '"deduction": why you advised NOT buying it now, '
    '"reminder": "YYYY-MM-DD" from which you allow the user to buy it}.'
)
PAYMENTS_FORMAT = (
    'Payments (data/payments.json) is a JSON list of entries: '
    '{"id": bill id such as "P01", "type": one of rent, loan, debt, utility, subscription, insurance, '
    '"fee": amount owed in USD, "due": "YYYY-MM-DD" due date, "status": "unpaid" or "paid", '
    '"paid_on": "YYYY-MM-DD" or null, "confirmation": Bank Agent\'s confirmation id or null}.'
)
ACCOUNTS_FORMAT = (
    'Accounts (data/accounts.json) is a JSON list of entries: '
    '{"bank": bank name, "type": "checking" or "savings", "amount": balance in USD, '
    '"goal": savings goal in USD (savings accounts only; the balance must not drop below it), '
    '"apy": annual percentage yield as a decimal}. '
    'Deposits (data/deposits.json) is a JSON list of scheduled income: '
    '{"bank": bank name, "type": account type, "amount": USD, "date": "YYYY-MM-DD", "source": description}. '
    'Transactions (data/transactions.json) is a JSON list of debits you made: '
    '{"confirmation": id such as "TX-0001", "bank": bank name, "type": account type, "amount": USD, '
    '"reference": bill id, "date": "YYYY-MM-DD", "timestamp": ISO-8601 time}.'
)
