import zmq
import json
import time
from datetime import datetime, timedelta

def create_comprehensive_batch(batch_num):
    """Create a batch with ALL event types"""
    now = datetime.utcnow()
    
    events = [
        # Event 1: Order update (new order submitted)
        {
            'type': 'order_update',
            'timestamp': now.isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'order_id': f'ORD{batch_num:05d}',
                'symbol': 'TSLA',
                'side': 'BUY',
                'quantity': 50,
                'status': 'SUBMITTED',
                'order_type': 'LIMIT',
                'limit_price': 245.50
            }
        },
        
        # Event 2: Execution (order filled)
        {
            'type': 'execution',
            'timestamp': (now + timedelta(seconds=1)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'order_id': f'ORD{batch_num:05d}',
                'ib_execution_id': f'EXEC{batch_num:08d}',
                'symbol': 'TSLA',
                'side': 'BUY',
                'quantity': 50,
                'price': 245.50,
                'commission': 0.50,
                'strategy': 'momentum_scalper'
            }
        },
        
        # Event 3: Strategy signal
        {
            'type': 'signal',
            'timestamp': (now + timedelta(seconds=2)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'strategy': 'momentum_scalper',
                'symbol': 'TSLA',
                'signal_type': 'BUY',
                'confidence': 0.85,
                'reason': 'Strong momentum + volume breakout',
                'features': '{"rsi": 72.3, "volume_ratio": 2.4, "price_momentum": 0.03}'
            }
        },
        
        # Event 4: Engine log (info)
        {
            'type': 'log',
            'timestamp': (now + timedelta(seconds=3)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'log_level': 'INFO',
                'component': 'momentum_scalper',
                'message': f'Executed trade: TSLA BUY 50 @ $245.50',
                'data': '{"order_id": "' + f'ORD{batch_num:05d}' + '"}'
            }
        },
        
        # Event 5: Engine log (debug)
        {
            'type': 'log',
            'timestamp': (now + timedelta(seconds=4)).isoformat() + 'Z',
            'server_env': 'paper',
            'data': {
                'log_level': 'DEBUG',
                'component': 'risk_manager',
                'message': 'Position check passed',
                'data': '{"max_position": 1000, "current": 50}'
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
    print("🚀 Connected to ingestion service on port 5555\n")
    
    # Send 3 batches with different stocks
    stocks = ['TSLA', 'NVDA', 'MSFT']
    
    for i, stock in enumerate(stocks, start=1):
        batch = create_comprehensive_batch(i)
        
        # Change the symbol in events
        for event in batch['events']:
            if 'symbol' in event['data']:
                event['data']['symbol'] = stock
        
        socket.send_json(batch)
        print(f"Sent batch {i}: {stock}")
        print(f"   - Order update")
        print(f"   - Execution")
        print(f"   - Strategy signal")
        print(f"   - 2 log entries\n")
        time.sleep(2)
    
    print("All comprehensive test batches sent!\n")
    print("Check your databases:")
    print("   PostgreSQL: http://localhost:8080")
    print("   - orders table: 3 new orders")
    print("   - positions table: TSLA, NVDA, MSFT positions")
    print("\n   QuestDB: http://localhost:9000")
    print("   - executions: 3 trades")
    print("   - strategy_signals: 3 signals")
    print("   - engine_logs: 6 log entries")
    
    socket.close()
    context.term()

if __name__ == '__main__':
    main()