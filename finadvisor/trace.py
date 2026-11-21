"""A run's trajectory: every message, model output, tool call, tool result and clock move, in order."""
from datetime import datetime
import json
from pathlib import Path


class Trace:
    def __init__(self, title: str = ''):
        self.title = title
        self.events: list[dict] = []

    def add(self, kind: str, actor: str, **fields) -> str:
        event = {'id': f'E{len(self.events) + 1:04d}', 'sequence': len(self.events), 'kind': kind,
                 'actor': actor, 'timestamp': datetime.now().astimezone().isoformat(timespec='seconds'),
                 **fields}
        self.events.append(event)
        return event['id']

    def of_kind(self, kind: str) -> list[dict]:
        return [e for e in self.events if e['kind'] == kind]

    def usage(self) -> dict:
        """Total model tokens in this run (for cost tracking)."""
        totals = {'input_tokens': 0, 'output_tokens': 0, 'model_calls': 0}
        for e in self.of_kind('llm_output'):
            totals['model_calls'] += 1
            for key in ('input_tokens', 'output_tokens'):
                totals[key] += (e.get('usage') or {}).get(key, 0)
        return totals

    def to_dict(self) -> dict:
        return {'title': self.title, 'usage': self.usage(), 'events': self.events}

    def save(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str) + '\n', encoding='utf-8')
