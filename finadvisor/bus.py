"""MessageBus.send: the one place every message between agents goes through.

The bus, not the sender, labels who a message is from, so a recipient always knows whether a
request came from the user or from another agent. A send runs the recipient's turn and returns its
reply to the sender, like a function call.
"""


USER = 'user'


class MessageBus:
    def __init__(self, trace, can_message: dict[str, list[str]]):
        self.trace = trace
        self.can_message = can_message  # which agents each agent may message; the user may message any
        self.agents = {}

    def register(self, agent):
        self.agents[agent.name] = agent

    def send(self, sender: str, recipient: str, text: str) -> dict:
        allowed = list(self.agents) if sender == USER else self.can_message.get(sender, [])
        if recipient not in self.agents or recipient not in allowed:
            return {'error': f'{sender} cannot message {recipient!r}'
                             + (f' (allowed: {", ".join(allowed)})' if allowed else '')}
        agent = self.agents[recipient]
        if agent.busy:
            # The recipient is waiting on this very exchange; a reply would loop back into itself.
            return {'error': f'{recipient} is in the middle of its own request and cannot take another'}
        sent = self.trace.add('message', sender, recipients=[recipient], content=text)
        reply = agent.run_turn(text, sender=sender)
        self.trace.add('message', recipient, recipients=[sender], content=reply, in_reply_to=sent)
        return {'from': recipient, 'reply': reply}
