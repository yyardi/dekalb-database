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
