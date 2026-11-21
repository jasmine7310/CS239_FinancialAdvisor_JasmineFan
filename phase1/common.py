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
TRACES_DIR = ROOT / 'traces' / 'phase1'  # Phase 2 traces go in traces/phase2

# The simulated clock lives in data/clock.json, shared by all three servers, so the user can move
# time forward (python -m phase1.clock; no agent can) and see reminders come due. run_servers --reset
# shifts the whole scenario so the clock starts on today's real date (or a date given with --start).
# FINANCE_AS_OF=YYYY-MM-DD[THH:MM] (or "today") overrides the file, e.g. in tests.
DEFAULT_NOW = '2026-10-24T09:00:00'
SCOPES = {'day': 0, 'week': 7, 'month': 30}
CLOCK_FILE = 'clock.json'


def parse_when(value: str) -> datetime:
    """'YYYY-MM-DD' (9:00 that day) or 'YYYY-MM-DDTHH:MM[:SS]'."""
    value = value.strip().replace(' ', 'T')
    parsed = datetime.fromisoformat(value)
    return parsed.replace(hour=9, minute=0, second=0) if 'T' not in value else parsed.replace(microsecond=0)


def now() -> datetime:
    override = os.environ.get('FINANCE_AS_OF')
    if override:
        return datetime.now().replace(microsecond=0) if override == 'today' else parse_when(override)
    try:
        return parse_when(read_json(CLOCK_FILE)['now'])
    except (OSError, KeyError, ValueError):
        return parse_when(DEFAULT_NOW)


def today() -> date:
    return now().date()


def set_now(when: datetime) -> dict:
    """Move the shared clock; returns the previous and new time."""
    if os.environ.get('FINANCE_AS_OF'):
        raise ValueError('FINANCE_AS_OF is set, so the clock file is ignored; unset it to move the clock')
    previous = now()
    write_json(CLOCK_FILE, {'now': when.isoformat(timespec='seconds'),
                            'start': start().isoformat(timespec='seconds')})
    return {'previous': previous.isoformat(timespec='seconds'), 'now': when.isoformat(timespec='seconds')}


def start() -> datetime:
    """When this run's scenario begins: the clock's start after the last reset."""
    try:
        return parse_when(read_json(CLOCK_FILE)['start'])
    except (OSError, KeyError, ValueError):
        return parse_when(DEFAULT_NOW)


def horizon(scope: str) -> date:
    """Last day (inclusive) covered by a scope."""
    if scope not in SCOPES:
        raise ValueError(f'scope must be one of {list(SCOPES)}')
    return today() + timedelta(days=SCOPES[scope])


def clock_note() -> str:
    """Bots must use the simulated clock, not the real calendar, or they flag the data as stale."""
    return ('The current date and time come from the system\'s simulated clock, which the user can move '
            'forward to simulate time passing. Use the as_of or now value your tools report as today; '
            'never use the real calendar or a date from earlier messages. Any other date you are given, '
            'including the date in your own system context, is not the user\'s date: the simulated clock '
            'always wins. Never call figures out of date or in the future because of another date, and '
            'do not mention the difference. ')


def read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding='utf-8'))


def write_json(name: str, value):
    path = DATA_DIR / name
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


# Every date in the seed, by file, so a reset can move the whole scenario to another start day.
SEED_START = date(2026, 10, 24)
DATE_FIELDS = {'payments.json': ('due', 'paid_on'), 'deposits.json': ('date',),
               'wishlist.json': ('date', 'timestamp', 'reminder'), 'transactions.json': ('date', 'timestamp'),
               'clock.json': ('now', 'start')}


def shift(value, days: int):
    """Move a YYYY-MM-DD or ISO datetime string by whole days; leave anything else alone."""
    if not isinstance(value, str) or not value:
        return value
    moved = (datetime.fromisoformat(value) if 'T' in value else date.fromisoformat(value)) + timedelta(days=days)
    return moved.isoformat()


def reset_data(start: date | None = None) -> int:
    """Restore every file the agents can change (wishlist, bills, balances, paychecks, ledger, clock)
    from data/seed. With start, shift every date by the same number of days so the simulated clock
    starts that day; bills, paychecks and answers keep their spacing. Returns the shift in days."""
    days = (start - SEED_START).days if start else 0
    for seed in sorted((DATA_DIR / 'seed').glob('*.json')):
        value = json.loads(seed.read_text(encoding='utf-8'))
        fields = DATE_FIELDS.get(seed.name, ())
        if days and fields:
            for row in (value if isinstance(value, list) else [value]):
                for name in fields:
                    if name in row:
                        row[name] = shift(row[name], days)
        write_json(seed.name, value)
    return days


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
    '"timestamp": ISO-8601 simulated time of the user\'s message, '
    '"deduction": why you advised NOT buying it now, '
    '"reminder": "YYYY-MM-DD" from which you allow the user to buy it and remind them}.'
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
    'Transactions (data/transactions.json) is a JSON list of debits: '
    '{"confirmation": id such as "TX-0001", "bank": bank name, "type": account type, "amount": USD, '
    '"reference": bill id, "date": "YYYY-MM-DD", "timestamp": ISO-8601 time, '
    '"source": "autopay" when the bill was paid automatically as the user moved the clock forward, '
    'absent when you paid it with debit_account}.'
)
