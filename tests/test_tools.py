"""Tests for the tools, data, policies the tools enforce, and the submission descriptions.

Run from the folder that contains tests/:  python -m unittest discover tests -v
No LLM, Rakazo or network is needed. Every test runs on a temporary copy of the starting data.
"""
import asyncio
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent / 'src' if (HERE.parent / 'src' / 'phase1').exists() else HERE.parent
sys.path.insert(0, str(CODE))

# Point the tools at a scratch copy of the data before they are imported.
SCRATCH = Path(tempfile.mkdtemp())
shutil.copytree(CODE / 'data', SCRATCH / 'data', ignore=shutil.ignore_patterns('charts'))
os.environ['FINANCE_DATA_DIR'] = str(SCRATCH / 'data')
os.environ['FINANCE_TOOL_LOG'] = str(SCRATCH / 'tool_calls.jsonl')
os.environ.pop('FINANCE_AS_OF', None)

from phase1 import advisor_server as fa, bank_server as bank, payments_server as pm  # noqa: E402
from phase1.app import PAYMENTS_POLICY, BANK_POLICY, ADVISOR_POLICY, profiles  # noqa: E402
from phase1.common import TOOL_LOG, read_json, reset_data  # noqa: E402
from phase1.rakazo import ModelConnection  # noqa: E402

CONSOLE, HEADPHONES, PC = ('https://www.amazon.com/dp/B0NOVAPLY5',
                           'https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1',
                           'https://www.amazon.com/dp/B0TITANPC9')


def tools_of(module):
    return {t.name for t in asyncio.run(module.server.list_tools())}


def advise(url):
    """The purchase workflow with a script standing in for the three LLM agents."""
    product = fa.lookup_product(url=url)
    fees = {s: pm.get_upcoming_fees(scope=s)['total'] for s in ('day', 'week', 'month')}
    totals = bank.get_projected_totals()['projected_total']
    remaining = fa.project_balances(price=product['price'], **{f'fees_{s}': v for s, v in fees.items()},
                                    **{f'total_{s}': v for s, v in totals.items()})['remaining']
    ok = {s: c['above_threshold'] for s, c in bank.check_savings_threshold(**remaining)['checks'].items()}
    if all(ok.values()):
        return 'today'
    if ok['week'] and ok['month']:
        return 'week'
    return 'month' if ok['month'] else 'not now'


class Base(unittest.TestCase):
    def setUp(self):
        reset_data()


class StartingData(Base):
    def test_starting_data_matches_spec(self):
        accounts = read_json('accounts.json')
        self.assertEqual(read_json('wishlist.json'), [])
        self.assertEqual(len(read_json('payments.json')), 20)
        self.assertEqual(sorted(a['type'] for a in accounts), ['checking'] * 2 + ['savings'] * 3)
        self.assertTrue(all('goal' in a for a in accounts if a['type'] == 'savings'))
        self.assertFalse(any('goal' in a for a in accounts if a['type'] == 'checking'))
        self.assertTrue(all(p['status'] == 'unpaid' for p in read_json('payments.json')))
        self.assertEqual(read_json('transactions.json'), [])

    def test_reset_restores_seed(self):
        fa.add_to_wishlist(name='Thing', price=1, deduction='test')
        bank.debit_account(bank='Sunset Federal Bank', account_type='checking', amount=650, reference='P01')
        reset_data()
        self.assertEqual(read_json('wishlist.json'), [])
        self.assertEqual(read_json('transactions.json'), [])
        self.assertEqual(read_json('accounts.json')[0]['amount'], 742.18)


class ToolInventory(Base):
    """P1: each agent's server exposes only that agent's tools; tools.md lists exactly these."""

    def test_each_server_exposes_only_its_tools(self):
        self.assertEqual(tools_of(fa), {'lookup_product', 'project_balances', 'list_wishlist',
                                        'add_to_wishlist', 'remove_from_wishlist'})
        self.assertEqual(tools_of(pm), {'get_upcoming_fees', 'list_unpaid_bills', 'mark_bill_paid',
                                        'spending_chart'})
        self.assertEqual(tools_of(bank), {'get_accounts', 'get_projected_totals',
                                          'check_savings_threshold', 'debit_account'})

    def test_tools_md_matches_implementation(self):
        listed = set(re.findall(r'^([a-z_]+): ', (CODE / 'description' / 'tools.md').read_text(encoding='utf-8'),
                                re.MULTILINE))
        self.assertEqual(listed, tools_of(fa) | tools_of(pm) | tools_of(bank) | {'message_bot'})


class PurchaseAdvice(Base):
    """P10: the timing rule gives the three designed outcomes on the starting data."""

    def test_console_wait_a_week(self):
        self.assertEqual(advise(CONSOLE), 'week')

    def test_headphones_buy_today(self):
        self.assertEqual(advise(HEADPHONES), 'today')

    def test_gaming_pc_not_now(self):
        self.assertEqual(advise(PC), 'not now')

    def test_unknown_link_asks_for_price(self):
        self.assertEqual(fa.lookup_product(url='https://www.amazon.com/dp/B0UNKNOWN0')['status'], 'not_found')

    def test_project_balances_math(self):
        result = fa.project_balances(price=10, fees_day=1, fees_week=2, fees_month=3,
                                     total_day=100, total_week=200, total_month=300)
        self.assertEqual(result['remaining'], {'day': 89, 'week': 188, 'month': 287})

    def test_projected_totals_include_deposits_and_interest(self):
        result = bank.get_projected_totals()
        self.assertEqual(result['expected_deposits'], {'day': 0, 'week': 1650.0, 'month': 3300.0})
        self.assertTrue(all(v > 0 for v in result['expected_interest'].values()))
        self.assertEqual(result['through'], {'day': '2026-10-24', 'week': '2026-10-31', 'month': '2026-11-23'})


class Wishlist(Base):
    """P14: wishlist format, default reminder, removal."""

    def test_add_list_remove(self):
        saved = fa.add_to_wishlist(name='Titan RTX Gaming Desktop', price=2899, deduction='Over budget')['saved']
        self.assertEqual(set(saved), {'name', 'price', 'date', 'timestamp', 'deduction', 'reminder'})
        self.assertEqual((saved['date'], saved['reminder']), ('2026-10-24', '2026-11-23'))
        self.assertEqual(fa.list_wishlist(due_only=True)['items'], [])
        self.assertEqual(len(fa.list_wishlist()['items']), 1)
        self.assertEqual(fa.remove_from_wishlist(name='titan rtx gaming desktop')['removed'], 1)

    def test_due_reminders(self):
        fa.add_to_wishlist(name='Due', price=5, deduction='x', reminder='2026-10-24')
        self.assertEqual([i['name'] for i in fa.list_wishlist(due_only=True)['items']], ['Due'])

    def test_rejects_invalid_entries(self):
        for bad in [dict(name='', price=1, deduction='x'), dict(name='a', price=-1, deduction='x'),
                    dict(name='a', price=1, deduction=' ')]:
            with self.assertRaises(ValueError):
                fa.add_to_wishlist(**bad)


class Payments(Base):
    """P2, P8, P12, P13: only debit_account moves money; refusals change nothing; bills are paid once."""

    def pay(self, bank_name, kind, amount, ref):
        return bank.debit_account(bank=bank_name, account_type=kind, amount=amount, reference=ref)

    def test_pay_bill_end_to_end(self):
        result = self.pay('Sunset Federal Bank', 'checking', 650.00, 'P01')
        self.assertEqual((result['status'], result['confirmation']), ('completed', 'TX-0001'))
        self.assertEqual(read_json('accounts.json')[0]['amount'], 92.18)
        self.assertEqual(read_json('transactions.json')[0]['reference'], 'P01')
        self.assertEqual(pm.mark_bill_paid(bill_id='P01', confirmation='TX-0001')['paid']['status'], 'paid')
        self.assertEqual(pm.get_upcoming_fees(scope='day')['total'], 200.39)
        self.assertEqual(advise(CONSOLE), 'week')  # paying a bill lowers fees and balance equally

    def assert_refused(self, result, reason):
        self.assertEqual(result['status'], 'refused')
        self.assertTrue(result['reason'].startswith(reason), result['reason'])
        self.assertEqual(read_json('transactions.json'), [])

    def test_debit_refuses_below_savings_goal(self):
        before = read_json('accounts.json')
        self.assert_refused(self.pay('Westwood Savings & Loan', 'savings', 210.00, 'P15'), 'below_savings_goal')
        self.assertEqual(read_json('accounts.json'), before)

    def test_debit_refuses_insufficient_funds(self):
        self.assert_refused(self.pay('Bruin Credit Union', 'checking', 1850.00, 'P09'), 'insufficient_funds')

    def test_debit_refuses_unknown_account(self):
        self.assert_refused(self.pay('Fake Bank', 'checking', 10, 'P03'), 'account_not_found')

    def test_debit_refuses_non_bill_reference(self):
        self.assert_refused(self.pay('Sunset Federal Bank', 'checking', 10, 'gift'), 'invalid_request')
        self.assert_refused(self.pay('Sunset Federal Bank', 'checking', -5, 'P03'), 'invalid_request')

    def test_bill_paid_only_once(self):
        self.pay('Sunset Federal Bank', 'checking', 650.00, 'P01')
        pm.mark_bill_paid(bill_id='P01', confirmation='TX-0001')
        again = self.pay('Sunset Federal Bank', 'checking', 650.00, 'P01')
        self.assertEqual((again['status'], again['reason'].split(':')[0]), ('refused', 'duplicate_reference'))
        with self.assertRaises(ValueError):
            pm.mark_bill_paid(bill_id='P01', confirmation='TX-0002')

    def test_mark_paid_requires_bank_confirmation_format(self):
        for bad in ['', 'ok', 'TX-1', 'paid']:
            with self.assertRaises(ValueError):
                pm.mark_bill_paid(bill_id='P02', confirmation=bad)
        with self.assertRaises(ValueError):
            pm.mark_bill_paid(bill_id='P99', confirmation='TX-0001')

    def test_fees_count_unpaid_overdue_bills(self):
        os.environ['FINANCE_AS_OF'] = '2026-10-26'
        try:
            day = pm.get_upcoming_fees(scope='day')
        finally:
            os.environ.pop('FINANCE_AS_OF')
        self.assertEqual(day['overdue_count'], 3)
        self.assertEqual(day['total'], 946.59)  # P01-P03 overdue + P04 due 10-26


class SpendingChart(Base):
    def test_chart_written(self):
        result = pm.spending_chart(scope='month')
        self.assertTrue(Path(result['chart']).exists())
        self.assertAlmostEqual(sum(result['share'].values()), 1, places=2)


class Logging(Base):
    """P16: every tool call is logged with agent, tool, arguments and result."""

    def test_tool_calls_logged(self):
        start = TOOL_LOG.read_text(encoding='utf-8').count('\n') if TOOL_LOG.exists() else 0
        bank.get_accounts()
        last = TOOL_LOG.read_text(encoding='utf-8').splitlines()[start]
        self.assertIn('"agent": "Bank Agent"', last)
        self.assertIn('"tool": "get_accounts"', last)
        self.assertIn('"result"', last)


class Prompts(Base):
    """The prompts carry the prompt-level policies and the demo date; agent files hold the exact prompts."""

    def setUp(self):
        super().setUp()
        self.bots = {b.name: b for b in profiles(ModelConnection('anthropic', 'claude-opus-5-5', ''))}

    def test_prompts_carry_policies_and_date(self):
        for bot, policy in [('Financial Advisor', ADVISOR_POLICY), ('Payment Manager', PAYMENTS_POLICY),
                            ('Bank Agent', BANK_POLICY)]:
            self.assertIn(policy, self.bots[bot].instructions)
            self.assertTrue(self.bots[bot].instructions.startswith('Today is 2026-10-24.'))
        self.assertIn('never reuse figures', self.bots['Financial Advisor'].instructions)
        self.assertIn('Only after the user clearly confirms', self.bots['Payment Manager'].instructions)

    def test_agent_files_hold_exact_prompts(self):
        files = {'Financial Advisor': 'financial_advisor.md', 'Payment Manager': 'payment_manager.md',
                 'Bank Agent': 'bank_agent.md'}
        for bot, name in files.items():
            text = (CODE / 'description' / 'agents' / name).read_text(encoding='utf-8')
            self.assertIn(self.bots[bot].instructions, text, f'{name} is stale: run python -m phase1.describe')


class TraceExport(unittest.TestCase):
    """export_traces --session: every message in a chat, across Rakazo's pages, scripted or typed."""

    def fake_rakazo(self):
        from phase1.rakazo import Rakazo
        app = Rakazo('http://127.0.0.1:1')
        msg = lambda seq, text, t: {'id': f'm{seq}', 'seq': seq, 'role': 'user',
                                    'blocks': [{'kind': 'text', 'text': text}],
                                    'createdAt': f'2026-10-25T20:0{t}:00Z'}
        app.conversation = lambda bot_id: {'threadId': 't', 'messages': [msg(4, 'typed in UI', 4), msg(5, 'reply', 5)],
                                           'olderCursor': 4}
        pages = {4: {'messages': [msg(2, 'scripted --send', 2), msg(3, 'x', 3)], 'olderCursor': 2},
                 2: {'messages': [msg(1, 'first', 1), msg(2, 'scripted --send', 2)], 'olderCursor': None}}
        app.rpc = lambda route, data: pages[data['before']]
        return app

    def test_full_conversation_follows_pages(self):
        with self.fake_rakazo() as app:
            thread = app.full_conversation('bot')
        self.assertEqual([m['seq'] for m in thread['messages']], [1, 2, 3, 4, 5])

    def test_session_export_includes_scripted_and_typed(self):
        from phase1.export_traces import parse_time, render, session_run
        with self.fake_rakazo() as app:
            threads = {'Financial Advisor': app.full_conversation('bot')}
        run = session_run('session_test', threads)
        self.assertEqual(parse_time(run['started_at']), parse_time('2026-10-25T20:01:00Z'))
        text = render(run, threads, [], parse_time(run['started_at']))
        self.assertIn('scripted --send', text)
        self.assertIn('typed in UI', text)


class Descriptions(Base):
    def test_policy_file_format(self):
        text = (CODE / 'policy.md').read_text(encoding='utf-8')
        numbers = [int(n) for n in re.findall(r'^P(\d+)\. ', text, re.MULTILINE)]
        self.assertGreaterEqual(len(numbers), 3)
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        # One paragraph per policy, separated by blank lines.
        self.assertTrue(all(re.match(r'P\d+\. ', block) for block in text.strip().split('\n\n')))

    def test_episodes_cite_existing_policies(self):
        count = len(re.findall(r'^P\d+\. ', (CODE / 'policy.md').read_text(encoding='utf-8'), re.MULTILINE))
        for episode in (CODE / 'description' / 'episodes').glob('*.md'):
            cited = {int(n) for n in re.findall(r'\bP(\d+)\b', episode.read_text(encoding='utf-8'))}
            self.assertTrue(cited, episode.name)
            self.assertLessEqual(max(cited), count, episode.name)


if __name__ == '__main__':
    unittest.main()
