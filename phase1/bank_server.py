"""Bank Agent's MCP server: accounts, projected totals, the savings-threshold check and bill debits.

The savings threshold is the sum of every savings account's goal. debit_account is the only
tool in the system that changes a balance.
"""
import argparse
from datetime import date, datetime
import re
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from .common import SCOPES, horizon, logged, read_json, today, write_json

server = MCPServer('Bank Agent')
log = logged('Bank Agent')
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                            idempotent_hint=True, open_world_hint=False)


def savings_threshold(accounts: list[dict]) -> float:
    return round(sum(a.get('goal', 0) for a in accounts if a['type'] == 'savings'), 2)


@server.tool(annotations=READ_ONLY)
@log
def get_accounts() -> dict:
    """Every account with its balance, savings goal and APY, plus the savings threshold."""
    accounts = read_json('accounts.json')
    return {'as_of': today().isoformat(), 'accounts': accounts,
            'current_total': round(sum(a['amount'] for a in accounts), 2),
            'savings_threshold': savings_threshold(accounts)}


@server.tool(annotations=READ_ONLY)
@log
def get_projected_totals() -> dict:
    """Total money across all accounts at the end of each scope (day, week, month),
    including scheduled deposits and expected interest."""
    accounts = read_json('accounts.json')
    deposits = read_json('deposits.json')
    current = sum(a['amount'] for a in accounts)
    result = {'as_of': today().isoformat(), 'current_total': round(current, 2),
              'through': {s: horizon(s).isoformat() for s in SCOPES},
              'expected_deposits': {}, 'expected_interest': {}, 'projected_total': {}}
    for scope, days in SCOPES.items():
        incoming = sum(d['amount'] for d in deposits
                       if today() <= date.fromisoformat(d['date']) <= horizon(scope))
        interest = sum(a['amount'] * a.get('apy', 0) * max(days, 1) / 365 for a in accounts)
        result['expected_deposits'][scope] = round(incoming, 2)
        result['expected_interest'][scope] = round(interest, 2)
        result['projected_total'][scope] = round(current + incoming + interest, 2)
    return result


@server.tool(annotations=READ_ONLY)
@log
def check_savings_threshold(day: float, week: float, month: float) -> dict:
    """Check whether each remaining total (after purchase and fees) stays at or above the savings threshold."""
    threshold = savings_threshold(read_json('accounts.json'))
    remaining = {'day': day, 'week': week, 'month': month}
    return {'savings_threshold': threshold,
            'checks': {s: {'remaining': v, 'above_threshold': v >= threshold}
                       for s, v in remaining.items()}}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         idempotent_hint=False, open_world_hint=False))
@log
def debit_account(bank: str, account_type: str, amount: float, reference: str) -> dict:
    """Pay a bill by debiting one account. reference is the bill id (e.g. P01).
    Refuses an unknown account, a non-bill reference, a bill already paid, insufficient funds,
    or a debit that would drop a savings account below its goal."""
    def refused(reason):
        return {'status': 'refused', 'reason': reason, 'reference': reference}

    amount = round(amount, 2)
    reference = reference.strip().upper()
    if amount <= 0 or not re.fullmatch(r'P\d{2,}', reference):
        return refused('invalid_request: amount must be positive and reference a bill id like P01')
    ledger = read_json('transactions.json')
    if any(t['reference'] == reference for t in ledger):
        return refused('duplicate_reference: this bill was already paid')
    accounts = read_json('accounts.json')
    account = next((a for a in accounts if a['bank'].lower() == bank.strip().lower()
                    and a['type'] == account_type.strip().lower()), None)
    if account is None:
        return refused('account_not_found')
    if amount > account['amount']:
        return refused('insufficient_funds')
    if account['type'] == 'savings' and account['amount'] - amount < account.get('goal', 0):
        return refused('below_savings_goal')
    account['amount'] = round(account['amount'] - amount, 2)
    entry = {'confirmation': f'TX-{len(ledger) + 1:04d}', 'bank': account['bank'],
             'type': account['type'], 'amount': amount, 'reference': reference,
             'date': today().isoformat(), 'timestamp': datetime.now().isoformat(timespec='seconds')}
    write_json('accounts.json', accounts)
    write_json('transactions.json', ledger + [entry])
    return {'status': 'completed', 'confirmation': entry['confirmation'], 'reference': reference,
            'amount': amount}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--port', type=int, default=8773)
    args = parser.parse_args()
    if args.http:
        server.run(transport='streamable-http', host='0.0.0.0', port=args.port)
    else:
        server.run(transport='stdio')
