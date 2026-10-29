# Copied from the CS239 tutorial (examples/movie_night/rakazo.py); find_bot() added,
# create_team() reuses an existing provider sign-in when no API key is given and
# updates same-named bots instead of refusing, 4xx errors show Rakazo's reason, clear() added,
# ensure_login() reuses a saved session instead of signing in on every command, and
# full_conversation() follows threads/messages pages back to a chat's first message.
"""Small teaching wrapper around this Rakazo version's authenticated HTTP API.

This is not an official Rakazo SDK or an A2A server. Rakazo must already run.
"""
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import httpx

# Outside the repository, so a session cookie can never be committed.
SESSION_FILE = Path(os.environ.get('RAKAZO_SESSION_FILE',
                                   Path.home() / '.cs239-financial-advisor' / 'rakazo-session.json'))


def _read_sessions(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _write_sessions(path: Path, sessions: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 0o600: only the current user can read it (Windows profile folders are already private).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(sessions, stream)


@dataclass(frozen=True)
class ModelConnection:
    provider: str
    model_id: str
    base_url: str
    api_key: str = field(default='', repr=False)


@dataclass(frozen=True)
class MCPConnection:
    name: str
    slug: str
    endpoint: str


@dataclass(frozen=True)
class BotProfile:
    name: str
    instructions: str
    model: ModelConnection
    mcp: tuple[MCPConnection, ...] = ()


class Rakazo:
    def __init__(self, url: str, *, origin: str | None = None):
        # Use the web origin when its API is reached on a different port.
        self.http = httpx.Client(base_url=url.rstrip('/'), timeout=30,
                                 headers={'Origin': origin or url.rstrip('/')})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.close()

    def login(self, email: str, password: str):
        response = self.http.post('/api/auth/sign-in/email',
                                  json={'email': email, 'password': password})
        if response.status_code == 429:
            raise RuntimeError('Login failed (HTTP 429): Rakazo allows 10 sign-ins per 15 minutes. '
                               'Wait 15 minutes, then try once.')
        if not response.is_success:
            raise RuntimeError(f'Login failed (HTTP {response.status_code}). Check account and origin.')

    def has_session(self) -> bool:
        """True when the current cookies belong to a live session (not rate-limited like sign-in)."""
        response = self.http.get('/api/auth/get-session')
        return response.is_success and response.json() is not None

    def ensure_login(self, email: str, password, session_file: Path = SESSION_FILE):
        """Reuse a saved session for this URL and account; sign in (password()) only when it has expired.

        The session cookie is saved outside the repository, readable only by the current user.
        """
        key = f'{self.http.base_url}|{email}'
        saved = _read_sessions(session_file)
        for cookie in saved.get(key, []):
            self.http.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'],
                                  path=cookie['path'])
        if saved.get(key) and self.has_session():
            return
        self.http.cookies.clear()
        self.login(email, password())
        saved[key] = [{'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path}
                      for c in self.http.cookies.jar]
        _write_sessions(session_file, saved)

    def rpc(self, route: str, data: dict | None = None):
        response = self.http.post('/rpc/' + route, json={'json': data or {}})
        if not response.is_success:
            # Do not print model-provider errors: they can echo credentials. Other 4xx
            # errors carry only Rakazo's short reason (e.g. a refused MCP endpoint).
            reason = ''
            if 400 <= response.status_code < 500 and not route.startswith('models/'):
                try:
                    reason = ': ' + str(response.json()['json']['message'])[:200]
                except (ValueError, KeyError, TypeError):
                    pass
            raise RuntimeError(f'{route} failed (HTTP {response.status_code}){reason}. '
                               'Check the Rakazo server logs.')
        body = response.json()
        if 'json' not in body:
            raise RuntimeError(f'{route} returned an unexpected response')
        return body['json']

    def create_team(self, *profiles: BotProfile) -> dict[str, str]:
        """Create the bots, or update same-named bots left by an earlier (possibly failed) run."""
        names = [p.name for p in profiles]
        if len(set(names)) != len(names):
            raise ValueError('Bot names must be distinct')
        existing = {b['name']: b['id'] for b in self.rpc('bots/list') if b['name'] in names}
        servers = {s['slug']: s for s in self.rpc('mcp/servers/list')}
        endpoints = {}
        for p in profiles:
            for mcp in p.mcp:
                if mcp.slug in endpoints and endpoints[mcp.slug] != mcp.endpoint:
                    raise ValueError('Conflicting MCP endpoints for the same slug')
                endpoints[mcp.slug] = mcp.endpoint
                if mcp.slug in servers and servers[mcp.slug]['endpoint'] != mcp.endpoint:
                    raise ValueError('Existing MCP slug points to a different endpoint')
        bots = {}
        for p in profiles:
            # Without a key (e.g. "Sign in with Claude Pro/Max"), reuse the provider already
            # connected in Rakazo instead of overwriting that sign-in.
            if p.model.provider == 'openai-compatible' or p.model.api_key:
                self.rpc('models/connect', {'provider': p.model.provider, 'modelId': p.model.model_id,
                         'baseUrl': p.model.base_url, 'apiKey': p.model.api_key})
            if p.name in existing:
                bot = {'id': existing[p.name]}
                self.rpc('bots/update', {'botId': bot['id'], 'description': p.instructions,
                                        'instructions': p.instructions})
            else:
                bot = self.rpc('bots/create', {'name': p.name, 'title': '',
                               'description': p.instructions, 'instructions': p.instructions,
                               'notifyOnFinish': False})
            self.rpc('bots/update', {'botId': bot['id'], 'modelProvider': p.model.provider,
                                    'modelId': p.model.model_id})
            assigned = ({a['serverId'] for a in self.rpc('mcp/assignments/list', {'botId': bot['id']})}
                        if p.name in existing else set())
            for mcp in p.mcp:
                if mcp.slug not in servers:
                    servers[mcp.slug] = self.rpc('mcp/servers/create', {
                        **asdict(mcp), 'transport': 'streamable_http'})
                if servers[mcp.slug]['id'] not in assigned:
                    self.rpc('mcp/assignments/approve', {'botId': bot['id'],
                             'serverId': servers[mcp.slug]['id']})
            bots[p.name] = bot['id']
        return bots

    def send(self, bot_id: str, message: str):
        """Start an asynchronous run; this returns a run handle, not its final answer."""
        return self.rpc('threads/send', {'botId': bot_id, 'text': message})

    def conversation(self, bot_id: str):
        return self.rpc('threads/get', {'botId': bot_id})

    def full_conversation(self, bot_id: str, max_pages: int = 500):
        """threads/get plus every older page (threads/messages), messages de-duplicated in seq order."""
        snapshot = self.conversation(bot_id)
        found = {m['id']: m for m in snapshot['messages']}
        before = snapshot.get('olderCursor')
        for _ in range(max_pages):
            if before is None:
                break
            page = self.rpc('threads/messages', {'botId': bot_id, 'before': before})
            found.update({m['id']: m for m in page['messages']})
            if not page['messages'] or page.get('olderCursor') == before:
                break
            before = page.get('olderCursor')
        return {**snapshot, 'messages': sorted(found.values(), key=lambda m: m['seq']), 'olderCursor': None}

    def clear(self, bot_id: str):
        """Permanently delete a bot's chat history and cancel its active runs."""
        return self.rpc('threads/clear', {'botId': bot_id})

    def find_bot(self, name: str) -> str:
        """Return the id of an existing bot by its exact name."""
        for bot in self.rpc('bots/list'):
            if bot['name'] == name:
                return bot['id']
        raise ValueError(f'No bot named {name!r}. Run with --apply first.')
