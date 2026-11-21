"""Show or move the simulated clock that all three agents' tools use.

    python -m phase1.clock                       show the current simulated date and time
    python -m phase1.clock set 2026-10-31        jump to a date (09:00) or a time: 2026-10-31T18:30
    python -m phase1.clock advance 7d            move forward: 7d, 2w, 12h, 1d6h
    python -m phase1.clock reset                 back to the demo start, 2026-10-24 09:00

The running MCP servers read the clock on every call, so no restart is needed.
run_servers --reset also resets the clock along with the rest of the data.
"""
import argparse
from datetime import timedelta
import re
from .common import DEFAULT_NOW, now, parse_when, set_now

UNITS = {'w': 'weeks', 'd': 'days', 'h': 'hours', 'm': 'minutes'}


def parse_step(text: str) -> timedelta:
    parts = re.findall(r'(\d+)\s*([wdhm])', text.lower())
    if not parts or ''.join(n + u for n, u in parts) != re.sub(r'\s+', '', text.lower()):
        raise argparse.ArgumentTypeError('use a step like 7d, 2w, 12h or 1d6h')
    return timedelta(**{UNITS[u]: int(n) for n, u in parts})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('set', help='Set the date or date and time').add_argument('when')
    sub.add_parser('advance', help='Move forward by a step').add_argument('step', type=parse_step)
    sub.add_parser('reset', help='Back to the demo start date')
    args = parser.parse_args()
    if args.command == 'set':
        try:
            result = set_now(parse_when(args.when))
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == 'advance':
        result = set_now(now() + args.step)
    elif args.command == 'reset':
        result = set_now(parse_when(DEFAULT_NOW))
    else:
        print(f'Simulated clock: {now():%Y-%m-%d %H:%M} ({now():%A})')
        return
    print(f'Simulated clock moved from {result["previous"]} to {result["now"]}.')


if __name__ == '__main__':
    main()
