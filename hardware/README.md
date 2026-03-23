# mqtt_hub

Drop-in MQTT client. 

## Quickstart

```bash
pip install paho-mqtt
```

```python
from mqtt_hub import MQTTHub, json_parse, json_dump

hub = MQTTHub("broker.local")

@hub.on("sensors/+/temp", parse=json_parse)
def on_temp(topic, payload):
    print(payload["value"])

@hub.watch("status/heartbeat", interval=5.0, serialize=json_dump)
def heartbeat():
    return {"alive": True}

hub.run()
```

## Концепция

Hub-ът е **open-closed** — добавяш функционалност само с decorator-и, core-ът не се пипа.

Три примитива покриват всичко:

| Примитив | Посока | Какво прави |
|---|---|---|
| `@hub.on(topic)` | incoming | Получава съобщения |
| `@hub.watch(topic)` | outgoing | Изпраща данни (stream или periodic) |
| `hub.publish(topic, data)` | outgoing | Еднократен publish |

Parsing и serialization са **per-handler**, **opt-in** — по подразбиране всичко е raw bytes, нула overhead.

---

## API

### `MQTTHub(broker, port, *, client_id, username, password, keepalive)`

Конструкторът. Всичко освен `broker` е optional.

```python
hub = MQTTHub("192.168.1.50", username="device01", password="secret")
```

### `hub.run()`

Свързва се, subscribe-ва, пуска watch-овете и блокира до Ctrl-C.

### `hub.stop()`

Graceful shutdown — спира watch timers/threads, disconnect-ва.

---

### `@hub.on(topic_pattern, *, parse=raw, qos=0)`

Subscribe + handler за входящи съобщения.

**Параметри:**
- `topic_pattern` — MQTT topic, поддържа `+` (single level) и `#` (multi level)
- `parse` — `Callable[[bytes], T]`, трансформира raw payload преди handler-а
- `qos` — 0, 1 или 2

**Handler signature:** `(topic: str, payload: T) -> None`

```python
@hub.on("sensors/+/temperature", parse=json_parse, qos=1)
def handle(topic: str, payload: dict):
    print(payload)
```

Множество handler-и на един topic работят — всички се извикват.

---

### `@hub.watch(topic, *, interval=None, serialize=raw_dump, qos=0, retain=False)`

Регистрира изходящ publisher. Два режима:

#### Stream (interval=None) — default

Функцията е **generator**. Върти се в daemon thread. Всеки `yield` публикува веднага.

```python
@hub.watch("sensors/lidar")
def lidar():
    while True:
        yield sensor.read()  # блокира до нови данни
```

- `yield None` — skip-ва, нищо не се publish-ва
- Generator-ът може да свърши (`StopIteration`) — логва се и thread-ът спира
- При `hub.stop()` generator-ът се затваря с `.close()`

#### Periodic (interval=N)

Обикновена функция, извиква се на всеки N секунди.

```python
@hub.watch("status/hb", interval=5.0, serialize=json_dump)
def heartbeat():
    return {"alive": True}
```

- `return None` — skip-ва цикъла

---

### `hub.publish(topic, payload, *, serialize=raw_dump, qos=0, retain=False)`

Еднократен publish. Ползвай от handler, от API endpoint, откъдето трябва.

```python
hub.publish("commands/reset", {"reboot": True}, serialize=json_dump)
```

---

## Parsers & Serializers

### Вградени

| Функция | Тип | Какво прави |
|---|---|---|
| `raw` | Parser | `bytes → bytes` (no-op, default) |
| `json_parse` | Parser | `bytes → dict/list` |
| `text` | Parser | `bytes → str` (UTF-8) |
| `raw_dump` | Serializer | `Any → bytes` (pass-through за bytes, JSON за dict/list) |
| `json_dump` | Serializer | `Any → bytes` (JSON) |

### Писане на custom parser

Parser е всяка функция `(bytes) -> T`:

```python
import struct

def parse_imu(data: bytes) -> tuple[float, float, float]:
    """12 bytes → 3 floats (little-endian)."""
    return struct.unpack("<3f", data)

@hub.on("sensors/imu", parse=parse_imu)
def handle_imu(topic, payload):
    ax, ay, az = payload
```

Други примери:

```python
import msgpack

# MessagePack parser
def parse_msgpack(data: bytes) -> Any:
    return msgpack.unpackb(data, raw=False)

# CSV line parser
def parse_csv_line(data: bytes) -> list[str]:
    return data.decode().strip().split(",")

# Fixed-point integer (2 decimal places)
def parse_fixed(data: bytes) -> float:
    return int.from_bytes(data, "big", signed=True) / 100
```

### Писане на custom serializer

Serializer е всяка функция `(T) -> bytes`:

```python
import struct

def dump_imu(values: tuple[float, float, float]) -> bytes:
    return struct.pack("<3f", *values)

@hub.watch("actuators/motors", serialize=dump_imu)
def motor_output():
    while True:
        yield (speed_x, speed_y, speed_z)
```

Други примери:

```python
import msgpack

# MessagePack serializer
def dump_msgpack(value: Any) -> bytes:
    return msgpack.packb(value, use_bin_type=True)

# Compact: just the float as 4 bytes
def dump_float(value: float) -> bytes:
    return struct.pack("<f", value)
```

---

## Error handling

- Ако handler гръмне → логва exception, продължава с другите handler-и
- Ако watch producer гръмне → логва exception, periodic продължава на следващия tick, stream спира
- Ако stream функцията не е generator → логва грешка, не crash-ва
- Ако broker-ът не е наличен → paho retry-ва connection автоматично

---

## Тестване

```bash
# Terminal 1: broker
mosquitto -v

# Terminal 2: hub
python examples.py

# Terminal 3: ръчни съобщения
mosquitto_pub -t "sensors/kitchen/temp" -m '{"value": 23.5}'
mosquitto_pub -t "raw/ping" -m "hello"
mosquitto_sub -t "demo/#" -v    # гледай outgoing
```

---

## Файлова структура

```
mqtt_hub.py     ← библиотеката, copy-paste в проекта
examples.py     ← демо на всички възможности
README.md       ← това
```
