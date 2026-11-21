"""Show or move the simulated clock that all three agents' tools use.

    python -m phase1.clock                       show the current simulated date and time
    python -m phase1.clock advance 7d            live through 7 days: 7d, 2w, 12h, 1d6h
    python -m phase1.clock set 2026-12-01        jump to a date (09:00) or a time: 2026-12-01T18:30
    python -m phase1.clock reset                 start this run over (data and clock as at its start)

Moving forward means you lived through those days: paychecks dated up to the new day arrive,
and every bill due before the new day is paid automatically, from the paycheck account when it
can cover it, else other checking, else savings. Bills due on the new day itself are still due.
Moving back changes only the clock.
The running MCP servers read the data on every call, so no restart is needed.
"""
import argparse
from datetime import timedelta
import re
from .common import now, parse_when, reset_data, start
from .simulator import move_clock

UNITS = {'w': 'weeks', 'd': 'days', 'h': 'hours', 'm': 'minutes'}


def parse_step(text: str) -> timedelta:
    parts = re.findall(r'(\d+)\s*([wdhm])', text.lower())
    if not parts or ''.join(n + u for n, u in parts) != re.sub(r'\s+', '', text.lower()):
        raise argparse.ArgumentTypeError('use a step like 7d, 2w, 12h or 1d6h')
    return timedelta(**{UNITS[u]: int(n) for n, u in parts})


def report(moved: dict):
    print(f'Simulated clock moved from {moved["previous"]} to {moved["now"]}.')
    if moved['went_back']:
        print('Moved back: nothing was paid or received. Bills already paid stay paid; '
              'use "python -m phase1.clock reset" to start the run over.')
        return
    for amount, day in moved['paychecks']:
        print(f'  Paycheck received: ${amount:,.2f} on {day}')
    for bill, amount, day, account in moved['bills_paid']:
        print(f'  Bill paid automatically: {bill} ${amount:,.2f} (due {day}) from {account}')
    print(f'  Received ${moved["received_total"]:,.2f}, paid ${moved["paid_total"]:,.2f}.')
    for account in moved['overdrawn']:
        print(f'  Warning: {account} is overdrawn.')
    for account in moved['below_goal']:
        print(f'  Note: {account} is now below its savings goal; purchase checks will say so.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('set', help='Jump to a date or date and time').add_argument('when')
    sub.add_parser('advance', help='Live through a step of time').add_argument('step', type=parse_step)
    sub.add_parser('reset', help='Start this run over')
    args = parser.parse_args()
    try:
        if args.command == 'set':
            report(move_clock(parse_when(args.when)))
        elif args.command == 'advance':
            report(move_clock(now() + args.step))
        elif args.command == 'reset':
            begin = start()
            reset_data(begin.date())
            print(f'Run started over at {begin:%A %Y-%m-%d %H:%M}: starting data restored, clock reset.')
        else:
            print(f'Simulated clock: {now():%A %Y-%m-%d %H:%M} (this run started {start():%Y-%m-%d})')
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
