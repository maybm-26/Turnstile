class TurnstileError extends Error {
  constructor(message) {
    super(message);
    this.name = "TurnstileError";
  }
}

class ResourceBusyError extends TurnstileError {
  constructor(message) {
    super(message);
    this.name = "ResourceBusyError";
  }
}

class InvalidLeaseError extends TurnstileError {
  constructor(message) {
    super(message);
    this.name = "InvalidLeaseError";
  }
}

class TurnstileClient {
  constructor(baseUrl = "http://127.0.0.1:8765", timeoutMs = 5000) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  async _post(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data.error || `HTTP ${res.status}`;
        if (res.status === 409) {
          if (msg.toLowerCase().includes("busy") || msg.toLowerCase().includes("already leased")) {
            throw new ResourceBusyError(msg);
          }
          throw new InvalidLeaseError(msg);
        }
        throw new TurnstileError(msg);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  acquire(resource, owner, ttl = 5.0) {
    return this._post("/acquire", { resource, owner, ttl });
  }

  release(resource, owner, token) {
    return this._post("/release", { resource, owner, token });
  }

  writeFenced(resource, owner, token, value) {
    return this._post("/demo-write", { resource, owner, token, value });
  }

  async withLock(resource, owner, fn, ttl = 5.0) {
    const lease = await this.acquire(resource, owner, ttl);
    const token = lease.token;
    try {
      return await fn(token);
    } finally {
      try {
        await this.release(resource, owner, token);
      } catch (err) {
        if (!(err instanceof InvalidLeaseError)) throw err;
      }
    }
  }
}

module.exports = {
  TurnstileClient,
  TurnstileError,
  ResourceBusyError,
  InvalidLeaseError,
};
