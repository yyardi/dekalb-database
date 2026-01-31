from questdb.ingress import Sender, IngressError
from datetime import datetime
import logging


class QuestDBWriter:
    def __init__(self, config):
        self.config = config
        self.sender = None

    def connect(self):
        self.sender = Sender(
            host=self.config.QUESTDB_ILP_HOST,
            port=self.config.QUESTDB_ILP_PORT
        )

    def insert_execution(self, event):
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            timestamp_ns = int(dt.timestamp() * 1_000_000_000)

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
            logging.info(f"Inserted execution for order {event['data']['order_id']}")
            return True
        except Exception as e:
            logging.error(f"Error inserting execution: {e}")
            return False

    def insert_log(self, event):
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            timestamp_ns = int(dt.timestamp() * 1_000_000_000)

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
            logging.info("Inserted engine log")
            return True
        except Exception as e:
            logging.error(f"Error inserting log: {e}")
            return False

    def insert_signal(self, event):
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            timestamp_ns = int(dt.timestamp() * 1_000_000_000)

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
            logging.info(f"Inserted signal for {event['data']['symbol']}")
            return True
        except Exception as e:
            logging.error(f"Error inserting signal: {e}")
            return False

    def close(self):
        self.sender.close()
