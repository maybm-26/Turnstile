# Turnstile

**Zero-dependency execution locks and fencing tokens for autonomous AI agents.**

When multiple AI agents or background workers act on the same customer, API, or database record at the same time, they collide—causing duplicate refunds, double emails, and corrupted state. Turnstile stops collisions in 3 lines of Python without requiring Redis, ZooKeeper, or complex infrastructure.

https://github.com/maybm-26/Turnstile/raw/main/Screen%20Recording%202026-11-19%20184806.mp4
---

## Why Turnstile?
* **Zero External Dependencies:** Built purely on Python's standard library with SQLite persistence. Runs in 10 seconds.
* **Crash-Safe Leases:** Every lock has a time-to-live (TTL). If an AI agent hangs or crashes, the lock automatically expires so your system never deadlocks.
* **Fencing Token Protection:** Every lease issues a strictly increasing fencing token, rejecting late writes from frozen or zombie workers.

---

## 60-Second Quickstart

### 1. Start the Turnstile Server
```bash
python server.py
```

### 2. Run the AI Agent Double-Refund Demo
In a second terminal:
```bash
python ai_agent_demo.py
```

---

## Usage (3-Line Python SDK)

```python
from turnstile_sdk import TurnstileClient, ResourceBusyError

client = TurnstileClient("http://127.0.0.1:8765")

try:
    with client.lock("stripe:refund:customer_9821", owner="support-agent-1", ttl=10) as token:
        # Only one agent can execute this block at a time
        client.write_fenced("stripe:refund:customer_9821", "support-agent-1", token, "refunded_\$500")
except ResourceBusyError:
    print("Another AI agent is already processing this customer!")
```

---

## Project Structure
* `engine.py` — SQLite-backed lease and monotonic fencing token engine.
* `server.py` — Lightweight HTTP JSON API (`/acquire`, `/release`, `/demo-write`, `/events`, `/health`).
* `turnstile_sdk.py` — Zero-dependency Python client with context-manager locking (`with client.lock(...)`).
* `ai_agent_demo.py` — Live simulation showing duplicate refund prevention and stale-token rejection.
