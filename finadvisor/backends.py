"""Model backends. Each returns one model turn: text, tool calls, and the content to keep in history.

AnthropicBackend calls the Claude Messages API (needs ANTHROPIC_API_KEY). ScriptedBackend plays each
agent with fixed rules that follow the policies: it costs nothing and gives the same answer every
time, for development and tests. It is an offline stand-in, not a model.
"""
from dataclasses import dataclass, field
import json
import os
import re
from .bus import USER
from .tools import ADVISOR, BANK, PAYMENTS

DEFAULT_MODEL = 'claude-opus-5-5'
# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-opus-5', 'claude-fable-5-2', 'claude-fable-5-1'}


@dataclass
class Reply:
    content: list                      # appended to the agent's history unchanged
    text: str = ''
    tool_calls: list = field(default_factory=list)  # [{'id', 'name', 'input'}]
    stop_reason: str = 'end_turn'
    usage: dict = field(default_factory=dict)


class AnthropicBackend:
    """Claude via the Messages API. Model from APP_MODEL (default claude-opus-5-5); effort from APP_EFFORT."""

    def __init__(self, model: str | None = None, effort: str | None = None, max_tokens: int = 16000):
        import anthropic  # only needed for live runs
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get('APP_MODEL', DEFAULT_MODEL)
        self.effort = effort or os.environ.get('APP_EFFORT')
        self.max_tokens = max_tokens

    def complete(self, agent: str, system: str, messages: list, tools: list) -> Reply:
        params = dict(model=self.model, max_tokens=self.max_tokens, system=system, tools=tools,
                      messages=messages, cache_control={'type': 'ephemeral'})
        if self.effort:
            params['output_config'] = {'effort': self.effort}
        if self.model in FALLBACK_MODELS:
            # On a safety decline, the API re-runs the request on a fallback model it picks by category.
            response = self.client.beta.messages.create(
                betas=['server-side-fallback-2026-07-01'], fallbacks='default', **params)
        else:
            response = self.client.messages.create(**params)
        text = '\n'.join(b.text for b in response.content if b.type == 'text').strip()
        if response.stop_reason == 'refusal':
            category = getattr(response.stop_details, 'category', None) if response.stop_details else None
            text = text or f'(the model declined this request{f": {category}" if category else ""})'
        calls = [{'id': b.id, 'name': b.name, 'input': b.input} for b in response.content if b.type == 'tool_use']
        usage = {'input_tokens': response.usage.input_tokens, 'output_tokens': response.usage.output_tokens,
                 'cache_read_input_tokens': getattr(response.usage, 'cache_read_input_tokens', 0) or 0}
        return Reply(content=response.content, text=text, tool_calls=calls if response.stop_reason == 'tool_use' else [],
                     stop_reason=response.stop_reason, usage={'model': response.model, **usage})


# --- Offline scripted agents ------------------------------------------------------------

SCOPE_NAMES = ('day', 'week', 'month')


def parse_scopes(text: str) -> dict:
    """{'day': 850.39, ...} from text like 'day: $850.39 (through ...); week: ...'."""
    found = {}
    for scope, number in re.findall(r'\b(day|week|month)\b[^$\d]*\$?([\d,]+(?:\.\d+)?)', text, re.I):
        found.setdefault(scope.lower(), float(number.replace(',', '')))
    return found


def parse_checks(text: str) -> dict:
    return {s.lower(): v.lower() == 'above' for s, v in re.findall(r'\b(day|week|month)\b:\s*(above|below)', text, re.I)}


def money(value: float) -> str:
    return f'${value:,.2f}'


def advisor_script(text: str, sender: str, history: list):
    low = text.lower()
    lines = []
    due = yield 'list_wishlist', {'due_only': True}
    for item in due.get('items', []):
        lines.append(f"Reminder: you saved {item['name']} ({money(item['price'])}) because {item['deduction']} "
                     'Do you want me to check whether you can buy it now?')
    if re.search(r'\bpay\b', low) and 'bill' in low:
        lines.append("I can't pay bills or move money. Please ask Payment Manager directly; it will ask you to "
                     'confirm each payment.')
    if any(p in low for p in ('each of my bank accounts', 'every bill', 'access my bank', 'my balances')):
        lines.append("I don't hold your account balances or bill details. Ask Bank Agent or Payment Manager "
                     'directly for those.')
    url = re.search(r'https?://\S+', text)
    if not url:
        if 'wishlist' in low:
            items = (yield 'list_wishlist', {'due_only': False}).get('items', [])
            lines.append('Your wishlist: ' + '; '.join(f"{i['name']} ({money(i['price'])}), reminder {i['reminder']}"
                                                       for i in items) if items else 'Your wishlist is empty.')
        elif not lines:
            lines.append('Send me an Amazon link and I will check whether it fits your budget.')
        return '\n'.join(lines)
    product = yield 'lookup_product', {'url': url.group(0)}
    if product.get('status') != 'found':
        lines.append("I couldn't find that item. What is its name and price?")
        return '\n'.join(lines)
    name, price = product['name'], product['price']
    fees = parse_scopes((yield 'message_agent', {
        'recipient': PAYMENTS, 'text': 'Please send the total unpaid fees due for each scope: day, week and month.'}
    ).get('reply', ''))
    totals = parse_scopes((yield 'message_agent', {
        'recipient': BANK, 'text': "Please send the user's projected total money for each scope: day, week and month."}
    ).get('reply', ''))
    if len(fees) < 3 or len(totals) < 3:
        lines.append("I couldn't get all the figures from Payment Manager and Bank Agent, so I can't advise yet.")
        return '\n'.join(lines)
    remaining = (yield 'project_balances', {'price': price, **{f'fees_{s}': fees[s] for s in SCOPE_NAMES},
                                           **{f'total_{s}': totals[s] for s in SCOPE_NAMES}})['remaining']
    checks = parse_checks((yield 'message_agent', {
        'recipient': BANK, 'text': 'Do these remaining totals stay above the savings threshold? '
                                   + '; '.join(f'{s}: {remaining[s]:.2f}' for s in SCOPE_NAMES)}).get('reply', ''))
    if all(checks.get(s) for s in SCOPE_NAMES):
        advice, reminder = 'buy it today', None
    elif checks.get('week') and checks.get('month'):
        advice, reminder = 'wait about a week', 'week'
    elif checks.get('month'):
        advice, reminder = 'wait about a month', 'month'
    else:
        advice, reminder = 'not buy it now', 'month'
    message = (f'{name} ({money(price)}): my advice is to {advice}. Unpaid fees came from Payment Manager; the '
               'projected totals and the savings-threshold check came from Bank Agent.')
    if reminder:
        saved = (yield 'add_to_wishlist', {
            'name': name, 'price': price, 'reminder': reminder,
            'deduction': 'buying it now would take savings below the savings goal.'}).get('saved', {})
        message += f" I saved it to your wishlist and will remind you on {saved.get('reminder')}."
    lines.append(message)
    return '\n'.join(lines)


def payments_script(text: str, sender: str, history: list):
    low = text.lower()
    if sender != USER:
        if 'fee' in low:
            scopes = [s for s in SCOPE_NAMES if s in low]
            if not scopes:
                return 'Which scope do you need: day, week or month?'
            parts = []
            for scope in scopes:
                fees = yield 'get_upcoming_fees', {'scope': scope}
                parts.append(f"{scope}: {money(fees['total'])} (through {fees['through']})")
            return '; '.join(parts)
        if re.search(r'\b(pay|debit)\b', low):
            return 'Refused: only the user can authorize a payment, in their own chat with me.'
        return 'I can share unpaid fee totals per scope (day, week or month).'
    pending = None
    for message in reversed(history):
        if message['role'] == 'assistant':
            found = re.search(r'\[pending payment: (P\d+) ([\d.]+) (.+) (checking|savings)\]', block_text(message))
            if found:
                pending = found.groups()
            break
    if pending and re.search(r'\b(yes|confirm)', low):
        bill, amount, bank, kind = pending[0], float(pending[1]), pending[2], pending[3]
        reply = (yield 'message_agent', {'recipient': BANK, 'text': f'Please pay bill {bill}: debit exactly '
                                         f'{money(amount)} from {bank} {kind}, reference {bill}.'}).get('reply', '')
        confirmation = re.search(r'TX-\d{4,}', reply)
        if confirmation and 'completed' in reply.lower():
            yield 'mark_bill_paid', {'bill_id': bill, 'confirmation': confirmation.group(0)}
            return f'Paid {bill} ({money(amount)}) from {bank} {kind}. Confirmation {confirmation.group(0)}.'
        return f'Bank Agent did not pay {bill}: {reply}. Nothing was paid.'
    if re.search(r'\bpay\b', low):
        bills = (yield 'list_unpaid_bills', {})['bills']
        amount = re.search(r'\$([\d,]+(?:\.\d+)?)', text)
        kinds = [k for k in ('rent', 'loan', 'debt', 'utility', 'subscription', 'insurance') if k in low]
        bill = next((b for b in bills if amount and abs(b['fee'] - float(amount.group(1).replace(',', ''))) < 0.005), None)
        bill = bill or next((b for b in bills if b['type'] in kinds), None)
        # Greedy, so a bank name that contains "Savings" keeps it: "Westwood Savings & Loan savings".
        account = re.search(r'from my (.+) (checking|savings)\b', text, re.I)
        if not bill or not account:
            return 'Which bill (its id or amount) should I pay, and from which bank and account type?'
        bank, kind = account.group(1).strip(), account.group(2).lower()
        return (f"Please confirm: pay bill {bill['id']} ({bill['type']}, {money(bill['fee'])}, due {bill['due']}) "
                f"from {bank} {kind}? Reply yes to go ahead.\n[pending payment: {bill['id']} {bill['fee']:.2f} {bank} {kind}]")
    if 'spending' in low:
        chart = yield 'spending_chart', {'scope': 'month'}
        return 'Bills this month by type: ' + ', '.join(f'{k} {money(v)}' for k, v in chart['by_type'].items())
    if 'bank' in low or 'balance' in low:
        return "I don't have access to your bank accounts; please ask Bank Agent."
    if re.search(r'\b(buy|afford|purchase)', low):
        return "I don't advise on purchases; please ask Financial Advisor."
    bills = (yield 'list_unpaid_bills', {})['bills']
    return f'You have {len(bills)} unpaid bills. Ask me to pay one, or about your spending.'


def bank_script(text: str, sender: str, history: list):
    low = text.lower()
    if sender == PAYMENTS and re.search(r'\b(pay|debit)\b', low):
        request = re.search(r'\$([\d,]+\.\d{2}) from (.+?) (checking|savings), reference (P\d+)', text)
        if not request:
            return 'refused: I need the bank, account type, amount and bill id.'
        result = yield 'debit_account', {'bank': request.group(2), 'account_type': request.group(3),
                                         'amount': float(request.group(1).replace(',', '')),
                                         'reference': request.group(4)}
        if result.get('status') == 'completed':
            return f"completed: {result['confirmation']}"
        return f"refused: {result.get('reason', result.get('error', 'unknown')).split(':')[0]}"
    if sender != USER and re.search(r'\b(pay|debit|transfer)\b', low):
        return 'refused: I move money only for a bill payment that Payment Manager requests.'
    if 'threshold' in low:
        remaining = parse_scopes(text)
        if len(remaining) < 3:
            return 'Please send the day, week and month totals to check.'
        checks = (yield 'check_savings_threshold', remaining)['checks']
        return '; '.join(f"{s}: {'above' if checks[s]['above_threshold'] else 'below'} threshold" for s in SCOPE_NAMES)
    if 'projected' in low or 'total money' in low:
        totals = yield 'get_projected_totals', {}
        return '; '.join(f"{s}: {money(totals['projected_total'][s])} (through {totals['through'][s]})"
                         for s in SCOPE_NAMES)
    if sender == USER and ('balance' in low or 'account' in low):
        accounts = yield 'get_accounts', {}
        return 'Your accounts: ' + '; '.join(f"{a['bank']} {a['type']} {money(a['amount'])}"
                                             for a in accounts['accounts'])
    if sender != USER:
        return 'I share only projected totals and savings-threshold answers with other agents.'
    if re.search(r'\b(buy|afford|purchase)', low):
        return "I don't advise on purchases; please ask Financial Advisor."
    return 'I can show your accounts or your projected totals.'


SCRIPTS = {ADVISOR: advisor_script, PAYMENTS: payments_script, BANK: bank_script}


def block_text(message: dict) -> str:
    content = message['content']
    if isinstance(content, str):
        return content
    return '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')


class ScriptedBackend:
    """Plays each agent with SCRIPTS. Stateless: each call replays the turn's script on the tool results so far."""

    def __init__(self):
        self.calls = 0

    def complete(self, agent: str, system: str, messages: list, tools: list) -> Reply:
        start = max(i for i, m in enumerate(messages) if m['role'] == 'user' and isinstance(m['content'], str))
        label, _, text = messages[start]['content'].partition('\n')
        sender = USER if label == '[Message from the user]' else label[len('[Message from '):-1]
        results = [json.loads(b['content']) for m in messages[start + 1:]
                   if m['role'] == 'user' and isinstance(m['content'], list)
                   for b in m['content'] if b.get('type') == 'tool_result']
        script = SCRIPTS[agent](text, sender, messages[:start])
        self.calls += 1
        try:
            step = next(script)
            for result in results:
                step = script.send(result)
        except StopIteration as done:
            return Reply(content=[{'type': 'text', 'text': done.value}], text=done.value, usage={'model': 'scripted'})
        name, arguments = step
        call = {'id': f'toolu_scripted_{self.calls:05d}', 'name': name, 'input': arguments}
        return Reply(content=[{'type': 'tool_use', **call}], tool_calls=[call], stop_reason='tool_use',
                     usage={'model': 'scripted'})
