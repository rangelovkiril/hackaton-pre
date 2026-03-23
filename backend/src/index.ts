import { Elysia } from "elysia";
import { createHub, jsonParse, type Parser } from "./plugins/mqtt-hub";

const hub = await createHub("mqtt://localhost");

// ── Incoming: raw bytes (default) ────────────────────────────────────────

hub.on("raw/#", (topic: string, buf) => {
  console.log(`[raw]  ${topic}:`, buf);
});

// ── Incoming: JSON ───────────────────────────────────────────────────────

hub.on("sensors/+/temp", jsonParse, (topic, data) => {
  console.log(`[json] ${topic}:`, data);
});

// ── Incoming: custom binary parser ───────────────────────────────────────

const parseIMU: Parser<[number, number, number]> = (buf) => {
  const v = new DataView(buf.buffer, buf.byteOffset);
  return [v.getFloat32(0, true), v.getFloat32(4, true), v.getFloat32(8, true)];
};

hub.on("binary/imu", parseIMU, (_topic, [ax, ay, az]) => {
  console.log(
    `[imu]  ax=${ax.toFixed(2)} ay=${ay.toFixed(2)} az=${az.toFixed(2)}`,
  );
});

// ── Outgoing: periodic heartbeat ─────────────────────────────────────────

setInterval(() => {
  hub.publish(
    "status/heartbeat",
    JSON.stringify({ alive: true, ts: Date.now() }),
  );
}, 5000);

// ── Elysia: pipe MQTT → WebSocket ───────────────────────────────────────

new Elysia()
  .ws("/sensors", {
    open(ws) {
      (ws.data as any).__unsub = hub.on(
        "sensors/#",
        jsonParse,
        (topic, data) => {
          ws.send(JSON.stringify({ topic, data }));
        },
      );
    },
    close(ws) {
      (ws.data as any).__unsub?.();
    },
    message(_ws, msg) {
      // WS → MQTT bridge
      const { topic, payload } = msg as any;
      if (topic) hub.publish(topic, JSON.stringify(payload));
    },
  })

  // ── Dynamic subscriptions per client ─────────────────────────────────

  .ws("/subscribe", {
    open(ws) {
      (ws.data as any).__unsubs = [] as (() => void)[];
    },
    message(ws, msg) {
      const { action, topic, payload } = msg as any;
      if (action === "subscribe" && topic) {
        const unsub = hub.on(topic, jsonParse, (t, data) => {
          ws.send(JSON.stringify({ topic: t, data }));
        });
        (ws.data as any).__unsubs.push(unsub);
      }
      if (action === "publish" && topic) {
        hub.publish(topic, JSON.stringify(payload));
      }
    },
    close(ws) {
      for (const fn of (ws.data as any).__unsubs) fn();
    },
  })

  .listen(3000);

console.log("Elysia :3000 + MQTT hub ready");
