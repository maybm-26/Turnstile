import argparse
import json
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class Client:
    def __init__(self, url='http://127.0.0.1:8765'):
        self.url = url.rstrip('/')

    def call(self, path, data=None):
        request = Request(self.url + path,
                          data=None if data is None else json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def acquire(self, resource, owner, ttl=5):
        status, result = self.call('/acquire', dict(resource=resource, owner=owner, ttl=ttl))
        if status != 200:
            raise RuntimeError(result)
        return result

    def write_demo(self, lease, value):
        payload = {key: lease[key] for key in ('resource', 'owner', 'token')}
        return self.call('/demo-write', dict(payload, value=value))

    def release(self, lease):
        return self.call('/release', {key: lease[key] for key in ('resource', 'owner', 'token')})

    def demo(self):
        resource = 'demo:' + uuid.uuid4().hex[:10]
        first = self.acquire(resource, 'worker-A', ttl=1)
        print('1. Worker A acquired token', first['token'])
        status, _ = self.call('/acquire', dict(resource=resource, owner='worker-B', ttl=5))
        assert status == 409, 'Expected B to be blocked'
        print('2. Worker B blocked: resource is busy')
        print('3. Simulating A stopping without releasing its lease; waiting...')
        time.sleep(1.2)
        second = self.acquire(resource, 'worker-B', ttl=5)
        print('4. Worker B acquired token', second['token'])
        status, _ = self.write_demo(second, 'written by B')
        assert status == 200
        status, _ = self.write_demo(first, 'stale write from A')
        assert status == 409, 'Expected stale write rejection'
        print('5. Stale worker A write rejected; B write accepted')
        self.release(second)
        print('PASS. This protects only the built-in demo store, not external APIs.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['demo', 'events', 'health'])
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    client = Client(args.url)
    try:
        if args.command == 'demo':
            client.demo()
        else:
            status, data = client.call('/' + args.command)
            print(json.dumps(data, indent=2))
            if status != 200:
                raise SystemExit(1)
    except (URLError, RuntimeError) as exc:
        parser.exit(1, f'Cannot complete request: {exc}. Is server.py running?\n')
