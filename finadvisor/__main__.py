"""Run the app.

    python -m finadvisor chat                 talk to the agents (Claude; needs ANTHROPIC_API_KEY)
    python -m finadvisor chat --scripted      the same with the free offline scripted agents
    python -m finadvisor scenario console     run a scripted scenario and save its trace
    python -m finadvisor list                 list the scenarios

In chat, start a line with "fa:", "pm:" or "bank:" to choose who you talk to (default: the last one,
starting with the Financial Advisor). Commands: /advance 7d, /set 2026-10-31, /state, /usage, /quit.
Moving the clock is yours alone: no agent can do it.
"""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
from .app import ALIASES, App
from .backends import AnthropicBackend, ScriptedBackend
from .scenarios import SCENARIOS, run_scenario
from .tools import ADVISOR

RUNS = Path(__file__).resolve().parents[1] / 'sessions'  # chat and scenario output (runs/ is for the graded harness)


def backend(args):
    return ScriptedBackend() if args.scripted else AnthropicBackend(model=args.model)


def print_clock(moved: dict):
    print(f"[clock] {moved['previous']} -> {moved['now']}")
    for p in moved['paychecks']:
        print(f"  paycheck received: ${p['amount']:,.2f} on {p['date']}")
    for b in moved['bills_paid']:
        print(f"  bill paid automatically: {b['bill']} ${b['amount']:,.2f} (due {b['due']}) from {b['from']}")
    for account in moved['below_goal']:
        print(f'  note: {account} is now below its savings goal')


def chat(args):
    start = date.today() if args.start == 'today' else date.fromisoformat(args.start)
    app = App(backend(args), start=start, title='chat')
    folder = RUNS / f'chat-{datetime.now():%Y%m%d-%H%M%S}'
    print(f'Simulated clock: {app.store.now():%A %Y-%m-%d %H:%M}. Talking to {ADVISOR}. /quit to stop.')
    current = ADVISOR
    try:
        while True:
            line = input(f'you -> {current}: ').strip()
            if not line:
                continue
            if line in ('/quit', '/exit'):
                break
            command, _, rest = line.partition(' ')
            try:
                if command == '/advance':
                    print_clock(app.move_clock(step=rest or '1d'))
                elif command == '/set':
                    print_clock(app.move_clock(when=rest))
                elif command == '/state':
                    print(json.dumps(app.state(), indent=2))
                elif command == '/usage':
                    print(app.trace.usage())
                else:
                    target, colon, message = line.partition(':')
                    if colon and target.strip().lower() in ALIASES:
                        current, line = ALIASES[target.strip().lower()], message.strip()
                    print(f'{current}: {app.send(current, line)}\n')
            except ValueError as exc:
                print(f'error: {exc}')
    except (EOFError, KeyboardInterrupt):
        print()
    app.trace.save(folder / 'trace.json')
    (folder / 'state.json').write_text(json.dumps(app.state(), indent=2), encoding='utf-8')
    print(f'Saved {folder / "trace.json"} ({app.trace.usage()})')


def scenario(args):
    folder = Path(args.out) if args.out else RUNS / f'{args.name}-{datetime.now():%Y%m%d-%H%M%S}'
    result = run_scenario(args.name, backend(args), workdir=folder / 'data')
    for r in result['replies']:
        print(f"you -> {r['to']}: {r['message']}\n{r['to']}: {r['reply']}\n")
    result['trace'].save(folder / 'trace.json')
    (folder / 'state.json').write_text(json.dumps(result['final_state'], indent=2), encoding='utf-8')
    print(f'Saved {folder} ({result["trace"].usage()})')


def main():
    parser = argparse.ArgumentParser(prog='python -m finadvisor', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('chat', 'scenario'):
        p = sub.add_parser(name)
        p.add_argument('--scripted', action='store_true', help='Use the free offline scripted agents')
        p.add_argument('--model', help='Claude model ID (default: APP_MODEL or claude-haiku-5-5)')
        if name == 'chat':
            p.add_argument('--start', default='today', help='Start date: today (default) or YYYY-MM-DD')
        else:
            p.add_argument('name', choices=SCENARIOS)
            p.add_argument('--out', help='Output folder (default: sessions/<name>-<time>)')
    sub.add_parser('list')
    args = parser.parse_args()
    if args.command == 'list':
        print('\n'.join(SCENARIOS))
    elif args.command == 'chat':
        chat(args)
    else:
        scenario(args)


if __name__ == '__main__':
    main()
