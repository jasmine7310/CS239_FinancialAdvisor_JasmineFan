"""Call the three MCP servers yourself, before involving any LLM.

Walks the purchase and payment workflows with a script in place of the agents, on a
temporary copy of the starting data (data/seed), so the real data and tool log are untouched.
"""
import asyncio
from contextlib import AsyncExitStack
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
LINKS = {
    'console': 'https://www.amazon.com/dp/B0NOVAPLY5',
    'headphones': 'https://www.amazon.com/Wavelength-Wireless-Headphones/dp/B0WAVEHP01?th=1',
    'gaming_pc': 'https://www.amazon.com/dp/B0TITANPC9',
}


def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))
    return result.structured_content or json.loads(result.content[0].text)


def decide(checks):
    """The Financial Advisor's timing rule: buy at the earliest point after which every check passes."""
    ok = {s: checks[s]['above_threshold'] for s in ('day', 'week', 'month')}
    if all(ok.values()):
        return 'buy today'
    if ok['week'] and ok['month']:
        return 'wait about a week'
    if ok['month']:
        return 'wait about a month'
    return 'do not buy now; add to wishlist'


async def connect(stack, module, env):
    params = StdioServerParameters(command=sys.executable, args=['-m', f'phase1.{module}'],
                                   cwd=str(ROOT), env=env)
    read, write = await stack.enter_async_context(stdio_client(params))
    client = await stack.enter_async_context(ClientSession(read, write))
    await client.initialize()
    return client


async def demo():
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(ROOT / 'data', Path(folder) / 'data')
        # Start from the seed (unpaid bills, original balances), whatever live runs have changed.
        for seed in (ROOT / 'data' / 'seed').glob('*.json'):
            shutil.copy(seed, Path(folder) / 'data' / seed.name)
        env = {**os.environ, 'FINANCE_DATA_DIR': str(Path(folder) / 'data'),
               'FINANCE_TOOL_LOG': str(Path(folder) / 'tool_calls.jsonl')}
        async with AsyncExitStack() as stack:
            advisor = await connect(stack, 'advisor_server', env)
            payments = await connect(stack, 'payments_server', env)
            bank = await connect(stack, 'bank_server', env)
            for name, client in [('Financial Advisor', advisor), ('Payment Manager', payments),
                                 ('Bank Agent', bank)]:
                print(f'{name} tools:', [t.name for t in (await client.list_tools()).tools])

            fees = {s: unpack(await payments.call_tool('get_upcoming_fees', {'scope': s}))['total']
                    for s in ('day', 'week', 'month')}
            totals = unpack(await bank.call_tool('get_projected_totals', {}))['projected_total']
            print('\nFees due (Payment Manager):', fees)
            print('Projected totals (Bank Agent):', totals)
            chart = unpack(await payments.call_tool('spending_chart', {'scope': 'month'}))
            print('Spending by type this month:', chart['by_type'])

            for label, url in LINKS.items():
                product = unpack(await advisor.call_tool('lookup_product', {'url': url}))
                projected = unpack(await advisor.call_tool('project_balances', {
                    'price': product['price'],
                    **{f'fees_{s}': fees[s] for s in fees},
                    **{f'total_{s}': totals[s] for s in totals}}))['remaining']
                checks = unpack(await bank.call_tool('check_savings_threshold', projected))['checks']
                verdict = decide(checks)
                print(f'\n{label}: {product["name"]} ${product["price"]}')
                print('  remaining after fees + price:', projected)
                print('  above threshold:', {s: c['above_threshold'] for s, c in checks.items()})
                print('  advice:', verdict)
                if verdict.startswith('do not'):
                    saved = unpack(await advisor.call_tool('add_to_wishlist', {
                        'name': product['name'], 'price': product['price'],
                        'deduction': 'Buying it would push savings below the goal within 30 days.'}))
                    print('  wishlist entry:', saved['saved'])

            missing = unpack(await advisor.call_tool('lookup_product',
                                                     {'url': 'https://www.amazon.com/dp/B0UNKNOWN0'}))
            print('\nUnknown link:', missing['status'])

            # Paying a bill: Payment Manager records it, but only Bank Agent moves money.
            bills = unpack(await payments.call_tool('list_unpaid_bills', {}))['bills']
            print(f'\nUnpaid bills: {len(bills)}; first: {bills[0]}')

            async def debit(bank, kind, amount, reference):
                result = unpack(await bank_client.call_tool('debit_account', {
                    'bank': bank, 'account_type': kind, 'amount': amount, 'reference': reference}))
                return result.get('confirmation') or result['reason']

            bank_client = bank
            paid = await debit('Sunset Federal Bank', 'checking', 650.00, 'P01')
            print('Pay P01 ($650 debt) from Sunset checking:', paid)
            print('Mark P01 paid:', unpack(await payments.call_tool(
                'mark_bill_paid', {'bill_id': 'P01', 'confirmation': paid}))['paid']['status'])
            print('Day fees after paying:',
                  unpack(await payments.call_tool('get_upcoming_fees', {'scope': 'day'}))['total'])
            print('Day total after paying:',
                  unpack(await bank.call_tool('get_projected_totals', {}))['projected_total']['day'])
            print('Pay P01 again:', await debit('Sunset Federal Bank', 'checking', 650.00, 'P01'))
            again = await payments.call_tool('mark_bill_paid', {'bill_id': 'P01', 'confirmation': 'TX-0009'})
            print('Mark P01 paid again: error =', again.is_error)
            print('Pay P15 ($210) from Westwood savings:',
                  await debit('Westwood Savings & Loan', 'savings', 210.00, 'P15'))
            print('Pay P09 ($1850 rent) from Bruin checking:',
                  await debit('Bruin Credit Union', 'checking', 1850.00, 'P09'))
            print('Pay from an unknown account:', await debit('Fake Bank', 'checking', 10.00, 'P03'))
            print('Debit with no bill id:', await debit('Sunset Federal Bank', 'checking', 10.00, 'gift'))


if __name__ == '__main__':
    asyncio.run(demo())
