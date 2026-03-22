#!/bin/bash
# Creates the equities team's isolated database and applies the trade tracker schema.
#
# Why a shell script instead of a plain .sql file:
#   PostgreSQL's docker-entrypoint-initdb.d runs all .sql files against the
#   default database (POSTGRES_DB = "trading"). To create a second database
#   and run a schema against it we need a shell script that can switch databases.
#
# Execution order (alphabetical in initdb.d):
#   01_trading.sql  → quant team tables in "trading" DB  (auto-run by PG)
#   02_equities.sh  → creates "trade_tracker" DB + runs equities schema (this file)

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE trade_tracker;
EOSQL

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname   "trade_tracker" \
     --file     /etc/schemas/trade_tracker_schema.sql

echo "trade_tracker database initialized for equities team."
