import zmq
import asyncio
import json
import logging
import time
from db_writers.postgres_writer import PostgresWriter
from db_writers.questdb_writer import QuestDBWriter
from router import EventRouter
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    # Give databases time to start up
    logging.info("Waiting 5 seconds for databases to be ready...")
    await asyncio.sleep(5)
    
    # Initialize database writers
    logging.info("Initializing database writers...")
    postgres_writer = PostgresWriter(config)
    questdb_writer = QuestDBWriter(config)
    
    # Connect to PostgreSQL only (QuestDB connects per-write)
    logging.info("Connecting to databases...")
    await postgres_writer.connect()
    logging.info("Connected to databases")
    
    # Create router
    router = EventRouter(postgres_writer, questdb_writer)
    
    # Set up ZMQ socket
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(config.ZMQ_BIND_ADDRESS)
    logging.info(f"Listening on {config.ZMQ_BIND_ADDRESS}")
    
    # Main event loop
    try:
        while True:
            # Receive message (blocking)
            message_bytes = socket.recv()
            message = json.loads(message_bytes)
            
            # Extract events
            events = message.get('events', [])
            logging.info(f"Received batch with {len(events)} events")
            
            # Process each event
            start_time = time.time()
            for event in events:
                await router.route_event(event)
            
            # Log performance
            elapsed_ms = (time.time() - start_time) * 1000
            logging.info(f"Processed {len(events)} events in {elapsed_ms:.2f}ms")
    
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    
    finally:
        # Cleanup
        await postgres_writer.close()
        socket.close()
        context.term()
        logging.info("Service stopped")

if __name__ == '__main__':
    asyncio.run(main())