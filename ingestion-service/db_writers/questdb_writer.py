from questdb.ingress import Sender, TimestampNanos
from datetime import datetime
import logging

class QuestDBWriter:
    def __init__(self, config):
        self.config = config
        self.conf = f'tcp::addr={config.QUESTDB_ILP_HOST}:{config.QUESTDB_ILP_PORT};'
    
    def insert_execution(self, event):
        """Insert execution"""
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            
            with Sender.from_conf(self.conf) as sender:
                sender.row(
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
                        'quantity': float(event['data']['quantity']),
                        'price': float(event['data']['price']),
                        'commission': float(event['data'].get('commission', 0.0))
                    },
                    at=dt  # Just pass the datetime object directly
                )
            
            logging.info(f"Inserted execution for order {event['data']['order_id']}")
            return True
        except Exception as e:
            logging.error(f"Failed to insert execution: {e}")
            return False
    
    def insert_log(self, event):
        """Insert log"""
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            
            with Sender.from_conf(self.conf) as sender:
                sender.row(
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
                    at=dt  # Just pass the datetime object
                )
            
            logging.debug("Inserted log event")
            return True
        except Exception as e:
            logging.error(f"Failed to insert log: {e}")
            return False
    
    def insert_signal(self, event):
        """Insert signal"""
        try:
            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            
            with Sender.from_conf(self.conf) as sender:
                sender.row(
                    'strategy_signals',
                    symbols={
                        'server_env': event['server_env'],
                        'strategy': event['data']['strategy'],
                        'symbol': event['data']['symbol'],
                        'signal_type': event['data']['signal_type']
                    },
                    columns={
                        'confidence': float(event['data'].get('confidence', 0.0)),
                        'reason': event['data'].get('reason', ''),
                        'features': event['data'].get('features', '')
                    },
                    at=dt  # Just pass the datetime object
                )
            
            logging.info(f"Inserted signal for {event['data']['symbol']}")
            return True
        except Exception as e:
            logging.error(f"Failed to insert signal: {e}")
            return False