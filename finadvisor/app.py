"""The application: one run's data, trace, tools, message bus and three agents."""
from datetime import date
from pathlib import Path
from . import prompts, simulator, tools
from .agents import Agent
from .bus import USER, MessageBus
from .store import Store, parse_when
from .trace import Trace

ALIASES = {'fa': tools.ADVISOR, 'advisor': tools.ADVISOR, 'pm': tools.PAYMENTS, 'payments': tools.PAYMENTS,
           'bank': tools.BANK}


class App:
    def __init__(self, backend, workdir: Path | None = None, start: date | None = None, title: str = ''):
        self.store = Store.fresh(workdir, start)
        self.trace = Trace(title)
        self.toolbox = tools.ToolBox(self.store, self.trace)
        self.bus = MessageBus(self.trace, prompts.CAN_MESSAGE)
        self.agents = {}
        for name in tools.AGENTS:
            definitions = tools.definitions(name)
            message_tool = prompts.message_tool(name)
            agent = Agent(name, prompts.SYSTEM[name], definitions + ([message_tool] if message_tool else []),
                          backend, self.toolbox, self.bus, self.trace)
            self.agents[name] = agent
            self.bus.register(agent)

    def send(self, agent: str, text: str) -> str:
        """The user sends `text` to an agent; returns the agent's reply."""
        agent = ALIASES.get(agent.lower(), agent)
        result = self.bus.send(USER, agent, text)
        return result.get('reply', result.get('error', ''))

    def move_clock(self, when: str | None = None, step: str | None = None) -> dict:
        """The user moves time (a date/time, or a step like '7d'). Not available to agents."""
        target = parse_when(when) if when else self.store.now() + simulator.parse_step(step)
        moved = simulator.move_clock(self.store, target)
        self.trace.add('state', USER, data={'clock': moved})
        return moved

    def state(self) -> dict:
        """The final application state, for checks against expected outcomes."""
        accounts = tools.current_accounts(self.store)
        return {'clock': self.store.now().isoformat(timespec='minutes'),
                'wishlist': self.store.read('wishlist.json'),
                'payments': self.store.read('payments.json'),
                'accounts': accounts,
                'total_money': round(sum(a['amount'] for a in accounts), 2),
                'transactions': self.store.read('transactions.json')}
