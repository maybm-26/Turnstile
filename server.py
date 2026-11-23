import argparse
import json
import math
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from engine import Engine, Busy, InvalidLease

BLOCKED_EVENTS = []
SERVER_API_KEY = os.environ.get('TURNSTILE_API_KEY', '').strip()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Turnstile — Live AI Agent Control Plane</title>
<style>
  body { font-family: system-ui, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 24px; }
  .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; gap: 12px; flex-wrap: wrap; }
  .actions { display: flex; align-items: center; gap: 12px; }
  .btn { background: #2563eb; color: #fff; border: none; padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn:hover { background: #1d4ed8; }
  .btn:disabled { opacity: 0.6; cursor: wait; }
  .badge { background: #064e3b; color: #34d399; padding: 6px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 20px 0; }
  .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 16px; }
  .num { font-size: 28px; font-weight: 700; color: #38bdf8; margin-top: 6px; }
  .blocked { color: #f87171; }
  table { width: 100%; border-collapse: collapse; background: #111827; border-radius: 10px; overflow: hidden; }
  th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid #1f2937; font-size: 14px; }
  th { color: #94a3b8; font-size: 12px; text-transform: uppercase; }
  .tag-ok { color: #34d399; font-weight: 600; text-transform: uppercase; }
  .tag-err { color: #f87171; font-weight: 700; text-transform: uppercase; }
</style>
</head>
<body>
  <div class="header">
    <div><h1 style="margin:0;font-size:22px;">Turnstile Control Plane</h1><small style="color:#94a3b8;">Real-Time Execution Locks & Fencing Tokens for AI Agents</small></div>
    <div class="actions">
      <button class="btn" id="simBtn" onclick="simulate()">⚡ Simulate Agent Collision</button>
      <span class="badge">● LIVE (Auto-refreshing)</span>
    </div>
  </div>
  <div class="grid">
    <div class="card"><div>Total Recorded Events</div><div class="num" id="total">0</div></div>
    <div class="card"><div>Latest Fencing Token</div><div class="num" id="token">#0</div></div>
    <div class="card"><div>Collisions / Stale Writes Blocked</div><div class="num blocked" id="blocked">0</div></div>
  </div>
  <table><thead><tr><th>Event</th><th>Resource</th><th>Agent / Owner</th><th>Token</th><th>Details</th></tr></thead><tbody id="rows"></tbody></table>
<script>
const demoHeaders = {'Content-Type': 'application/json', 'X-Turnstile-Demo': '1'};
async function simulate() {
  const btn = document.getElementById('simBtn');
  btn.disabled = true; btn.textContent = 'Simulating...';
  const resId = 'stripe:refund:cust_' + Math.floor(1000 + Math.random() * 9000);
  try {
    const r1 = await fetch('/acquire', { method: 'POST', headers: demoHeaders, body: JSON.stringify({ resource: resId, owner: 'agent-alpha', ttl: 10 }) });
    const lease = await r1.json();
    await fetch('/acquire', { method: 'POST', headers: demoHeaders, body: JSON.stringify({ resource: resId, owner: 'agent-beta-duplicate', ttl: 10 }) });
    await fetch('/demo-write', { method: 'POST', headers: demoHeaders, body: JSON.stringify({ resource: resId, owner: 'agent-alpha', token: lease.token, value: 'refunded_$500_once' }) });
    await fetch('/release', { method: 'POST', headers: demoHeaders, body: JSON.stringify({ resource: resId, owner: 'agent-alpha', token: lease.token }) });
    await refresh();
  } finally {
    btn.disabled = false; btn.textContent = '⚡ Simulate Agent Collision';
  }
}
async function refresh() {
  const res = await fetch('/events');
  const data = await res.json();
  const events = Array.isArray(data) ? data : (data.events || []);
  document.getElementById('total').textContent = events.length;
  let maxTok = 0, blocked = 0;
  const rows = events.slice().reverse().map(e => {
    const tok = e.token || 0;
    if (tok > maxTok) maxTok = tok;
    const type = (e.kind || e.event || 'event').toString();
    const isErr = type.toLowerCase().includes('blocked');
    if (isErr) blocked++;
    return `<tr><td class="${isErr ? 'tag-err' : 'tag-ok'}">${type}</td><td>${e.resource || '-'}</td><td>${e.owner || '-'}</td><td>${tok ? '#' + tok : '-'}</td><td><code>${JSON.stringify(e)}</code></td></tr>`;
  }).join('');
  document.getElementById('token').textContent = '#' + maxTok;
  document.getElementById('blocked').textContent = blocked;
  document.getElementById('rows').innerHTML = rows || '<tr><td colspan="5">No events yet. Click "Simulate Agent Collision" above!</td></tr>';
}
refresh(); setInterval(refresh, 1000);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self):
        if not SERVER_API_KEY:
            return True
        if self.headers.get('X-Turnstile-Demo') == '1':
            return True
        auth = self.headers.get('Authorization', '')
        return auth == f'Bearer {SERVER_API_KEY}'

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            body = DASHBOARD_HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/health':
            self.reply(200, {'ok': True, 'auth_enabled': bool(SERVER_API_KEY)})
        elif path == '/events':
            combined = list(self.server.engine.events()) + BLOCKED_EVENTS
            combined.sort(key=lambda x: x.get('at', 0))
            self.reply(200, combined)
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self._is_authorized():
            self.reply(401, {'error': 'Unauthorized: missing or invalid Bearer API key'})
            return
        resource, owner, token = '-', '-', None
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('Body must be between 1 and 16384 bytes')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            resource, owner = data.get('resource'), data.get('owner')
            token = data.get('token')
            if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in (resource, owner)):
                raise ValueError('resource and owner must be nonempty strings, max 200 characters')
            path = urlparse(self.path).path
            if path == '/acquire':
                ttl = data.get('ttl', 5)
                if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or not 0.1 <= ttl <= 300:
                    raise ValueError('ttl must be between 0.1 and 300 seconds')
                result = self.server.engine.acquire(resource, owner, ttl)
            elif path in ('/release', '/demo-write'):
                if type(token) is not int or token <= 0:
                    raise ValueError('token must be a positive integer')
                if path == '/release':
                    result = self.server.engine.release(resource, owner, token)
                else:
                    value = data.get('value')
                    if not isinstance(value, str) or len(value) > 4000:
                        raise ValueError('value must be a string, max 4000 characters')
                    result = self.server.engine.write_demo(resource, owner, token, value)
            else:
                self.reply(404, {'error': 'Not found'})
                return
            self.reply(200, result)
        except (Busy, InvalidLease) as exc:
            BLOCKED_EVENTS.append({
                'at': time.time(),
                'kind': 'BLOCKED',
                'resource': resource,
                'owner': owner,
                'token': token if isinstance(token, int) else None,
                'reason': str(exc),
            })
            self.reply(409, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})
        except Exception:
            self.reply(500, {'error': 'Internal error; demo unavailable'})


if __name__ == '__main__':
    default_port = int(os.environ.get('PORT', 8765))
    parser = argparse.ArgumentParser(description='Turnstile Coordination Server')
    parser.add_argument('--port', type=int, default=default_port)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--db', default='turnstile.db')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.engine = Engine(args.db)
    print(f'Turnstile server running on http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
