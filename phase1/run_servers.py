"""Start all three MCP servers over HTTP and keep them running until Ctrl+C."""
import argparse
import subprocess
import sys
from .app import PORTS
from .common import ROOT, reset_data

MODULES = {'Financial Advisor': 'advisor_server', 'Payment Manager': 'payments_server',
           'Bank Agent': 'bank_server'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset', action='store_true',
                        help='Restore the starting data (empty wishlist, unpaid bills, original balances)')
    args = parser.parse_args()
    if args.reset:
        reset_data()
        print('Data reset from data/seed.')
    processes = []
    for agent, module in MODULES.items():
        processes.append(subprocess.Popen(
            [sys.executable, '-m', f'phase1.{module}', '--http', '--port', str(PORTS[agent])], cwd=ROOT))
        print(f'{agent}: http://127.0.0.1:{PORTS[agent]}/mcp')
    print('Tool calls are logged to traces/tool_calls.jsonl. Press Ctrl+C to stop.')
    try:
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            process.terminate()


if __name__ == '__main__':
    main()
