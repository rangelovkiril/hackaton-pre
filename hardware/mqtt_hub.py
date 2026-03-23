"""
mqtt_hub — Plug & play MQTT client for hackathons.

    from mqtt_hub import MQTTHub, json_parse, json_dump, text

Single file, one dependency (paho-mqtt), decorator-based, open-closed.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger("mqtt_hub")

# ─── Parsers & serializers ────────────────────────────────────────────────────
#
# Parser:     Callable[[bytes], T]   — transforms incoming raw bytes
# Serializer: Callable[[T], bytes]   — transforms outgoing value to bytes
#
# Built-ins are provided below.  Drop in any function with the right
# signature for custom formats (struct, msgpack, protobuf, …).

Parser = Callable[[bytes], Any]
Serializer = Callable[[Any], bytes]
TopicHandler = Callable[[str, Any], None]
WatchProducer = Callable[[], Any]


def raw(data: bytes) -> bytes:
    """No-op parser — returns raw bytes.  (Default for @hub.on)"""
    return data


def json_parse(data: bytes) -> Any:
    """Parse bytes as JSON."""
    return json.loads(data)


def text(data: bytes) -> str:
    """Decode bytes as UTF-8."""
    return data.decode("utf-8", errors="replace")


def json_dump(value: Any) -> bytes:
    """Serialize to JSON bytes."""
    return json.dumps(value, ensure_ascii=False).encode()


def raw_dump(value: Any) -> bytes:
    """Best-effort serializer: bytes pass through, dict/list → JSON, else str."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False).encode()
    return str(value).encode()


# ─── Internals ────────────────────────────────────────────────────────────────


def _mqtt_pattern_to_regex(pattern: str) -> re.Pattern:
    parts = []
    for segment in pattern.split("/"):
        if segment == "+":
            parts.append(r"[^/]+")
        elif segment == "#":
            parts.append(r".*")
        else:
            parts.append(re.escape(segment))
    return re.compile("^" + "/".join(parts) + "$")


@dataclass
class _Subscription:
    pattern: str
    regex: re.Pattern
    handler: TopicHandler
    parse: Parser
    qos: int


@dataclass
class _WatchJob:
    topic: str
    producer: WatchProducer
    serialize: Serializer
    qos: int
    retain: bool
    interval: float | None = None
    _timer: threading.Timer | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)


# ─── Hub ──────────────────────────────────────────────────────────────────────


class MQTTHub:
    """
    Open-closed MQTT client.

    Register handlers with @hub.on() and publishers with @hub.watch().
    The core never needs modification.
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        *,
        client_id: str = "",
        username: str | None = None,
        password: str | None = None,
        keepalive: int = 60,
    ):
        self._broker = broker
        self._port = port
        self._keepalive = keepalive

        self._client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if username:
            self._client.username_pw_set(username, password)

        self._subscriptions: list[_Subscription] = []
        self._watches: list[_WatchJob] = []
        self._running = threading.Event()

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    # ── Incoming ──────────────────────────────────────────────────────────

    def on(
        self,
        topic_pattern: str,
        *,
        parse: Parser = raw,
        qos: int = 0,
    ):
        """
        Decorator — subscribe to a topic pattern and handle messages.

        Args:
            topic_pattern: MQTT topic with optional wildcards (+ / #).
            parse:         Callable[[bytes], T] applied to raw payload
                           before it reaches the handler.  Default: raw.
            qos:           MQTT QoS level (0, 1, or 2).
        """

        def decorator(fn: TopicHandler):
            sub = _Subscription(
                pattern=topic_pattern,
                regex=_mqtt_pattern_to_regex(topic_pattern),
                handler=fn,
                parse=parse,
                qos=qos,
            )
            self._subscriptions.append(sub)
            logger.debug("Registered handler for %s → %s", topic_pattern, fn.__name__)
            return fn

        return decorator

    # ── Outgoing ──────────────────────────────────────────────────────────

    def watch(
        self,
        topic: str,
        *,
        interval: float | None = None,
        serialize: Serializer = raw_dump,
        qos: int = 0,
        retain: bool = False,
    ):
        """
        Decorator — publish outgoing data on a topic.

        Mode is chosen by the presence of `interval`:

        Stream (interval=None, default):
            Function must be a generator.  Runs in a daemon thread.
            Each yielded value is published immediately.

        Periodic (interval=<seconds>):
            Regular callable, invoked every N seconds.
            Return value is published; return None to skip a cycle.

        Args:
            topic:     MQTT topic to publish on.
            interval:  None → stream mode, float → periodic mode.
            serialize: Callable[[T], bytes] applied to the value
                       before publishing.  Default: raw_dump.
            qos:       MQTT QoS level.
            retain:    MQTT retain flag.
        """

        def decorator(fn: WatchProducer):
            job = _WatchJob(
                topic=topic,
                producer=fn,
                serialize=serialize,
                interval=interval,
                qos=qos,
                retain=retain,
            )
            self._watches.append(job)
            mode = "periodic" if interval else "stream"
            logger.debug("Registered %s watch %s → %s", mode, topic, fn.__name__)
            return fn

        return decorator

    def publish(
        self,
        topic: str,
        payload: Any = b"",
        *,
        serialize: Serializer = raw_dump,
        qos: int = 0,
        retain: bool = False,
    ):
        """One-shot publish.  Serializer is configurable."""
        self._client.publish(topic, serialize(payload), qos=qos, retain=retain)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def run(self):
        """Connect, subscribe, start watches, block until Ctrl-C."""
        self._running.set()

        self._client.connect(self._broker, self._port, self._keepalive)
        self._client.loop_start()

        time.sleep(0.3)
        self._start_watches()

        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())

        logger.info("MQTTHub running — %s:%d", self._broker, self._port)
        stop.wait()
        self.stop()

    def stop(self):
        """Graceful shutdown."""
        if not self._running.is_set():
            return
        self._running.clear()
        logger.info("Shutting down…")

        for job in self._watches:
            if job._timer:
                job._timer.cancel()

        self._client.loop_stop()
        self._client.disconnect()

    # ── Paho internals ────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            logger.error("Connection failed (rc=%d)", rc)
            return
        logger.info("Connected to %s:%d", self._broker, self._port)
        for sub in self._subscriptions:
            client.subscribe(sub.pattern, qos=sub.qos)
            logger.debug("Subscribed to %s (qos=%d)", sub.pattern, sub.qos)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        matched = False
        for sub in self._subscriptions:
            if sub.regex.match(msg.topic):
                matched = True
                try:
                    payload = sub.parse(msg.payload)
                    sub.handler(msg.topic, payload)
                except Exception:
                    logger.exception(
                        "Handler %s crashed on %s", sub.handler.__name__, msg.topic
                    )
        if not matched:
            logger.debug("No handler for %s", msg.topic)

    # ── Watch internals ───────────────────────────────────────────────────

    def _start_watches(self):
        for job in self._watches:
            if job.interval is not None:
                self._tick_periodic(job)
            else:
                self._start_stream(job)

    def _tick_periodic(self, job: _WatchJob):
        if not self._running.is_set():
            return
        try:
            result = job.producer()
            if result is not None:
                self._client.publish(
                    job.topic, job.serialize(result), qos=job.qos, retain=job.retain
                )
        except Exception:
            logger.exception("Watch %s crashed", job.producer.__name__)

        job._timer = threading.Timer(job.interval, self._tick_periodic, args=(job,))
        job._timer.daemon = True
        job._timer.start()

    def _start_stream(self, job: _WatchJob):
        def _run():
            name = job.producer.__name__
            logger.debug("Stream started: %s → %s", name, job.topic)
            try:
                gen = job.producer()
                if not inspect.isgenerator(gen):
                    logger.error(
                        "%s is in stream mode but didn't return a generator. "
                        "Use 'yield' in the function body.",
                        name,
                    )
                    return
                for value in gen:
                    if not self._running.is_set():
                        gen.close()
                        return
                    if value is not None:
                        self._client.publish(
                            job.topic,
                            job.serialize(value),
                            qos=job.qos,
                            retain=job.retain,
                        )
            except StopIteration:
                logger.info("Stream %s finished", name)
            except Exception:
                logger.exception("Stream %s crashed", name)

        job._thread = threading.Thread(
            target=_run, name=f"watch-{job.topic}", daemon=True
        )
        job._thread.start()
