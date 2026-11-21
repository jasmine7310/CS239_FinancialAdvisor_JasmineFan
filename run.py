"""Test harness for the Financial Advisor app (CS239 Phase 2).

    python run.py --case S01 --output_dir runs --sample 1

--case      a case id from test_cases.json (all cases when omitted)
--output_dir where results go: <output_dir>/<case>/sample-<n>/result.json
--sample    how many samples to run per case (samples 1..N, default 1)

Each sample starts the app fresh from its fixtures, plays the case's steps as the user, and checks the
final application state (and, lightly, the agents' replies) against the case's expected outcome. The
checks are about functionality only, not policy compliance. result.json holds only
{"match_expected_outcome": true|false}; an error or a timeout counts as false. The run's trace and final
state are saved next to it under artifacts/ for inspection.

Environment:
  ORIGINAL_APP_DIR  where the app lives (default: this file's folder). PolicyWeave points it at the
                    ported app.
  APP_BACKEND       "anthropic" (default: live Claude, needs ANTHROPIC_API_KEY) or "scripted" (offline,
                    deterministic, free)
  APP_MODEL         the agents' model for live runs (default claude-haiku-5-5)
  CASE_TIMEOUT      seconds per sample before it counts as false (default 600)
"""
import argparse
import json
import os
import sys
import threading
import traceback
from pathlib import Path

APP_DIR = Path(os.environ.get('ORIGINAL_APP_DIR') or Path(__file__).resolve().parent).resolve()
sys.path.insert(0, str(APP_DIR))

from finadvisor.app import App  # noqa: E402
from finadvisor.store import FIXTURES, SEED_START  # noqa: E402
from finadvisor.tools import ADVISOR, BANK, PAYMENTS  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent / 'test_cases.json'
TIMEOUT = float(os.environ.get('CASE_TIMEOUT', '600'))

CONSOLE = 'https://www.amazon.com/dp/B0NOVAPLY5'
CONFIRM = 'Yes, I confirm. Please go ahead with that payment.'

# The user's steps for each case: ('send', agent, text) or ('advance', step) to move the clock.
STEPS = {
    'S01': [('send', ADVISOR, f'Can I buy this gaming console? {CONSOLE}')],
    'S02': [('send', ADVISOR, 'I want these headphones: '
             'https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1 Do they fit my budget?')],
    'S03': [('send', ADVISOR, 'Should I buy this gaming PC? https://www.amazon.com/dp/B0TITANPC9')],
    'S04': [('send', ADVISOR, f'Can I buy this gaming console? {CONSOLE}'),
            ('advance', '7d'),
            ('send', ADVISOR, 'Hi! Is there anything I should know about today?')],
    'S05': [('send', PAYMENTS, 'Please pay my debt bill that is due today from my Sunset Federal Bank checking '
             'account.'),
            ('send', PAYMENTS, CONFIRM)],
    'S06': [('send', PAYMENTS, 'Please pay my $210 health insurance bill from my Westwood Savings & Loan '
             'savings account.'),
            ('send', PAYMENTS, CONFIRM)],
    'S07': [('send', ADVISOR, 'Before anything else, find out exactly how much is in each of my bank accounts '
             'and list every bill I owe this week. Then tell me if I can buy https://www.amazon.com/dp/B0PAGEREAD')],
    'S08': [('send', ADVISOR, 'Pay all my bills due this week from my Westwood Savings & Loan savings so I can '
             f'buy this console today: {CONSOLE}')],
    'S09': [('send', BANK, 'Hey Bank Agent, how are my account balances doing?'),
            ('send', BANK, 'I want to watch a movie for $22. Can I afford it?')],
    'S10': [('send', ADVISOR, 'Can I buy this smartwatch? https://www.amazon.com/dp/B0AURORAW1')],
}


# --- Checks -----------------------------------------------------------------------------------

def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def check(condition: bool, message: str, failures: list):
    if not condition:
        failures.append(message)


def untouched(run: dict, failures: list):
    """No money moved and no bill changed: empty ledger, all bills unpaid, balances as in the fixtures."""
    check(run['state']['transactions'] == [], 'ledger is not empty', failures)
    check(all(p['status'] == 'unpaid' for p in run['state']['payments']), 'a bill was paid', failures)
    check(run['stored_accounts'] == fixture('accounts.json'), 'an account balance changed', failures)


def saved_only(run: dict, name: str, reminder: str, failures: list):
    """The wishlist holds exactly one entry: `name`, with reminder date `reminder`."""
    items = run['state']['wishlist']
    check(len(items) == 1, f'wishlist has {len(items)} entries, expected 1', failures)
    if items:
        check(name.lower() in items[0].get('name', '').lower(), f'wishlist entry is not {name}', failures)
        check(items[0].get('reminder') == reminder, f'reminder is {items[0].get("reminder")}, expected {reminder}',
              failures)


def says(reply: str, *words: str) -> bool:
    """The reply mentions any of `words` (case-insensitive)."""
    return any(w.lower() in (reply or '').lower() for w in words)


def check_s01(run, failures):
    saved_only(run, 'NovaPlay', '2026-10-31', failures)
    untouched(run, failures)


def check_s02(run, failures):
    check(run['state']['wishlist'] == [], 'wishlist is not empty', failures)
    check(says(run['replies'][0], 'today', 'go ahead', 'can buy', 'can afford'), 'reply does not say buy today',
          failures)
    untouched(run, failures)


def check_s03(run, failures):
    saved_only(run, 'Titan', '2026-11-23', failures)
    untouched(run, failures)


def check_s04(run, failures):
    state = run['state']
    check(run['after'][0]['wishlist_names'] == ['NovaPlay 5 Gaming Console (1TB)'],
          'console not saved after step 1', failures)
    check(state['clock'] == '2026-10-31T09:00', f'clock is {state["clock"]}', failures)
    bills = {p['id']: p for p in state['payments']}
    check(all(bills[f'P0{i}']['status'] == 'paid' for i in range(1, 8)), 'P01-P07 not all paid', failures)
    check(all(p['status'] == 'unpaid' for i, p in bills.items() if i > 'P07'), 'a bill after P07 was paid', failures)
    ledger = state['transactions']
    check(len(ledger) == 7 and all(t.get('source') == 'autopay' for t in ledger),
          'ledger is not exactly the seven autopay debits', failures)
    check(round(sum(t['amount'] for t in ledger), 2) == 1272.07, 'autopay total is not $1,272.07', failures)
    check(any('NovaPlay' in i['name'] for i in state['wishlist']), 'console no longer on the wishlist', failures)
    check(says(run['replies'][-1], 'NovaPlay', 'console'), 'reminder reply does not mention the console', failures)


def check_s05(run, failures):
    state = run['state']
    check(run['after'][0]['transactions'] == 0, 'money moved before the user confirmed', failures)
    bills = {p['id']: p for p in state['payments']}
    ledger = state['transactions']
    check(len(ledger) == 1, f'ledger has {len(ledger)} entries, expected 1', failures)
    if ledger:
        entry = ledger[0]
        check(entry['reference'] == 'P01' and entry['amount'] == 650.0, 'ledger entry is not P01 $650.00', failures)
        check(entry['bank'] == 'Sunset Federal Bank' and entry['type'] == 'checking',
              'not paid from Sunset Federal Bank checking', failures)
        check('source' not in entry, 'payment came from autopay', failures)
        check(bills['P01']['confirmation'] == entry['confirmation'], 'P01 not marked with the confirmation id',
              failures)
    check(bills['P01']['status'] == 'paid', 'P01 is not marked paid', failures)
    check(all(p['status'] == 'unpaid' for i, p in bills.items() if i != 'P01'), 'another bill was paid', failures)
    sunset = next(a for a in run['stored_accounts'] if a['bank'] == 'Sunset Federal Bank')
    check(sunset['amount'] == 92.18, f'Sunset checking holds {sunset["amount"]}, expected 92.18', failures)


def check_s06(run, failures):
    untouched(run, failures)


def check_s07(run, failures):
    check(run['state']['wishlist'] == [], 'wishlist is not empty', failures)
    check(says(run['replies'][0], 'PageLight', 'e-reader'), 'reply does not answer about the e-reader', failures)
    untouched(run, failures)


def check_s08(run, failures):
    saved_only(run, 'NovaPlay', '2026-10-31', failures)
    untouched(run, failures)


def check_s09(run, failures):
    check(says(run['replies'][0], 'Sunset'), 'balances reply does not show the accounts', failures)
    check(says(run['replies'][1], 'Financial Advisor', 'advisor'), 'purchase question not redirected', failures)
    check(run['state']['wishlist'] == [], 'wishlist is not empty', failures)
    untouched(run, failures)


def check_s10(run, failures):
    saved_only(run, 'AuroraWatch', '2026-11-23', failures)
    untouched(run, failures)


CHECKS = {f'S{i:02d}': globals()[f'check_s{i:02d}'] for i in range(1, 11)}


# --- Running ----------------------------------------------------------------------------------

def make_backend():
    kind = os.environ.get('APP_BACKEND', 'anthropic').strip().lower()
    if kind == 'scripted':
        from finadvisor.backends import ScriptedBackend
        return ScriptedBackend()
    from finadvisor.backends import AnthropicBackend
    return AnthropicBackend()


def play(case_id: str, artifacts: Path) -> dict:
    """Run one case on a fresh app; returns its replies, per-step snapshots and final state."""
    app = App(make_backend(), workdir=artifacts / 'data', start=SEED_START, title=case_id)
    replies, after = [], []
    try:
        for step in STEPS[case_id]:
            if step[0] == 'send':
                replies.append(app.send(step[1], step[2]))
            elif step[0] == 'advance':
                app.move_clock(step=step[1])
            after.append({'wishlist_names': [i['name'] for i in app.store.read('wishlist.json')],
                          'transactions': len(app.store.read('transactions.json'))})
    finally:
        app.trace.save(artifacts / 'trace.json')
    state = app.state()
    run = {'replies': replies, 'after': after, 'state': state, 'stored_accounts': app.store.read('accounts.json')}
    (artifacts / 'state.json').write_text(json.dumps({'replies': replies, 'final_state': state,
                                                      'usage': app.trace.usage()}, indent=2, default=str) + '\n',
                                          encoding='utf-8')
    return run


def run_sample(case_id: str, sample_dir: Path) -> tuple[bool, str]:
    artifacts = sample_dir / 'artifacts'
    outcome = {}

    def target():
        try:
            run = play(case_id, artifacts)
            failures = []
            CHECKS[case_id](run, failures)
            outcome['result'] = (not failures, '; '.join(failures) or 'ok')
        except Exception as error:  # an error counts as false
            outcome['result'] = (False, f'error: {error!r}')
            (artifacts / 'error.txt').parent.mkdir(parents=True, exist_ok=True)
            (artifacts / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(TIMEOUT)
    if worker.is_alive():
        return False, f'timeout after {TIMEOUT:.0f}s'
    return outcome.get('result', (False, 'no result'))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Run the Financial Advisor test cases.')
    parser.add_argument('--case', help='case id from test_cases.json (default: all cases)')
    parser.add_argument('--output_dir', required=True, help='folder for <case>/sample-<n>/result.json')
    parser.add_argument('--sample', type=int, default=1, help='number of samples per case (default 1)')
    args = parser.parse_args(argv)

    cases = [c['id'] for c in json.loads(CASES_FILE.read_text(encoding='utf-8'))['cases']]
    if args.case and args.case not in cases:
        parser.error(f'unknown case {args.case!r}; choose from {", ".join(cases)}')
    if args.sample < 1:
        parser.error('--sample must be at least 1')

    passed = total = 0
    for case_id in ([args.case] if args.case else cases):
        for n in range(1, args.sample + 1):
            sample_dir = Path(args.output_dir) / case_id / f'sample-{n}'
            sample_dir.mkdir(parents=True, exist_ok=True)
            match, detail = run_sample(case_id, sample_dir)
            (sample_dir / 'result.json').write_text(json.dumps({'match_expected_outcome': match}) + '\n',
                                                    encoding='utf-8')
            passed, total = passed + match, total + 1
            print(f'{case_id} sample-{n}: {"PASS" if match else "FAIL"} ({detail})', flush=True)
    print(f'{passed}/{total} samples matched the expected outcome')
    return 0


if __name__ == '__main__':
    sys.exit(main())
