# Python Ingestion Service - Build Specifications

## Context

Building a Python service that receives trading events via ZeroMQ and routes them to PostgreSQL and QuestDB databases.

**Event Flow:**
```
ZMQ Message (port 5555) → Router → PostgreSQL (orders, positions) + QuestDB (executions, logs)
```

**Event Types & Routing:**
- `execution` → PostgreSQL (UPDATE orders, UPDATE positions) + QuestDB (INSERT executions)
- `order_update` → PostgreSQL (UPDATE orders only)
- `log` → QuestDB (INSERT engine_logs only)
- `signal` → QuestDB (INSERT strategy_signals only)

**Database Connection Info:**
- PostgreSQL: `DB_HOST:5432`, database='trading', user='postgres', password='postgres'
- QuestDB ILP: `QUESTDB_ILP_HOST:9009` (InfluxDB Line Protocol for fast inserts)
- DB_HOST defaults to 'localhost' for local testing, 'postgres' in Docker, 'db-server' in production

---

## FILE 1: ingestion-service/config.py

Configuration module using environment variables with defaults.

```python
import os

# PostgreSQL
DB_HOST = os.getenv('DB_HOST', 'localhost')
POSTGRES_PORT = 5432
POSTGRES_DB = 'trading'
POSTGRES_USER = 'postgres'
POSTGRES_PASSWORD = 'postgres'

# QuestDB
QUESTDB_ILP_HOST = os.getenv('QUESTDB_ILP_HOST', 'localhost')
QUESTDB_ILP_PORT = 9009

# ZeroMQ
ZMQ_BIND_ADDRESS = 'tcp://*:5555'
```

**Requirements:**
- Use `os.getenv()` with fallback defaults
- DB_HOST and QUESTDB_ILP_HOST can be overridden via environment variables
- Keep it simple - just variable assignments

---

## FILE 2: ingestion-service/db_writers/__init__.py

Empty file to make db_writers a Python package.

```python
# Empty file
```

---

## FILE 3: ingestion-service/db_writers/postgres_writer.py

PostgreSQL writer using asyncpg for async database operations.

**Class: PostgresWriter**

### `__init__(self, config)`
Store config module reference.

### `async connect(self)`
```python
import asyncpg

self.pool = await asyncpg.create_pool(
    host=config.DB_HOST,
    port=config.POSTGRES_PORT,
    database=config.POSTGRES_DB,
    user=config.POSTGRES_USER,
    password=config.POSTGRES_PASSWORD
)
```

### `async update_order(self, event)`
Updates order status when order state changes.

**Extract from `event['data']`:**
- `order_id` (required)
- `status` (e.g., 'SUBMITTED', 'FILLED')
- `filled_quantity` (optional, default 0)
- `avg_fill_price` (optional, default None)
- `commission` (optional, default None)

**SQL:**
```sql
UPDATE orders 
SET status = $1, 
    filled_quantity = $2, 
    avg_fill_price = $3,
    commission = $4,
    updated_at = now()
WHERE order_id = $5
```

**Execute:**
```python
await self.pool.execute(
    sql,
    status,
    filled_quantity,
    avg_fill_price,
    commission,
    order_id
)
```

**Error Handling:**
- Wrap in try/except
- Log errors with `logging.error()`
- Return `True` on success, `False` on failure
- Don't crash the service

### `async update_position(self, event)`
Updates position after trade execution (UPSERT - insert if new, update if exists).

**Extract from `event['data']`:**
- `symbol` (e.g., 'AAPL')
- `side` ('BUY' or 'SELL')
- `quantity` (shares traded)
- `price` (execution price)
- `server_env` (from event root, e.g., 'paper')
- `account_id` (optional, default to 'PAPER_ACCOUNT')

**Logic:**
- For simple version: just update quantity, don't worry about avg_cost calculation yet
- BUY: add quantity
- SELL: subtract quantity

**SQL (UPSERT):**
```sql
INSERT INTO positions (server_env, account_id, symbol, quantity, updated_at)
VALUES ($1, $2, $3, $4, now())
ON CONFLICT (server_env, account_id, symbol)
DO UPDATE SET 
    quantity = positions.quantity + $4,
    updated_at = now()
```

**Note:** The `+` in the UPDATE clause handles both BUY (positive quantity) and SELL (negative quantity)

**Error Handling:** Same as update_order

### `async close(self)`
```python
await self.pool.close()
```

**Imports needed:**
```python
import asyncpg
import logging
```

**Logging:** Add `logging.info()` for successful operations, `logging.error()` for failures

---

## FILE 4: ingestion-service/db_writers/questdb_writer.py

QuestDB writer using ILP (InfluxDB Line Protocol) for high-speed inserts.

**Class: QuestDBWriter**

### `__init__(self, config)`
Store config module reference.

### `connect(self)`
```python
from questdb.ingress import Sender, IngressError

self.sender = Sender(
    host=config.QUESTDB_ILP_HOST,
    port=config.QUESTDB_ILP_PORT
)
```

### `insert_execution(self, event)`
Inserts trade execution into time-series database.

**ILP Format:**
```
table_name,tag1=value1,tag2=value2 field1=value1,field2=value2 timestamp_nanos
```

**Extract from event:**
- `timestamp` (root level, ISO format string)
- `server_env` (root level, e.g., 'paper')
- From `event['data']`:
  - `order_id`
  - `ib_execution_id`
  - `symbol`
  - `side`
  - `quantity`
  - `price`
  - `commission`
  - `strategy`

**Tags (SYMBOL columns):** server_env, order_id, ib_execution_id, symbol, side, strategy
**Fields (numeric):** quantity, price, commission
**Timestamp:** Convert ISO string to nanoseconds since epoch

**Code:**
```python
from datetime import datetime

# Convert timestamp
dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
timestamp_ns = int(dt.timestamp() * 1_000_000_000)

# Build ILP message
self.sender.row(
    'executions',
    symbols={
        'server_env': event['server_env'],
        'order_id': event['data']['order_id'],
        'ib_execution_id': event['data'].get('ib_execution_id', ''),
        'symbol': event['data']['symbol'],
        'side': event['data']['side'],
        'strategy': event['data'].get('strategy', 'unknown')
    },
    columns={
        'quantity': event['data']['quantity'],
        'price': event['data']['price'],
        'commission': event['data'].get('commission', 0.0)
    },
    at=timestamp_ns
)
self.sender.flush()
```

**Error Handling:** Wrap in try/except, log errors, return True/False

### `insert_log(self, event)`
Similar to insert_execution but for engine_logs table.

**Tags:** server_env, log_level, component
**Fields:** message (string), data (string)

```python
self.sender.row(
    'engine_logs',
    symbols={
        'server_env': event['server_env'],
        'log_level': event['data']['log_level'],
        'component': event['data']['component']
    },
    columns={
        'message': event['data']['message'],
        'data': event['data'].get('data', '{}')
    },
    at=timestamp_ns
)
self.sender.flush()
```

### `insert_signal(self, event)`
Similar for strategy_signals table.

**Tags:** server_env, strategy, symbol, signal_type
**Fields:** confidence (float), reason (string), features (string)

```python
self.sender.row(
    'strategy_signals',
    symbols={
        'server_env': event['server_env'],
        'strategy': event['data']['strategy'],
        'symbol': event['data']['symbol'],
        'signal_type': event['data']['signal_type']
    },
    columns={
        'confidence': event['data'].get('confidence', 0.0),
        'reason': event['data'].get('reason', ''),
        'features': event['data'].get('features', '')
    },
    at=timestamp_ns
)
self.sender.flush()
```

### `close(self)`
```python
self.sender.close()
```

**Imports needed:**
```python
from questdb.ingress import Sender, IngressError
from datetime import datetime
import logging
```

---

## FILE 5: ingestion-service/router.py

Event routing logic - the "brain" that decides where each event goes.

**Class: EventRouter**

### `__init__(self, postgres_writer, questdb_writer)`
Store references to both database writers.

### `async route_event(self, event)`
Route a single event to the appropriate database(s).

**Logic:**
```python
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
```

**Error Handling:**
- Wrap entire method in try/except
- Log errors but don't crash
- If one write fails, continue with others

**Imports needed:**
```python
import logging
import asyncio
```

---

## FILE 6: ingestion-service/main.py

Entry point - sets up ZMQ listener and processes incoming batches.

**Main function structure:**
```python
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
    # 1. Initialize database writers
    postgres_writer = PostgresWriter(config)
    questdb_writer = QuestDBWriter(config)
    
    # 2. Connect to databases
    await postgres_writer.connect()
    questdb_writer.connect()
    logging.info("Connected to databases")
    
    # 3. Create router
    router = EventRouter(postgres_writer, questdb_writer)
    
    # 4. Set up ZMQ socket
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(config.ZMQ_BIND_ADDRESS)
    logging.info(f"Listening on {config.ZMQ_BIND_ADDRESS}")
    
    # 5. Main event loop
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
        questdb_writer.close()
        socket.close()
        context.term()
        logging.info("Service stopped")

if __name__ == '__main__':
    asyncio.run(main())
```

**Key Points:**
- Use asyncio for PostgreSQL operations
- ZMQ recv() is blocking - that's OK
- Process events sequentially (can optimize later)
- Never crash - catch all exceptions
- Log everything important

---

## FILE 7: ingestion-service/Dockerfile

Container definition for the ingestion service.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better Docker caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the service
CMD ["python", "main.py"]
```

**Keep it simple - this is all you need.**

---

## FILE 8: tests/fake_zmq_sender.py

Test tool to send fake events to the ingestion service.

**Requirements:**
1. Create ZMQ PUSH socket
2. Connect to `tcp://localhost:5555`
3. Send 5 batches of events (with 2 second delay between)
4. Each batch contains 3 events: order_update, execution, log

**Code structure:**
```python
import zmq
import json
import time
from datetime import datetime, timedelta

def create_batch(batch_num):
    """Create a batch of 3 test events"""
    now = datetime.utcnow()
    
    events = [
        # Event 1: Order update
        {
            'type': 'order_update',
            'timestamp': now.isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'order_id': f'TEST{batch_num:03d}',
                'symbol': 'AAPL',
                'status': 'SUBMITTED',
                'quantity': 100
            }
        },
        # Event 2: Execution
        {
            'type': 'execution',
            'timestamp': (now + timedelta(seconds=1)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'order_id': f'TEST{batch_num:03d}',
                'ib_execution_id': f'IB{batch_num:05d}',
                'symbol': 'AAPL',
                'side': 'BUY',
                'quantity': 100,
                'price': 185.40,
                'commission': 1.00,
                'strategy': 'test_strategy'
            }
        },
        # Event 3: Log
        {
            'type': 'log',
            'timestamp': (now + timedelta(seconds=2)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'log_level': 'INFO',
                'component': 'test_sender',
                'message': f'Test batch {batch_num} sent successfully',
                'data': '{}'
            }
        }
    ]
    
    return {
        'type': 'batch',
        'batch_time': now.isoformat() + 'Z',
        'count': len(events),
        'events': events
    }

def main():
    # Set up ZMQ
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect('tcp://localhost:5555')
    print("Connected to ingestion service on port 5555")
    
    # Send 5 batches
    for i in range(1, 6):
        batch = create_batch(i)
        socket.send_json(batch)
        print(f"Sent batch {i} with {batch['count']} events")
        time.sleep(2)
    
    print("All test batches sent!")
    socket.close()
    context.term()

if __name__ == '__main__':
    main()
```

---

## Build Checklist

After building all files:

1. ✅ All 8 Python files created
2. ✅ No syntax errors
3. ✅ All imports are correct
4. ✅ Logging is configured properly
5. ✅ Error handling is in place
6. ✅ Code follows the specifications exactly

---

## Testing After Build

```bash
# Start Docker containers
docker-compose up --build

# In another terminal, send test events
python tests/fake_zmq_sender.py

# Check logs
docker-compose logs -f ingestion-service

# Verify data in databases
# PostgreSQL: http://localhost:8080
# QuestDB: http://localhost:9000
```

---

End of specifications.