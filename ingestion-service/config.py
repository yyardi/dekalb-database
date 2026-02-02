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
