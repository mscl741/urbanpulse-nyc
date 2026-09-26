import "dotenv/config";
import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

/** Milestone 1: exact Hello (any case, surrounding spaces ignored). Later this calls Python. */
export function replyFor(text: string): string | null {
  if (text.trim().toLowerCase() === "hello") {
    return "Hello from UrbanPulse.";
  }
  return null;
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

    const reply = replyFor(message.content.text);
    if (!reply) continue;

    await message.reply(reply);
  }
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
