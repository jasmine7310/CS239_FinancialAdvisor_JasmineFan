"""Tests for the app: tools, the two action boundaries, time passing, and every scenario end to end.

Run from the repository root:  python -m unittest discover tests -v
They use the free ScriptedBackend: no model, network or API key. Each test runs on its own fresh
copy of the fixtures.
"""
from datetime import date
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finadvisor import prompts, tools  # noqa: E402
from finadvisor.app import App  # noqa: E402
from finadvisor.backends import ScriptedBackend  # noqa: E402
from finadvisor.scenarios import SCENARIOS, run_scenario  # noqa: E402
from finadvisor.simulator import move_clock, parse_step  # noqa: E402
from finadvisor.store import Store, parse_when  # noqa: E402
from finadvisor.tools import ADVISOR, BANK, PAYMENTS  # noqa: E402

CONSOLE, HEADPHONES, PC = ('https://www.amazon.com/dp/B0NOVAPLY5',
                           'https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1',
                           'https://www.amazon.com/dp/B0TITANPC9')


def advise(store: Store, url: str) -> str:
    """The purchase timing rule computed straight from the tools."""
    price = tools.lookup_product(store, url=url)['price']
    fees = {s: tools.get_upcoming_fees(store, scope=s)['total'] for s in ('day', 'week', 'month')}
    totals = tools.get_projected_totals(store)['projected_total']
    remaining = tools.project_balances(store, price=price, **{f'fees_{s}': v for s, v in fees.items()},
                                       **{f'total_{s}': v for s, v in totals.items()})['remaining']
    ok = {s: c['above_threshold'] for s, c in tools.check_savings_threshold(store, **remaining)['checks'].items()}
    if all(ok.values()):
        return 'today'
    if ok['week'] and ok['month']:
        return 'week'
    return 'month' if ok['month'] else 'not now'


def scripted(name: str) -> dict:
    return run_scenario(name, ScriptedBackend())


class StoreAndClock(unittest.TestCase):
    def test_fixtures_start_on_the_seed_date(self):
        store = Store.fresh()
        self.assertEqual(store.now().isoformat(), '2026-10-24T09:00:00')
        self.assertEqual(len(store.read('payments.json')), 20)
        self.assertEqual(store.read('wishlist.json'), [])
        self.assertEqual(sorted(a['type'] for a in store.read('accounts.json')), ['checking'] * 2 + ['savings'] * 3)

    def test_start_day_shifts_every_date_but_not_the_answers(self):
        store = Store.fresh(start=date(2026, 11, 20))
        self.assertEqual(store.now().isoformat(), '2026-11-20T09:00:00')
        self.assertEqual(store.read('payments.json')[0]['due'], '2026-11-20')
        self.assertEqual(store.read('deposits.json')[0]['date'], '2026-11-26')
        self.assertEqual((advise(store, CONSOLE), advise(store, HEADPHONES), advise(store, PC)),
                         ('week', 'today', 'not now'))

    def test_runs_do_not_share_data(self):
        a, b = Store.fresh(), Store.fresh()
        tools.add_to_wishlist(a, name='x', price=1, deduction='y')
        self.assertEqual(b.read('wishlist.json'), [])

    def test_parse_step(self):
        self.assertEqual(parse_step('1d6h').total_seconds(), 30 * 3600)
        with self.assertRaises(ValueError):
            parse_step('7 days')


class Tools(unittest.TestCase):
    def setUp(self):
        self.store = Store.fresh()

    def test_purchase_outcomes(self):
        self.assertEqual((advise(self.store, CONSOLE), advise(self.store, HEADPHONES), advise(self.store, PC)),
                         ('week', 'today', 'not now'))

    def test_wishlist_reminders(self):
        saved = tools.add_to_wishlist(self.store, name='NovaPlay 5', price=499.99, deduction='d', reminder='week')
        self.assertEqual(saved['saved']['reminder'], '2026-10-31')
        again = tools.add_to_wishlist(self.store, name='novaplay 5', price=499.99, deduction='d', reminder='month')
        self.assertEqual((again['updated'], again['wishlist_size']), (True, 1))
        with self.assertRaises(ValueError):
            tools.add_to_wishlist(self.store, name='a', price=1, deduction='x', reminder='2026-10-01')

    def test_debit_refusals(self):
        debit = lambda bank, kind, amount, ref: tools.debit_account(self.store, bank=bank, account_type=kind,
                                                                    amount=amount, reference=ref)
        self.assertEqual(debit('Sunset Federal Bank', 'checking', 650, 'P01')['confirmation'], 'TX-0001')
        self.assertTrue(debit('Sunset Federal Bank', 'checking', 650, 'P01')['reason'].startswith('duplicate'))
        self.assertTrue(debit('Westwood Savings & Loan', 'savings', 210, 'P15')['reason'].startswith('below_savings_goal'))
        self.assertTrue(debit('Bruin Credit Union', 'checking', 1850, 'P09')['reason'].startswith('insufficient'))
        self.assertTrue(debit('Fake Bank', 'checking', 10, 'P03')['reason'].startswith('account_not_found'))
        self.assertTrue(debit('Sunset Federal Bank', 'checking', 10, 'gift')['reason'].startswith('invalid_request'))

    def test_mark_paid_needs_a_confirmation_id(self):
        with self.assertRaises(ValueError):
            tools.mark_bill_paid(self.store, bill_id='P01', confirmation='ok')


class Boundaries(unittest.TestCase):
    """P1, P2, P15: who may call which tool and message whom, enforced in code."""

    def setUp(self):
        self.app = App(ScriptedBackend())

    def test_toolbox_refuses_another_agents_tool(self):
        result = self.app.toolbox.call(ADVISOR, 'debit_account', {'bank': 'Sunset Federal Bank',
                                       'account_type': 'checking', 'amount': 10, 'reference': 'P03'})
        self.assertIn('PermissionError', result['error'])
        self.assertEqual(self.app.store.read('transactions.json'), [])

    def test_only_bank_moves_money_and_no_agent_moves_time(self):
        owners = {name: agent for agent, table in tools.TOOLS.items() for name in table}
        self.assertEqual(owners['debit_account'], BANK)
        every_tool = {t['name'] for a in self.app.agents.values() for t in a.tools}
        self.assertFalse(every_tool & {'set_clock', 'move_clock', 'advance_clock'})

    def test_bus_enforces_who_may_message_whom(self):
        self.assertIn('error', self.app.bus.send(BANK, PAYMENTS, 'hello'))        # Bank only replies
        self.assertIn('error', self.app.bus.send(PAYMENTS, ADVISOR, 'hello'))     # PM may message only Bank
        self.assertIn('reply', self.app.bus.send(ADVISOR, PAYMENTS, 'Please send the fees for day.'))
        self.assertEqual([t['name'] for t in self.app.agents[BANK].tools if t['name'] == 'message_agent'], [])

    def test_bus_labels_the_sender(self):
        self.app.bus.send(ADVISOR, PAYMENTS, 'Please send the fees for day.')
        self.assertTrue(self.app.agents[PAYMENTS].messages[0]['content'].startswith('[Message from Financial Advisor]'))
        self.app.send('pm', 'hi')
        incoming = [m['content'] for m in self.app.agents[PAYMENTS].messages
                    if m['role'] == 'user' and isinstance(m['content'], str)]
        self.assertTrue(incoming[-1].startswith('[Message from the user]\nhi'))

    def test_prompts_carry_the_policies(self):
        for agent, policy in [(ADVISOR, prompts.ADVISOR_POLICY), (PAYMENTS, prompts.PAYMENTS_POLICY),
                              (BANK, prompts.BANK_POLICY)]:
            self.assertIn(policy, prompts.SYSTEM[agent])
            self.assertIn('the simulated clock always wins', prompts.SYSTEM[agent])


class TimePassing(unittest.TestCase):
    """P2, P13, P15: moving the clock forward receives paychecks and autopays past bills."""

    def test_a_week_passes(self):
        store = Store.fresh()
        moved = move_clock(store, parse_when('2026-10-31'))
        self.assertEqual([b['bill'] for b in moved['bills_paid']], ['P01', 'P02', 'P03', 'P04', 'P05', 'P06', 'P07'])
        self.assertEqual((moved['paid_total'], moved['received_total'], moved['overdrawn']), (1272.07, 1650.0, []))
        self.assertEqual({e['source'] for e in store.read('transactions.json')}, {'autopay'})
        fees = tools.get_upcoming_fees(store, scope='day')
        self.assertEqual((fees['total'], fees['overdue_count']), (39.99, 0))
        self.assertEqual(advise(store, CONSOLE), 'month')  # rent on 11-01 is now inside the week

    def test_rent_comes_from_savings_without_overdraft(self):
        store = Store.fresh()
        moved = move_clock(store, parse_when('2026-11-02'))
        self.assertEqual(next(b['from'] for b in moved['bills_paid'] if b['bill'] == 'P09'),
                         'Westwood Savings & Loan savings')
        self.assertEqual(moved['overdrawn'], [])
        self.assertIn('Westwood Savings & Loan savings', moved['below_goal'])

    def test_moving_back_settles_nothing(self):
        store = Store.fresh()
        move_clock(store, parse_when('2026-10-31'))
        paid = len(store.read('transactions.json'))
        self.assertTrue(move_clock(store, parse_when('2026-10-25'))['went_back'])
        self.assertEqual(len(store.read('transactions.json')), paid)


class Scenarios(unittest.TestCase):
    """Every scenario end to end with the scripted agents: replies, final state and trace."""

    def test_console_waits_a_week_and_saves_a_reminder(self):
        r = scripted('console')
        self.assertIn('wait about a week', r['replies'][0]['reply'])
        self.assertEqual([(w['name'], w['reminder']) for w in r['final_state']['wishlist']],
                         [('NovaPlay 5 Gaming Console (1TB)', '2026-10-31')])
        # Only numbers crossed to the other agents: never the item or its price (P7).
        sent = [e['content'] for e in r['trace'].of_kind('message')
                if e['actor'] == ADVISOR and e['recipients'] != ['user']]
        self.assertTrue(sent and not any('NovaPlay' in m or '499.99' in m for m in sent))

    def test_headphones_buy_today(self):
        r = scripted('headphones')
        self.assertIn('buy it today', r['replies'][0]['reply'])
        self.assertEqual(r['final_state']['wishlist'], [])

    def test_gaming_pc_not_now(self):
        r = scripted('gaming_pc')
        self.assertIn('not buy it now', r['replies'][0]['reply'])
        self.assertEqual(r['final_state']['wishlist'][0]['reminder'], '2026-11-23')

    def test_wishlist_lists_items(self):
        self.assertIn('Titan RTX Gaming Desktop', scripted('wishlist')['replies'][1]['reply'])

    def test_reminder_after_a_week(self):
        r = scripted('reminder')
        self.assertIn('Reminder: you saved NovaPlay 5', r['replies'][1]['reply'])
        self.assertEqual(r['final_state']['clock'], '2026-10-31T09:00')

    def test_pay_bill_needs_confirmation_then_pays_once(self):
        r = scripted('pay_bill')
        self.assertIn('Please confirm: pay bill P01', r['replies'][0]['reply'])
        self.assertIn('Confirmation TX-0001', r['replies'][1]['reply'])
        paid = [p for p in r['final_state']['payments'] if p['status'] == 'paid']
        self.assertEqual([(p['id'], p['confirmation']) for p in paid], [('P01', 'TX-0001')])

    def test_pay_refused_moves_nothing(self):
        r = scripted('pay_refused')
        self.assertIn('below_savings_goal', r['replies'][1]['reply'])
        self.assertEqual(r['final_state']['transactions'], [])

    def test_probes_are_redirected(self):
        self.assertIn("don't hold your account balances", scripted('boundary_probe')['replies'][0]['reply'])
        probe = scripted('pay_probe')
        self.assertIn("can't pay bills", probe['replies'][0]['reply'])
        self.assertEqual(probe['final_state']['transactions'], [])
        bank = scripted('bank_purchase_question')
        self.assertIn('Your accounts', bank['replies'][0]['reply'])          # the user may see their own accounts
        self.assertIn("don't advise on purchases", bank['replies'][1]['reply'])

    def test_every_scenario_runs_and_is_traced(self):
        for name in SCENARIOS:
            trace = scripted(name)['trace']
            ids = [e['id'] for e in trace.events]
            self.assertEqual(len(ids), len(set(ids)), name)
            self.assertTrue(trace.of_kind('message'), name)
            for call in trace.of_kind('tool_call'):
                self.assertTrue(re.match(r'E\d{4}', call['id']))


if __name__ == '__main__':
    unittest.main()
