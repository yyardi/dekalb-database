-- Orders: tracks every order from submission to fill
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    ib_order_id VARCHAR(50),
    server_env VARCHAR(10) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    order_type VARCHAR(20),
    quantity DECIMAL(18,8) NOT NULL,
    limit_price DECIMAL(18,8),
    status VARCHAR(20) NOT NULL,
    strategy_name VARCHAR(50),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_quantity DECIMAL(18,8) DEFAULT 0,
    avg_fill_price DECIMAL(18,8),
    commission DECIMAL(10,4),
    metadata JSONB
);

CREATE INDEX idx_orders_status ON orders(status) WHERE status IN ('SUBMITTED', 'ACKNOWLEDGED');
CREATE INDEX idx_orders_symbol ON orders(symbol, submitted_at DESC);
CREATE INDEX idx_orders_updated ON orders(updated_at DESC);

-- Positions: current holdings
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    server_env VARCHAR(10) NOT NULL,
    account_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(18,8) NOT NULL DEFAULT 0,
    avg_cost DECIMAL(18,8),
    market_value DECIMAL(18,8),
    unrealized_pnl DECIMAL(18,8),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(server_env, account_id, symbol)
);

CREATE INDEX idx_positions_account ON positions(account_id, symbol);

-- Accounts: account balances
CREATE TABLE accounts (
    id BIGSERIAL PRIMARY KEY,
    server_env VARCHAR(10) NOT NULL,
    account_id VARCHAR(50) UNIQUE NOT NULL,
    cash_balance DECIMAL(18,2) NOT NULL DEFAULT 0,
    buying_power DECIMAL(18,2),
    total_equity DECIMAL(18,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Strategies: strategy configurations
CREATE TABLE strategies (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    parameters JSONB,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IB API Calls: audit log for compliance
CREATE TABLE ib_api_calls (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    server_env VARCHAR(10) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    request_data JSONB,
    response_status INTEGER,
    response_data JSONB,
    latency_ms INTEGER
);

CREATE INDEX idx_ib_api_timestamp ON ib_api_calls(timestamp DESC);
CREATE INDEX idx_ib_api_endpoint ON ib_api_calls(endpoint);