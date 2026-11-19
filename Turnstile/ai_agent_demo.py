import time
from turnstile_sdk import TurnstileClient, ResourceBusyError, InvalidLeaseError


def run_ai_agent_demo():
    client = TurnstileClient("http://127.0.0.1:8765")
    resource = "stripe:refund:customer_9821"

    print("\n--- SCENARIO 1: Two AI Agents Race to Refund the Same Customer ---")
    with client.lock(resource, owner="support-agent-alpha", ttl=5) as token:
        print(f"[Agent Alpha] Acquired lock (fencing token #{token}). Processing $500 refund...")

        try:
            with client.lock(resource, owner="support-agent-beta", ttl=5):
                print("[Agent Beta] ERROR: Should not have acquired lock!")
        except ResourceBusyError as err:
            print(f"[Agent Beta] BLOCKED duplicate refund! Reason: {err}")

        client.write_fenced(resource, "support-agent-alpha", token, "refunded_$500_once")
        print("[Agent Alpha] Refund completed and safely released lock.\n")

    print("--- SCENARIO 2: Crashed AI Agent & Stale Token Protection ---")
    stale_lease = client.acquire(resource, owner="crashed-agent-gamma", ttl=1.0)
    stale_token = stale_lease["token"]
    print(f"[Agent Gamma] Acquired lock (token #{stale_token}) with 1s TTL, then froze/crashed...")

    time.sleep(1.3)

    with client.lock(resource, owner="recovery-agent-delta", ttl=5) as fresh_token:
        print(f"[Agent Delta] Took over expired lock with higher fencing token #{fresh_token}.")
        client.write_fenced(resource, "recovery-agent-delta", fresh_token, "recovered_safely")
        print("[Agent Delta] Safely finished the task.")

        try:
            client.write_fenced(resource, "crashed-agent-gamma", stale_token, "corrupt_late_write")
        except InvalidLeaseError as err:
            print(f"[Turnstile Firewall] REJECTED late write from woken Agent Gamma! Reason: {err}\n")


if __name__ == "__main__":
    run_ai_agent_demo()
