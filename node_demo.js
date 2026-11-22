const { TurnstileClient, ResourceBusyError, InvalidLeaseError } = require("./turnstile");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function runNodeAgentDemo() {
  const client = new TurnstileClient("http://127.0.0.1:8765");
  const resource = "stripe:refund:customer_9821";

  console.log("\n--- SCENARIO 1: Two Node.js AI Agents Race to Refund the Same Customer ---");
  await client.withLock(resource, "node-agent-alpha", async (token) => {
    console.log(`[Node Agent Alpha] Acquired lock (fencing token #${token}). Processing $500 refund...`);

    try {
      await client.withLock(resource, "node-agent-beta", async () => {
        console.log("[Node Agent Beta] ERROR: Should not have acquired lock!");
      }, 5);
    } catch (err) {
      if (err instanceof ResourceBusyError) {
        console.log(`[Node Agent Beta] BLOCKED duplicate refund! Reason: ${err.message}`);
      } else {
        throw err;
      }
    }

    await client.writeFenced(resource, "node-agent-alpha", token, "refunded_$500_once");
    console.log("[Node Agent Alpha] Refund completed and safely released lock.\n");
  }, 5);

  console.log("--- SCENARIO 2: Crashed Node.js Agent & Stale Token Protection ---");
  const staleLease = await client.acquire(resource, "node-crashed-gamma", 1.0);
  const staleToken = staleLease.token;
  console.log(`[Node Agent Gamma] Acquired lock (token #${staleToken}) with 1s TTL, then froze/crashed...`);

  await sleep(1300);

  await client.withLock(resource, "node-recovery-delta", async (freshToken) => {
    console.log(`[Node Agent Delta] Took over expired lock with higher fencing token #${freshToken}.`);
    await client.writeFenced(resource, "node-recovery-delta", freshToken, "recovered_safely");
    console.log("[Node Agent Delta] Safely finished the task.");

    try {
      await client.writeFenced(resource, "node-crashed-gamma", staleToken, "corrupt_late_write");
    } catch (err) {
      if (err instanceof InvalidLeaseError) {
        console.log(`[Turnstile Firewall] REJECTED late write from woken Agent Gamma! Reason: ${err.message}\n`);
      } else {
        throw err;
      }
    }
  }, 5);
}

runNodeAgentDemo().catch((err) => {
  console.error("Demo failed:", err.message);
});