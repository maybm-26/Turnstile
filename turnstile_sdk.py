import json
import urllib.error
import urllib.request
from contextlib import contextmanager


class TurnstileError(Exception):
    pass


class ResourceBusyError(TurnstileError):
    """Raised when another worker or AI agent holds an active lease."""


class InvalidLeaseError(TurnstileError):
    """Raised when a lease has expired or the fencing token is stale."""


class TurnstileClient:
    def __init__(self, base_url="http://127.0.0.1:8765", api_key=None, timeout=5.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                msg = json.loads(err_body).get("error", err_body)
            except json.JSONDecodeError:
                msg = err_body
            if exc.code == 409:
                if "busy" in msg.lower() or "already leased" in msg.lower():
                    raise ResourceBusyError(msg) from None
                raise InvalidLeaseError(msg) from None
            raise TurnstileError(f"HTTP {exc.code}: {msg}") from None

    def acquire(self, resource, owner, ttl=5.0):
        return self._post("/acquire", {"resource": resource, "owner": owner, "ttl": ttl})

    def release(self, resource, owner, token):
        return self._post("/release", {"resource": resource, "owner": owner, "token": token})

    def write_fenced(self, resource, owner, token, value):
        return self._post(
            "/demo-write",
            {"resource": resource, "owner": owner, "token": token, "value": value},
        )

    @contextmanager
    def lock(self, resource, owner, ttl=5.0):
        lease = self.acquire(resource=resource, owner=owner, ttl=ttl)
        token = lease["token"]
        try:
            yield token
        finally:
            try:
                self.release(resource=resource, owner=owner, token=token)
            except InvalidLeaseError:
                pass
