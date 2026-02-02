import logging
import asyncio


class EventRouter:
    def __init__(self, postgres_writer, questdb_writer):
        self.postgres_writer = postgres_writer
        self.questdb_writer = questdb_writer

    async def route_event(self, event):
        try:
            event_type = event.get('type')

            if event_type == 'execution':
                # Trade executed - update both databases
                await self.postgres_writer.update_order(event)
                await self.postgres_writer.update_position(event)
                self.questdb_writer.insert_execution(event)
                logging.info(f"Routed execution for order {event['data'].get('order_id')}")

            elif event_type == 'order_update':
                # Order status changed - PostgreSQL only
                await self.postgres_writer.update_order(event)
                logging.info(f"Routed order_update for {event['data'].get('order_id')}")

            elif event_type == 'log':
                # Application log - QuestDB only
                self.questdb_writer.insert_log(event)
                logging.debug("Routed log event")

            elif event_type == 'signal':
                # Strategy signal - QuestDB only
                self.questdb_writer.insert_signal(event)
                logging.info(f"Routed signal for {event['data'].get('symbol')}")

            else:
                logging.warning(f"Unknown event type: {event_type}")

        except Exception as e:
            logging.error(f"Error routing event: {e}")
