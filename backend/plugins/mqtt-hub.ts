/**
 * mqtt-hub.ts — Minimal open-closed MQTT client for Bun.
 *
 *     const hub = await createHub("mqtt://localhost")
 *
 *     hub.on("sensors/#", (topic, buf) => { ... })
 *     hub.on("config/+",  jsonParse, (topic, data) => { ... })
 *
 *     hub.publish("cmd/reset", JSON.stringify({ reboot: true }))
 */

import mqtt from "mqtt";

// ─── Types ───────────────────────────────────────────────────────────────────

export type Parser<T> = (raw: Buffer) => T;
type Handler<T> = (topic: string, payload: T) => void;

interface Sub {
  regex: RegExp;
  parse: Parser<any>;
  handler: Handler<any>;
}

// ─── Built-in parsers ────────────────────────────────────────────────────────

export const jsonParse: Parser<unknown> = (buf) => JSON.parse(buf.toString());
export const text: Parser<string> = (buf) => buf.toString();

// ─── Pattern → Regex ─────────────────────────────────────────────────────────

const toRegex = (p: string) =>
  new RegExp(
    "^" +
      p
        .split("/")
        .map((s) =>
          s === "+"
            ? "[^/]+"
            : s === "#"
              ? ".*"
              : s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
        )
        .join("/") +
      "$",
  );

// ─── Hub ─────────────────────────────────────────────────────────────────────

export class MQTTHub {
  constructor(private client: mqtt.MqttClient) {
    client.on("message", (topic: string, buf: Buffer) => {
      for (const sub of this.subs) {
        if (!sub.regex.test(topic)) continue;
        try {
          sub.handler(topic, sub.parse(buf));
        } catch (e) {
          console.error(`[mqtt-hub] ${topic}:`, e);
        }
      }
    });
  }

  private subs: Sub[] = [];

  /** Subscribe to a topic. Returns unsubscribe function. */
  on<T = Buffer>(pattern: string, handler: Handler<T>): () => void;
  on<T>(pattern: string, parse: Parser<T>, handler: Handler<T>): () => void;
  on(
    pattern: string,
    parserOrHandler: Parser<unknown> | Handler<unknown>,
    maybeHandler?: Handler<unknown>,
  ): () => void {
    const parse = maybeHandler
      ? (parserOrHandler as Parser<unknown>)
      : (b: Buffer) => b;
    const handler = maybeHandler ?? (parserOrHandler as Handler<unknown>);

    const sub: Sub = { regex: toRegex(pattern), parse, handler };
    this.subs.push(sub);
    this.client.subscribe(pattern);

    return () => {
      this.subs.splice(this.subs.indexOf(sub), 1);
      if (!this.subs.some((s) => s.regex.source === sub.regex.source)) {
        this.client.unsubscribe(pattern);
      }
    };
  }

  /** Publish a message. Payload is string or Buffer. */
  publish(
    topic: string,
    payload: string | Buffer,
    opts?: { qos?: 0 | 1 | 2; retain?: boolean },
  ) {
    this.client.publish(topic, payload, {
      qos: opts?.qos ?? 0,
      retain: opts?.retain ?? false,
    });
  }

  /** Underlying MQTT.js client. */
  get raw() {
    return this.client;
  }

  async disconnect() {
    await this.client.endAsync();
  }
}

/** Connect and return a hub. */
export const createHub = async (url: string, opts?: mqtt.IClientOptions) =>
  new MQTTHub(await mqtt.connectAsync(url, opts));
