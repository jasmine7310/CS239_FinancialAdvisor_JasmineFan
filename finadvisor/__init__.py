"""Financial Advisor: a three-agent purchase advisor that runs in one Python process.

Agents (Financial Advisor, Payment Manager, Bank Agent) call their own tools through
ToolBox.call and talk to each other through MessageBus.send. Those two functions are the
application's action boundaries. All financial data is fictional.
"""
