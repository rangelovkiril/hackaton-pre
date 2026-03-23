"""
examples.py — All mqtt_hub capabilities in one runnable file.

Start mosquitto, then:
    python examples.py

In another terminal, test incoming handlers:
    mosquitto_pub -t "sensors/kitchen/temp" -m '{"value": 23.5}'
    mosquitto_pub -t "raw/ping"             -m 'hello'
    mosquitto_pub -t "binary/imu"           -m "$(printf '\x00\x00\x80\x41\x00\x00\x00\x42\x00\x00\x40\x42')"
"""

import logging
import random
import struct
import time

from mqtt_hub import MQTTHub, json_dump, json_parse, raw, text

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

hub = MQTTHub("localhost")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  INCOMING — @hub.on                                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ── 1. Raw bytes (default, zero overhead) ─────────────────────────────────


@hub.on("raw/#")
def handle_raw(topic: str, payload: bytes):
    print(f"[raw]    {topic}: {payload}")


# ── 2. JSON (opt-in) ─────────────────────────────────────────────────────


@hub.on("sensors/+/temp", parse=json_parse)
def handle_temp(topic: str, payload: dict):
    print(f"[json]   {topic}: {payload['value']}°C")


# ── 3. Plain text ─────────────────────────────────────────────────────────


@hub.on("logs/#", parse=text)
def handle_logs(topic: str, payload: str):
    print(f"[text]   {topic}: {payload}")


# ── 4. Custom parser: struct.unpack for binary sensor data ────────────────


def parse_imu(data: bytes) -> dict:
    """Parse 12 bytes as 3 little-endian floats (ax, ay, az)."""
    ax, ay, az = struct.unpack("<3f", data)
    return {"ax": ax, "ay": ay, "az": az}


@hub.on("binary/imu", parse=parse_imu)
def handle_imu(topic: str, payload: dict):
    print(
        f"[struct] {topic}: ax={payload['ax']:.2f} ay={payload['ay']:.2f} az={payload['az']:.2f}"
    )


# ── 5. Wildcard: catch-all debug listener ─────────────────────────────────


@hub.on("#", parse=text)
def debug_all(topic: str, payload: str):
    print(f"[debug]  {topic}: {payload[:80]}")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  OUTGOING — @hub.watch                                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ── 6. Stream mode: continuous data, publishes on every yield ─────────────


@hub.watch("demo/sensor", serialize=json_dump)
def fake_sensor():
    """Simulates a sensor producing readings at variable rate."""
    while True:
        yield {"value": round(random.uniform(20, 30), 2), "t": time.time()}
        time.sleep(random.uniform(0.3, 1.5))


# ── 7. Stream mode: finite generator (ends naturally) ────────────────────


@hub.watch("demo/countdown", serialize=json_dump)
def countdown():
    """Publishes 5 messages then stops."""
    for i in range(5, 0, -1):
        yield {"remaining": i}
        time.sleep(1.0)


# ── 8. Stream: raw bytes output ──────────────────────────────────────────


@hub.watch("demo/binary")
def binary_stream():
    """Yields packed binary data — no serializer needed with raw_dump."""
    while True:
        value = random.uniform(0, 100)
        yield struct.pack("<f", value)
        time.sleep(2.0)


# ── 9. Stream: yield None to skip a cycle ────────────────────────────────


@hub.watch("demo/conditional", serialize=json_dump)
def conditional_stream():
    """Only publishes when value exceeds threshold."""
    while True:
        value = random.uniform(0, 50)
        if value > 40:
            yield {"alert": True, "value": round(value, 2)}
        else:
            yield None  # skip, nothing published
        time.sleep(1.0)


# ── 10. Periodic mode: heartbeat every N seconds ─────────────────────────


@hub.watch("demo/heartbeat", interval=5.0, serialize=json_dump)
def heartbeat():
    return {"alive": True, "uptime": time.time()}


# ── 11. Periodic: return None to skip ────────────────────────────────────


@hub.watch("demo/periodic_conditional", interval=2.0, serialize=json_dump)
def periodic_conditional():
    """Only publishes every other cycle."""
    if int(time.time()) % 2 == 0:
        return {"tick": True}
    return None  # skipped


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  AD-HOC PUBLISH — hub.publish()                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# These run once after connection.  In real code you'd call publish()
# from inside a handler, an API endpoint, etc.

# ── 12. One-shot JSON ────────────────────────────────────────────────────

# hub.publish("commands/reset", {"action": "reboot"}, serialize=json_dump)

# ── 13. One-shot raw bytes ───────────────────────────────────────────────

# hub.publish("commands/raw", b"\x01\x02\x03")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RUN                                                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    hub.run()
