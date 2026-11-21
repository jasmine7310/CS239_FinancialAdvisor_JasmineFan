"""One run's data: a private copy of fixtures/ plus the simulated clock.

Every run works on its own folder, so runs never share or leak state. The fixtures are dated
from 2026-10-24; a store can start on another day, which shifts every date by the same amount.
"""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures'
SEED_START = date(2026, 10, 24)
SCOPES = {'day': 0, 'week': 7, 'month': 30}
# Every date in the fixtures, by file, so a run can start on another day.
DATE_FIELDS = {'payments.json': ('due', 'paid_on'), 'deposits.json': ('date',),
               'wishlist.json': ('date', 'timestamp', 'reminder'), 'transactions.json': ('date', 'timestamp'),
               'clock.json': ('now', 'start')}


def parse_when(value: str) -> datetime:
    """'YYYY-MM-DD' (9:00 that day) or 'YYYY-MM-DDTHH:MM[:SS]'."""
    value = value.strip().replace(' ', 'T')
    parsed = datetime.fromisoformat(value)
    return parsed.replace(hour=9, minute=0, second=0) if 'T' not in value else parsed.replace(microsecond=0)


def shift(value, days: int):
    """Move a YYYY-MM-DD or ISO datetime string by whole days; leave anything else alone."""
    if not isinstance(value, str) or not value:
        return value
    moved = (datetime.fromisoformat(value) if 'T' in value else date.fromisoformat(value)) + timedelta(days=days)
    return moved.isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def fresh(cls, root: Path | None = None, start: date | None = None) -> 'Store':
        """Copy the fixtures into `root` (a new temporary folder by default), starting on `start`."""
        root = Path(root) if root else Path(tempfile.mkdtemp(prefix='finadvisor-'))
        root.mkdir(parents=True, exist_ok=True)
        store = cls(root)
        days = (start - SEED_START).days if start else 0
        for fixture in sorted(FIXTURES.glob('*.json')):
            value = json.loads(fixture.read_text(encoding='utf-8'))
            for row in (value if isinstance(value, list) else [value]):
                for name in DATE_FIELDS.get(fixture.name, ()) if days else ():
                    if name in row:
                        row[name] = shift(row[name], days)
            store.write(fixture.name, value)
        return store

    def read(self, name: str):
        return json.loads((self.root / name).read_text(encoding='utf-8'))

    def write(self, name: str, value):
        (self.root / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

    # The simulated clock. Only the user moves it (simulator.move_clock); agents can only read it.
    def now(self) -> datetime:
        return parse_when(self.read('clock.json')['now'])

    def start(self) -> datetime:
        return parse_when(self.read('clock.json')['start'])

    def today(self) -> date:
        return self.now().date()

    def horizon(self, scope: str) -> date:
        """Last day (inclusive) covered by a scope."""
        if scope not in SCOPES:
            raise ValueError(f'scope must be one of {list(SCOPES)}')
        return self.today() + timedelta(days=SCOPES[scope])

    def set_now(self, when: datetime) -> dict:
        previous = self.now()
        self.write('clock.json', {'now': when.isoformat(timespec='seconds'),
                                  'start': self.start().isoformat(timespec='seconds')})
        return {'previous': previous.isoformat(timespec='seconds'), 'now': when.isoformat(timespec='seconds')}
