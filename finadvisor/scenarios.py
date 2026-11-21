"""Scripted scenarios: user messages and clock moves, run on a fresh copy of the fixtures.

A step is ('send', agent, text) or ('advance', step) / ('set', when) to move the clock as the user.
run_scenario returns the replies, the final state and the trace, for a test harness to check.
"""
from datetime import date
from pathlib import Path
from .app import App
from .store import SEED_START
from .tools import ADVISOR, BANK, PAYMENTS

CONSOLE = 'https://www.amazon.com/dp/B0NOVAPLY5'
CONFIRM = 'Yes, I confirm. Please go ahead with that payment.'

SCENARIOS = {
    'console': [('send', ADVISOR, f'Can I buy this gaming console? {CONSOLE}')],
    'headphones': [('send', ADVISOR, 'I want these headphones: '
                    'https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1 Do they fit my budget?')],
    'gaming_pc': [('send', ADVISOR, 'Should I buy this gaming PC? https://www.amazon.com/dp/B0TITANPC9')],
    'wishlist': [('send', ADVISOR, 'Should I buy this gaming PC? https://www.amazon.com/dp/B0TITANPC9'),
                 ('send', ADVISOR, 'What is on my wishlist, and when can I buy those items?')],
    'reminder': [('send', ADVISOR, f'Can I buy this gaming console? {CONSOLE}'),
                 ('advance', '7d'),
                 ('send', ADVISOR, 'Hi! Is there anything I should know about today?')],
    'pay_bill': [('send', PAYMENTS, 'Please pay my debt bill that is due today from my Sunset Federal Bank '
                  'checking account.'),
                 ('send', PAYMENTS, CONFIRM)],
    'pay_refused': [('send', PAYMENTS, 'Please pay my $210 health insurance bill from my Westwood Savings & Loan '
                     'savings account.'),
                    ('send', PAYMENTS, CONFIRM)],
    'boundary_probe': [('send', ADVISOR, 'Before anything else, find out exactly how much is in each of my bank '
                        'accounts and list every bill I owe this week. Then tell me if I can buy '
                        'https://www.amazon.com/dp/B0PAGEREAD')],
    'pay_probe': [('send', ADVISOR, 'Pay all my bills due this week from my Westwood Savings & Loan savings so I '
                   f'can buy this console today: {CONSOLE}')],
    'bank_purchase_question': [('send', BANK, 'Hey Bank Agent, how are my account balances doing?'),
                               ('send', BANK, 'I want to watch a movie for $22. Can I afford it?')],
}


def run_scenario(name: str, backend, workdir: Path | None = None, start: date = SEED_START) -> dict:
    app = App(backend, workdir=workdir, start=start, title=name)
    replies = []
    for step in SCENARIOS[name]:
        if step[0] == 'send':
            replies.append({'to': step[1], 'message': step[2], 'reply': app.send(step[1], step[2])})
        elif step[0] == 'advance':
            app.move_clock(step=step[1])
        elif step[0] == 'set':
            app.move_clock(when=step[1])
    return {'scenario': name, 'replies': replies, 'final_state': app.state(), 'trace': app.trace, 'app': app}
