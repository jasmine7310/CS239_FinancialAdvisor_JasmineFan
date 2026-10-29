"""Export a trace: the three bots' Rakazo conversations plus every MCP tool call.

    python -m phase1.export_traces <scenario>    one scripted run (from its --send start time)
    python -m phase1.export_traces --session     everything now in the three chats, scripted or
                                                 typed in Rakazo (since the last --fresh)

Writes traces/phase1/<name>/trace.json (raw, complete) and trace.md (readable).
The Markdown renderer is generic because Rakazo's thread format can change between versions;
trace.json always keeps the full responses.
"""
import argparse
from datetime import datetime
import json
import os
from .app import ADVISOR, BANK, PAYMENTS, ask_password
from .common import TOOL_LOG, TRACES_DIR
from .rakazo import Rakazo

TIME_KEYS = ('createdAt', 'created_at', 'timestamp', 'time')
TEXT_KEYS = ('text', 'content', 'parts', 'message', 'body')


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.astimezone()
    except ValueError:
        return None


def messages(node):
    """Yield message-like dicts (anything with a role/sender) in document order."""
    if isinstance(node, dict):
        if any(k in node for k in ('role', 'sender', 'author')):
            yield node
            return
        for value in node.values():
            yield from messages(value)
    elif isinstance(node, list):
        for value in node:
            yield from messages(value)


def text_of(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(filter(None, (text_of(v) for v in value)))
    if isinstance(value, dict):
        for key in TEXT_KEYS:
            if key in value:
                return text_of(value[key])
    return ''


def since(message, start):
    stamp = next((parse_time(message[k]) for k in TIME_KEYS if k in message), None)
    return stamp is None or stamp >= start


def render(run, threads, calls, start):
    lines = [f'# Trace: {run["scenario"]}', '', f'- Started: {run["started_at"]}',
             f'- Run id: {run.get("run_id")}', f'- Sent to: {run.get("bot", "Financial Advisor")}',
             f'- User request: {run["request"]}']
    lines += [f'- User follow-up ({f["sent_at"]}): {f["text"]}' for f in run.get('follow_ups', [])]
    lines.append('')
    for bot, thread in threads.items():
        lines += [f'## {bot} conversation', '']
        for m in messages(thread):
            if not since(m, start):
                continue
            who = m.get('role') or m.get('sender') or m.get('author')
            stamp = next((m[k] for k in TIME_KEYS if k in m), '')
            body = text_of(m) or json.dumps(m, indent=2, default=str)
            extra = {k: v for k, v in m.items() if k not in TEXT_KEYS + TIME_KEYS + ('role', 'id')}
            lines += [f'**{who}** {stamp}', '', body.strip(), '']
            if extra:
                lines += ['<details><summary>fields</summary>', '', '```json',
                          json.dumps(extra, indent=2, default=str), '```', '</details>', '']
    lines += ['## MCP tool calls (actions and observations)', '']
    for c in calls:
        lines += [f'### {c["ts"]} · {c["agent"]} → `{c["tool"]}`', '', '```json',
                  json.dumps({k: c[k] for k in ('arguments', 'result', 'error') if k in c},
                             indent=2), '```', '']
    return '\n'.join(lines)


def session_run(name: str, threads: dict) -> dict:
    """A run record covering every message now in the chats, starting at the earliest one."""
    stamps = [parse_time(m[k]) for t in threads.values() for m in messages(t) for k in TIME_KEYS if k in m]
    stamps = [s for s in stamps if s]
    start = min(stamps).astimezone() if stamps else datetime.now().astimezone()
    return {'scenario': name, 'bot': 'all three bots',
            'request': 'Whole current session: every message in the three chats, sent by the scripts '
                       'or typed in Rakazo', 'started_at': start.isoformat(timespec='milliseconds')}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('scenario', nargs='?', help='Scenario sent with --send (omit with --session)')
    parser.add_argument('--session', nargs='?', const='', metavar='NAME',
                        help='Export everything in the three chats into traces/NAME '
                             '(default: session_<date>-<time>)')
    args = parser.parse_args()
    if (args.scenario is None) == (args.session is None):
        parser.error('Give a scenario, or --session, but not both')
    missing = [n for n in ('RAKAZO_URL', 'RAKAZO_EMAIL') if not os.environ.get(n)]
    if missing:
        parser.error('Set ' + ', '.join(missing))
    with Rakazo(os.environ['RAKAZO_URL'], origin=os.environ.get('RAKAZO_ORIGIN')) as app:
        app.ensure_login(os.environ['RAKAZO_EMAIL'], ask_password)
        threads = {bot: app.full_conversation(app.find_bot(bot)) for bot in (ADVISOR, PAYMENTS, BANK)}
    if args.session is not None:
        name = args.session or datetime.now().strftime('session_%Y%m%d-%H%M%S')
        folder = TRACES_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        run = session_run(name, threads)
        (folder / 'run.json').write_text(json.dumps(run, indent=2), encoding='utf-8')
    else:
        folder = TRACES_DIR / args.scenario
        run = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    start = parse_time(run['started_at'])
    calls = []
    if TOOL_LOG.exists():
        for line in TOOL_LOG.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            if parse_time(entry['ts']) >= start:
                calls.append(entry)
    trace = {**run, 'exported_at': datetime.now().isoformat(timespec='seconds'),
             'tool_calls': calls, 'rakazo_threads': threads}
    (folder / 'trace.json').write_text(json.dumps(trace, indent=2, default=str), encoding='utf-8')
    (folder / 'trace.md').write_text(render(run, threads, calls, start), encoding='utf-8')
    print(f'Wrote {folder / "trace.json"} and trace.md ({len(calls)} tool calls).')


if __name__ == '__main__':
    main()
