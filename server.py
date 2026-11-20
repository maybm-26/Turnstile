import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from engine import Engine, Busy, InvalidLease

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self.reply(200, {'ok': True, 'mode': 'local-demo-only'})
        elif path == '/events':
            self.reply(200, self.server.engine.events())
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('Body must be between 1 and 16384 bytes')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            resource, owner = data.get('resource'), data.get('owner')
            if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in (resource, owner)):
                raise ValueError('resource and owner must be nonempty strings, max 200 characters')
            path = urlparse(self.path).path
            if path == '/acquire':
                ttl = data.get('ttl', 5)
                if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or not 0.1 <= ttl <= 300:
                    raise ValueError('ttl must be between 0.1 and 300 seconds')
                result = self.server.engine.acquire(resource, owner, ttl)
            elif path in ('/release', '/demo-write'):
                token = data.get('token')
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
            self.reply(409, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})
        except Exception:
            self.log_error('Unexpected server error', exc_info=False) if False else None
            self.reply(500, {'error': 'Internal error; demo unavailable'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local prototype. Do not expose to the internet.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default='turnstile.db')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.engine = Engine(args.db)
    print(f'Local demo: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
