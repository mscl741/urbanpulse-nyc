import "dotenv/config";
import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

const BRIDGE_URL = (
  process.env.URBANPULSE_BRIDGE_URL || "http://127.0.0.1:8766"
).replace(/\/$/, "");

/** Exact Hello stays local so the Photon check does not depend on Python. */
export function replyForHello(text: string): string | null {
  if (text.trim().toLowerCase() === "hello") {
    return "Hello from UrbanPulse.";
  }
  return null;
}

/** Other texts go to the Python bridge, which calls the existing hazard system. */
export async function replyFor(text: string): Promise<string | null> {
  const hello = replyForHello(text);
  if (hello) return hello;

  try {
    const res = await fetch(`${BRIDGE_URL}/message`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
      signal: AbortSignal.timeout(60_000),
    });
    if (!res.ok) {
      return "UrbanPulse couldn't check hazards just now. Please try again.";
    }
    const data = (await res.json()) as { reply?: unknown };
    return typeof data.reply === "string" && data.reply.trim()
      ? data.reply
      : null;
  } catch {
    return "UrbanPulse couldn't check hazards just now. Please try again.";
  }
}

function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    console.error(
      `Missing ${name}. Copy spectrum/.env.example to spectrum/.env and set it.`,
    );
    process.exit(1);
  }
  return value;
}

async function main(): Promise<void> {
  const projectId = requiredEnv("SPECTRUM_PROJECT_ID");
  const projectSecret = requiredEnv("SPECTRUM_PROJECT_SECRET");

  const app = await Spectrum({
    projectId,
    projectSecret,
    providers: [imessage.config()],
  });

  console.log("UrbanPulse Spectrum is listening for iMessage.");

  for await (const [, message] of app.messages) {
    if (message.direction !== "inbound") continue;
    if (message.content.type !== "text") continue;

    const reply = await replyFor(message.content.text);
    if (!reply) continue;

    await message.reply(reply);
  }
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
