# mqtt-hub

Minimal MQTT client за Bun + Elysia. `bun add mqtt`, един файл, готово.

## Quickstart

```ts
import { createHub, jsonParse } from "./mqtt-hub"

const hub = await createHub("mqtt://localhost")

// слушаш
hub.on("sensors/#", jsonParse, (topic, data) => {
  console.log(topic, data)
})

// пращаш
hub.publish("cmd/reset", JSON.stringify({ reboot: true }))
```

## API

### `createHub(url, opts?): Promise<MQTTHub>`

```ts
const hub = await createHub("mqtt://192.168.1.50", {
  username: "device01",
  password: "secret",
})
```

`opts` е стандартният MQTT.js `IClientOptions`.

### `hub.on(pattern, handler): () => void`
### `hub.on(pattern, parse, handler): () => void`

Слуша topic pattern. Без parser → `Buffer`. С parser → каквото върне parser-ът. Връща `unsub()`.

```ts
// raw
hub.on("raw/#", (topic, buf) => { ... })

// json
hub.on("data/+", jsonParse, (topic, obj) => { ... })

// custom
hub.on("imu", (buf) => struct.unpack(buf), (topic, vals) => { ... })

// unsubscribe
const unsub = hub.on("temp/#", (t, b) => { ... })
unsub() // махаш handler-а, broker unsubscribe-ва
```

### `hub.publish(topic, payload, opts?)`

Payload е `string | Buffer`. Сериализацията е на caller-а — `JSON.stringify()` преди подаване.

```ts
hub.publish("cmd/go", JSON.stringify({ speed: 100 }))
hub.publish("raw/bytes", Buffer.from([0x01, 0x02]))
hub.publish("important", "data", { qos: 1, retain: true })
```

### `hub.raw`

Underlying MQTT.js client.

### `hub.disconnect()`

Graceful disconnect.

---

## Parsers

Parser е `(buf: Buffer) => T`. Вградени: `jsonParse`, `text`. Custom:

```ts
import type { Parser } from "./mqtt-hub"

const parseIMU: Parser<[number, number, number]> = (buf) => {
  const v = new DataView(buf.buffer, buf.byteOffset)
  return [v.getFloat32(0, true), v.getFloat32(4, true), v.getFloat32(8, true)]
}

hub.on("sensors/imu", parseIMU, (topic, [ax, ay, az]) => { ... })
```

---

## Elysia WebSocket

`hub.on()` → `unsub()` map-ва директно към WS open/close:

```ts
new Elysia()
  .ws("/sensors", {
    open(ws) {
      ;(ws.data as any).__unsub = hub.on("sensors/#", jsonParse, (topic, data) => {
        ws.send(JSON.stringify({ topic, data }))
      })
    },
    close(ws) {
      ;(ws.data as any).__unsub?.()
    },
  })
  .listen(3000)
```
