-- Executions: historical trade fills (append-only)
CREATE TABLE executions (
    timestamp TIMESTAMP,
    server_env SYMBOL,
    order_id SYMBOL,
    ib_execution_id SYMBOL,
    symbol SYMBOL,
    side SYMBOL,
    quantity DOUBLE,
    price DOUBLE,
    commission DOUBLE,
    strategy SYMBOL,
    latency_us LONG
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

-- Engine Logs: application logs (high volume)
CREATE TABLE engine_logs (
    timestamp TIMESTAMP,
    server_env SYMBOL,
    log_level SYMBOL,
    component SYMBOL,
    message STRING,
    correlation_id UUID,
    data STRING,
    latency_us LONG
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

-- Strategy Signals: when strategies generate buy/sell signals
CREATE TABLE strategy_signals (
    timestamp TIMESTAMP,
    server_env SYMBOL,
    strategy SYMBOL,
    symbol SYMBOL,
    signal_type SYMBOL,
    confidence DOUBLE,
    reason STRING,
    features STRING
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

-- Tick Data: market prices (optional - only if storing market data)
CREATE TABLE tick_data (
    timestamp TIMESTAMP,
    symbol SYMBOL,
    bid DOUBLE,
    ask DOUBLE,
    bid_size LONG,
    ask_size LONG,
    last DOUBLE,
    volume LONG
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;