"""An agent: a system prompt, its own tools, and a loop that runs model calls until it replies.

Every tool call goes to ToolBox.call and every message to MessageBus.send; the agent never touches
data or other agents directly.
"""
import json
from .bus import USER


class Agent:
    def __init__(self, name: str, system: str, tools: list[dict], backend, toolbox, bus, trace, max_steps: int = 14):
        self.name, self.system, self.tools = name, system, tools
        self.backend, self.toolbox, self.bus, self.trace = backend, toolbox, bus, trace
        self.max_steps = max_steps
        self.messages: list[dict] = []   # this agent's whole conversation, user and agent requests alike
        self.busy = False

    def run_turn(self, text: str, sender: str = USER) -> str:
        """Handle one incoming message and return this agent's reply."""
        label = 'the user' if sender == USER else sender
        self.messages.append({'role': 'user', 'content': f'[Message from {label}]\n{text}'})
        self.busy = True
        try:
            for _ in range(self.max_steps):
                reply = self.backend.complete(self.name, self.system, self.messages, self.tools)
                self.messages.append({'role': 'assistant', 'content': reply.content})
                self.trace.add('llm_output', self.name, result=reply.text, stop_reason=reply.stop_reason,
                               tool_calls=[{'tool': c['name'], 'arguments': c['input']} for c in reply.tool_calls],
                               usage=reply.usage)
                if not reply.tool_calls:
                    return reply.text or f'({self.name} gave no reply: {reply.stop_reason})'
                results = []
                for call in reply.tool_calls:
                    result = self.dispatch(call['name'], call['input'])
                    results.append({'type': 'tool_result', 'tool_use_id': call['id'],
                                    'content': json.dumps(result, default=str),
                                    **({'is_error': True} if 'error' in result else {})})
                self.messages.append({'role': 'user', 'content': results})
            self.trace.add('error', self.name, result=f'stopped after {self.max_steps} model calls')
            return f'({self.name} stopped after {self.max_steps} steps without a final reply)'
        finally:
            self.busy = False

    def dispatch(self, tool: str, arguments: dict) -> dict:
        if tool == 'message_agent':
            return self.bus.send(self.name, str(arguments.get('recipient', '')), str(arguments.get('text', '')))
        return self.toolbox.call(self.name, tool, arguments)
