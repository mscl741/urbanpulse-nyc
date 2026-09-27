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

type BridgeBody = {
  text: string;
  image_base64?: string;
  mime?: string;
  filename?: string;
};

type LooseContent = {
  type?: string;
  text?: string;
  mimeType?: string;
  name?: string;
  read?: () => Promise<Uint8Array>;
  items?: Array<{ content?: LooseContent }>;
  content?: LooseContent;
};

/** Other texts and photos go to the Python bridge, which calls the existing hazard system. */
export async function replyFor(body: BridgeBody): Promise<string | null> {
  if (!body.image_base64) {
    const hello = replyForHello(body.text);
    if (hello) return hello;
  }

  try {
    const res = await fetch(`${BRIDGE_URL}/message`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(body.image_base64 ? 120_000 : 60_000),
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

function isImageMime(mime: string | undefined): boolean {
  return (mime || "").toLowerCase().startsWith("image/");
}

async function imageFromAttachment(content: LooseContent): Promise<{
  image_base64: string;
  mime: string;
  filename: string;
} | null> {
  if (!content.read || !isImageMime(content.mimeType)) return null;
  const bytes = Buffer.from(await content.read());
  if (!bytes.length) return null;
  return {
    image_base64: bytes.toString("base64"),
    mime: content.mimeType || "image/jpeg",
    filename: content.name || "hazard.jpg",
  };
}

/** Text plus the first photo, including iMessage caption+image groups. */
export async function inboundForBridge(content: LooseContent): Promise<BridgeBody | null> {
  if (content.type === "text") {
    return content.text?.trim() ? { text: content.text } : null;
  }
  if (content.type === "attachment") {
    const image = await imageFromAttachment(content);
    return image ? { text: "", ...image } : null;
  }
  if (content.type === "reply" && content.content) {
    return inboundForBridge(content.content);
  }
  if (content.type !== "group" || !content.items) return null;

  const texts: string[] = [];
  let image: Awaited<ReturnType<typeof imageFromAttachment>> = null;
  for (const item of content.items) {
    const part = item.content;
    if (!part) continue;
    if (part.type === "text" && part.text?.trim()) texts.push(part.text.trim());
    else if (part.type === "attachment" && !image) image = await imageFromAttachment(part);
    else if (part.type === "reply" && part.content) {
      const nested = await inboundForBridge(part.content);
      if (nested?.text) texts.push(nested.text);
      if (nested?.image_base64 && nested.mime && nested.filename && !image) {
        image = {
          image_base64: nested.image_base64,
          mime: nested.mime,
          filename: nested.filename,
        };
      }
    }
  }
  const text = texts.join("\n");
  if (!text && !image) return null;
  return { text, ...(image ?? {}) };
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

    const inbound = await inboundForBridge(
      message.content as LooseContent,
    );
    if (!inbound) continue;

    const reply = await replyFor(inbound);
    if (!reply) continue;

    await message.reply(reply);
  }
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
