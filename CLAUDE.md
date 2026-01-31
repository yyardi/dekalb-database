# Trading Database Ingestion Service - Build Instructions

## Project Overview

This ingestion service receives trading events via ZeroMQ and routes them to PostgreSQL and QuestDB databases.

**Architecture:**
```
Trading Engine (Machine 1)
    ↓ ZMQ PUSH
Ingestion Service ← THIS PROJECT
    ↓
    ├→ PostgreSQL (orders, positions, accounts)
    └→ QuestDB (executions, logs, signals)
```

---

## Technology Stack

- Python 3.11+
- ZeroMQ (pyzmq) - Message transport
- asyncpg - PostgreSQL async driver
- questdb - QuestDB Python client (ILP protocol)
- Docker - Containerization

---

## Event Types and Routing

**execution** → PostgreSQL (UPDATE orders, positions) + QuestDB (INSERT executions)
**order_update** → PostgreSQL (UPDATE orders)
**log** → QuestDB (INSERT engine_logs)
**signal** → QuestDB (INSERT strategy_signals)

---

## Database Schemas Reference

See `Backend_Trading_Engine.pdf`:
- PostgreSQL schemas: Pages 10-13
- QuestDB schemas: Pages 13-15

**Key differences:**
- PostgreSQL: UPDATE operations, transactional data
- QuestDB: INSERT only, time-series data with SYMBOL type and PARTITION BY DAY

---

## Connection Configuration

**Local (Development):**
- PostgreSQL: `localhost:5432`
- QuestDB ILP: `localhost:9009`
- QuestDB PostgreSQL wire: `localhost:8812`
- ZMQ listener: `tcp://*:5555`

**Production:**
- PostgreSQL: `db-server:5432` (via Tailscale VPN)
- QuestDB ILP: `db-server:9009`
- QuestDB PostgreSQL wire: `db-server:8812`

---

## Message Format

Events arrive as batches via ZMQ:

```json
{
  "type": "batch",
  "batch_time": "2026-01-31T14:30:05.000Z",
  "count": 3,
  "events": [
    {
      "type": "execution",
      "timestamp": "2026-01-31T14:30:00.123Z",
      "server_env": "paper",
      "data": {
        "order_id": "123",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 100,
        "price": 185.40,
        "commission": 1.00,
        "strategy": "momentum_v1"
      }
    }
  ]
}
```

---

## Build Order

Build files in this sequence for proper dependency management.

---

## FILE 1: requirements.txt

```
Create requirements.txt with these dependencies:
- pyzmq>=25.1.0
- asyncpg>=0.29.0
- questdb>=1.1.0
- python-dotenv>=1.0.0

Pin versions for production stability.
```

---

## FILE 2: config.py

```
Create a configuration module:

Required settings:
- DB_HOST: Environment variable with default 'localhost'
- POSTGRES_PORT: 5432
- POSTGRES_DB: 'trading'
- POSTGRES_USER: 'postgres'
- POSTGRES_PASSWORD: 'postgres'
- QUESTDB_ILP_HOST: Same as DB_HOST
- QUESTDB_ILP_PORT: 9009
- ZMQ_BIND_ADDRESS: 'tcp://*:5555'

Use os.getenv() with fallback defaults.
Allow easy switching between local and production via DB_HOST environment variable.
```

---

## FILE 3: ingestion-service/db_writers/postgres_writer.py

```
Create PostgresWriter class with async methods:

__init__(config):
  Store database configuration

async connect():
  Create asyncpg connection pool
  Return the pool object

async update_order(event):
  SQL: UPDATE orders 
       SET status = $1, 
           filled_quantity = $2, 
           avg_fill_price = $3,
           commission = $4,
           updated_at = now()
       WHERE order_id = $5
  
  Extract from event['data']:
  - order_id, status, filled_quantity, avg_fill_price, commission
  
  Use parameterized queries ($1, $2, etc.) to prevent SQL injection
  Log errors but return False instead of crashing
  Return True on success

async update_position(event):
  Calculate:
  - If side='BUY': new_quantity = current_quantity + quantity
  - If side='SELL': new_quantity = current_quantity - quantity
  - new_avg_cost = weighted average of (old_cost * old_qty + price * qty) / new_qty
  
  SQL: INSERT INTO positions (server_env, account_id, symbol, quantity, avg_cost, updated_at)
       VALUES ($1, $2, $3, $4, $5, now())
       ON CONFLICT (server_env, account_id, symbol)
       DO UPDATE SET quantity = $4, avg_cost = $5, updated_at = now()
  
  This is an UPSERT (insert or update)
  Extract from event: symbol, side, quantity, price, server_env
  Use account_id from event['data'] or default to 'PAPER_ACCOUNT'

async close():
  Close connection pool

Include logging for all operations.
Handle all exceptions gracefully.
```

---

## FILE 4: ingestion-service/db_writers/questdb_writer.py

```
Create QuestDBWriter class:

__init__(config):
  Store configuration

connect():
  Create QuestDB Sender using ILP protocol
  Connect to config.QUESTDB_ILP_HOST on port 9009

insert_execution(event):
  Format for QuestDB ILP (InfluxDB Line Protocol):
  
  Table: executions
  Tags (SYMBOL columns): server_env, order_id, ib_execution_id, symbol, side, strategy
  Fields (DOUBLE/LONG): quantity, price, commission, latency_us
  Timestamp: Convert event timestamp to nanoseconds since epoch
  
  Example ILP line:
  executions,server_env=paper,symbol=AAPL,side=BUY,strategy=momentum_v1 quantity=100,price=185.40,commission=1.00 1706716800000000000
  
  Extract all fields from event['data']
  Send via sender.row() method
  Flush after each write

insert_log(event):
  Table: engine_logs
  Tags: server_env, log_level, component
  Fields: message (STRING), data (STRING), latency_us (LONG)
  Timestamp: event timestamp in nanoseconds

insert_signal(event):
  Table: strategy_signals
  Tags: server_env, strategy, symbol, signal_type
  Fields: confidence (DOUBLE), reason (STRING), features (STRING)
  Timestamp: event timestamp in nanoseconds

close():
  Close ILP sender connection

Log all operations and handle errors gracefully.
```

---

## FILE 5: ingestion-service/router.py

```
Create EventRouter class:

__init__(postgres_writer, questdb_writer):
  Store writer instances

async route_event(event):
  Extract event_type from event['type']
  
  Routing logic:
  
  if event_type == "execution":
      await postgres_writer.update_order(event)
      await postgres_writer.update_position(event)
      questdb_writer.insert_execution(event)
      log: "Routed execution event for order {order_id}"
      
  elif event_type == "order_update":
      await postgres_writer.update_order(event)
      log: "Routed order_update for order {order_id}"
      
  elif event_type == "log":
      questdb_writer.insert_log(event)
      log: "Routed log event: {log_level}"
      
  elif event_type == "signal":
      questdb_writer.insert_signal(event)
      log: "Routed signal event for {symbol}"
      
  else:
      log warning: "Unknown event type: {event_type}"
      return 0
  
  Wrap all operations in try/except
  Count successful writes
  Return count of successful operations

Include detailed logging at INFO level for routing decisions.
```

---

## FILE 6: ingestion-service/main.py

```
Create main entry point:

Imports:
- zmq, asyncio, json, logging, time
- config, PostgresWriter, QuestDBWriter, EventRouter

Setup:
1. Configure logging (console, INFO level, include timestamps)
2. Log: "Starting ingestion service..."
3. Initialize PostgresWriter with config
4. Initialize QuestDBWriter with config
5. Connect both writers
6. Create EventRouter with both writers
7. Create ZMQ context
8. Create PULL socket
9. Bind to config.ZMQ_BIND_ADDRESS
10. Log: "Listening for events on port 5555"

Main loop (async):
  while True:
      # Receive message (blocking)
      message_bytes = socket.recv()
      message = json.loads(message_bytes)
      
      # Extract batch
      events = message.get('events', [])
      batch_count = len(events)
      
      # Start timer
      start_time = time.time()
      
      # Process each event
      for event in events:
          await router.route_event(event)
      
      # Log batch summary
      elapsed_ms = (time.time() - start_time) * 1000
      log: "Processed {batch_count} events in {elapsed_ms:.2f}ms"

Graceful shutdown:
  On KeyboardInterrupt:
      log: "Shutting down..."
      await postgres_writer.close()
      questdb_writer.close()
      socket.close()
      log: "Service stopped"

Handle all exceptions - service must never crash.
```

---

## FILE 7: docker-compose.yml

```
Create docker-compose.yml with 3 services:

version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: trading
    ports:
      - "5432:5432"
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  questdb:
    image: questdb/questdb:latest
    ports:
      - "9000:9000"   # Web console
      - "8812:8812"   # PostgreSQL wire protocol
      - "9009:9009"   # ILP (InfluxDB Line Protocol)
    volumes:
      - ./questdb-data:/var/lib/questdb

  ingestion-service:
    build: ./ingestion-service
    ports:
      - "5555:5555"
    environment:
      - DB_HOST=postgres
      - QUESTDB_ILP_HOST=questdb
    depends_on:
      postgres:
        condition: service_healthy
      questdb:
        condition: service_started
    restart: unless-stopped

networks:
  default:
    name: trading-network
```

---

## FILE 8: ingestion-service/Dockerfile

```
Create Dockerfile:

FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the service
CMD ["python", "main.py"]
```

---

## FILE 9: tests/fake_zmq_sender.py

```
Create test script that sends fake events:

1. Import zmq, json, time, datetime
2. Create ZMQ PUSH socket
3. Connect to tcp://localhost:5555
4. Log: "Connected to ingestion service"

Function create_batch(batch_num):
  Create a batch with 3 events:
  
  Event 1 - order_update:
    type: "order_update"
    timestamp: now() in ISO format
    server_env: "paper"
    data:
      order_id: f"TEST{batch_num:03d}"
      symbol: "AAPL"
      status: "SUBMITTED"
  
  Event 2 - execution:
    type: "execution"
    timestamp: now() + 1 second
    server_env: "paper"
    data:
      order_id: f"TEST{batch_num:03d}"
      ib_execution_id: f"IB{batch_num:05d}"
      symbol: "AAPL"
      side: "BUY"
      quantity: 100
      price: 185.40
      commission: 1.00
      strategy: "momentum_v1"
      latency_us: 1500
  
  Event 3 - log:
    type: "log"
    timestamp: now() + 2 seconds
    server_env: "paper"
    data:
      log_level: "INFO"
      component: "test_sender"
      message: f"Test batch {batch_num} sent successfully"
      data: "{}"
      latency_us: 200
  
  Return batch dict with: type="batch", batch_time=now(), count=3, events=[...]

Main loop:
  for i in range(1, 6):  # Send 5 batches
      batch = create_batch(i)
      socket.send_json(batch)
      print(f"Sent batch {i} with {batch['count']} events")
      time.sleep(2)  # Wait 2 seconds between batches
  
  print("All batches sent!")
  socket.close()
```

---

## FILE 10: README.md

```
Create comprehensive README:

# Trading Database Ingestion Service

## Overview
Receives trading events via ZeroMQ and routes them to PostgreSQL and QuestDB.

## Architecture
```
Trading Engine → ZMQ → Ingestion Service → PostgreSQL + QuestDB
```

## Prerequisites
- Docker Desktop installed
- Python 3.11+ (for local testing without Docker)
- Git

## Quick Start

### 1. Clone Repository
```bash
git clone <repo-url>
cd trading-database
```

### 2. Start Services
```bash
docker-compose up --build
```

This starts:
- PostgreSQL on port 5432
- QuestDB on ports 9000, 8812, 9009
- Ingestion service on port 5555

### 3. Create Database Schemas

PostgreSQL (visit http://localhost:8080 - Adminer):
- Run schemas/postgresql_schema.sql

QuestDB (visit http://localhost:9000):
- Run schemas/questdb_schema.sql

### 4. Test with Fake Data
```bash
python tests/fake_zmq_sender.py
```

### 5. Verify Data

PostgreSQL:
```sql
SELECT * FROM orders;
SELECT * FROM positions;
```

QuestDB:
```sql
SELECT * FROM executions;
SELECT * FROM engine_logs;
```

## Configuration

Environment variables (set in docker-compose.yml or .env):
- `DB_HOST`: PostgreSQL hostname (default: localhost)
- `QUESTDB_ILP_HOST`: QuestDB hostname (default: localhost)

## Deployment to Production

Change docker-compose.yml environment:
```yaml
environment:
  - DB_HOST=db-server  # Tailscale hostname
  - QUESTDB_ILP_HOST=db-server
```

Remove local database containers (use remote db-server instead).

## Project Structure
```
trading-database/
├── ingestion-service/      # Python service
│   ├── main.py            # Entry point
│   ├── router.py          # Event routing logic
│   ├── config.py          # Configuration
│   └── db_writers/        # Database writers
├── schemas/               # SQL table definitions
├── tests/                 # Testing utilities
└── docker-compose.yml     # Docker orchestration
```

## Event Types

| Type | PostgreSQL | QuestDB |
|------|-----------|---------|
| execution | UPDATE orders, positions | INSERT executions |
| order_update | UPDATE orders | - |
| log | - | INSERT engine_logs |
| signal | - | INSERT strategy_signals |

## Troubleshooting

**Service won't start:**
- Check Docker containers: `docker-compose ps`
- View logs: `docker-compose logs ingestion-service`

**Database connection errors:**
- Verify databases are running: `docker-compose ps`
- Check credentials in config.py

**Events not appearing:**
- Check ingestion service logs
- Verify ZMQ connection to port 5555
- Test with fake_zmq_sender.py

## Development

Run locally without Docker:
```bash
pip install -r ingestion-service/requirements.txt
python ingestion-service/main.py
```

## License
Internal use only - Dekalb Capital
```

---

## FILE 11: .gitignore

```
Create .gitignore:

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/

# Docker
postgres-data/
questdb-data/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local

# OS
.DS_Store
Thumbs.db
```

---

## Testing Checklist

After building all files:

1. ✅ Docker containers start: `docker-compose up`
2. ✅ PostgreSQL accessible: http://localhost:8080
3. ✅ QuestDB accessible: http://localhost:9000
4. ✅ Database schemas created
5. ✅ Fake sender sends events: `python tests/fake_zmq_sender.py`
6. ✅ Data appears in PostgreSQL orders table
7. ✅ Data appears in QuestDB executions table
8. ✅ Service logs show successful routing

---

## Production Deployment Steps

1. Push code to GitHub
2. SSH to db-server
3. Clone repository
4. Modify docker-compose.yml to remove postgres/questdb services
5. Set DB_HOST=localhost (db-server's local databases)
6. Run `docker-compose up -d ingestion-service`
7. Monitor logs: `docker-compose logs -f`

---

End of build instructions.