"""RocketMQ 收发（可选依赖 rocketmq-client-python；不可用则走 HTTP 降级）。"""

try:
    from rocketmq.client import Message, Producer, PushConsumer

    ROCKETMQ_AVAILABLE = True
except Exception:  # pragma: no cover
    ROCKETMQ_AVAILABLE = False


def send(topic: str, payload: str, nameserver: str = None):
    if not ROCKETMQ_AVAILABLE:
        return False
    try:
        from ..core.config import settings

        producer = Producer("generation-producer")
        producer.set_name_server_address(nameserver or settings.mq_nameserver)
        producer.start()
        msg = Message(topic)
        msg.set_body(payload)
        producer.send_sync(msg)
        producer.shutdown()
        return True
    except Exception as e:
        print(f"[warn] rocketmq send failed: {e}")
        return False
