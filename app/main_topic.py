# orders_service/main_topic.py
import aio_pika
import json
import os

RABBIT_URL = os.getenv("RABBIT_URL")
EXCHANGE_NAME = "topic_logs"

async def publish_message(routing_key: str, payload: dict):
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC
    )

    message = aio_pika.Message(body=json.dumps(payload).encode())

    await exchange.publish(message, routing_key=routing_key)
    print(f"[main_topic.py] Sent → {routing_key}: {payload}")

    await connection.close()
