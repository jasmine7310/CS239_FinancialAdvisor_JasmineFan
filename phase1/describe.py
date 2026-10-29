"""Write description/agents/*.md from the live bot profiles, so each file holds the exact system prompt."""
import asyncio
from pathlib import Path
from . import advisor_server, bank_server, payments_server
from .app import ADVISOR, BANK, DEFAULT_MODELS, PAYMENTS, PORTS, profiles
from .common import ROOT
from .rakazo import ModelConnection

SERVERS = {ADVISOR: advisor_server.server, PAYMENTS: payments_server.server, BANK: bank_server.server}
OWNS = {
    ADVISOR: 'Wishlist (`data/wishlist.json`) and product lookups (`data/products.json`, read-only).',
    PAYMENTS: 'Bills and their paid status (`data/payments.json`).',
    BANK: 'Accounts and savings goals (`data/accounts.json`), scheduled deposits (`data/deposits.json`, '
          'read-only) and the debit ledger (`data/transactions.json`).',
}
FILES = {ADVISOR: 'financial_advisor.md', PAYMENTS: 'payment_manager.md', BANK: 'bank_agent.md'}


def tool_names(name: str) -> list[str]:
    return sorted(t.name for t in asyncio.run(SERVERS[name].list_tools()))


def render(bot) -> str:
    tools = ', '.join(f'`{t}`' for t in tool_names(bot.name))
    return '\n'.join([
        f'# {bot.name}', '',
        f'- **Type:** LLM-based Rakazo bot (model: Anthropic `{DEFAULT_MODELS["anthropic"]}`, '
        'configurable with MODEL_PROVIDER / MODEL_ID).',
        f'- **Tools:** {tools} (its own MCP server at port {PORTS[bot.name]}), plus Rakazo\'s built-in '
        '`message_bot` for messages to the other agents.',
        f'- **Data it owns:** {OWNS[bot.name]}', '',
        '## System prompt', '',
        'The exact instructions this application gives the bot (`phase1/app.py`, `profiles()`), applied with '
        '`python -m phase1.app --apply`. Rakazo places them inside its own built-in system prompt, which '
        'defines how `message_bot` works. The date is the default demo date (`FINANCE_AS_OF`).', '',
        '```text', bot.instructions, '```', '',
    ])


def write(folder: Path = ROOT / 'description' / 'agents') -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    model = ModelConnection('anthropic', DEFAULT_MODELS['anthropic'], '')
    paths = []
    for bot in profiles(model):
        path = folder / FILES[bot.name]
        path.write_text(render(bot), encoding='utf-8')
        paths.append(path)
    return paths


if __name__ == '__main__':
    for path in write():
        print('Wrote', path.relative_to(ROOT))
