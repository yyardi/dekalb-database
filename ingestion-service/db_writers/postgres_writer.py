import asyncpg
import logging


class PostgresWriter:
    def __init__(self, config):
        self.config = config
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=self.config.DB_HOST,
            port=self.config.POSTGRES_PORT,
            database=self.config.POSTGRES_DB,
            user=self.config.POSTGRES_USER,
            password=self.config.POSTGRES_PASSWORD
        )

    async def update_order(self, event):
        """Insert or update order (UPSERT)"""
        try:
            data = event['data']
            order_id = data['order_id']
            status = data.get('status', 'UNKNOWN')
            filled_quantity = data.get('filled_quantity', 0)
            avg_fill_price = data.get('avg_fill_price')
            commission = data.get('commission')
            
            # UPSERT: Insert if new, update if exists
            sql = """
                INSERT INTO orders (
                    order_id, 
                    server_env, 
                    symbol, 
                    side, 
                    quantity, 
                    status, 
                    order_type,
                    limit_price,
                    submitted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
                ON CONFLICT (order_id) 
                DO UPDATE SET 
                    status = $6,
                    filled_quantity = $9,
                    avg_fill_price = $10,
                    commission = $11,
                    updated_at = now()
            """
            
            await self.pool.execute(
                sql,
                order_id,
                event.get('server_env', 'paper'),
                data.get('symbol'),
                data.get('side'),
                data.get('quantity'),
                status,
                data.get('order_type'),
                data.get('limit_price'),
                filled_quantity,
                avg_fill_price,
                commission
            )
            
            logging.info(f"Updated order {order_id} to status {status}")
            return True
        except Exception as e:
            logging.error(f"Error updating order: {e}")
            return False

    async def update_position(self, event):
        try:
            data = event['data']
            symbol = data['symbol']
            side = data['side']
            quantity = data['quantity']
            price = data['price']
            server_env = event['server_env']
            account_id = data.get('account_id', 'PAPER_ACCOUNT')

            # BUY: positive quantity, SELL: negative quantity
            if side == 'SELL':
                quantity = -quantity

            sql = """
                INSERT INTO positions (server_env, account_id, symbol, quantity, updated_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (server_env, account_id, symbol)
                DO UPDATE SET
                    quantity = positions.quantity + $4,
                    updated_at = now()
            """

            await self.pool.execute(
                sql,
                server_env,
                account_id,
                symbol,
                quantity
            )
            logging.info(f"Updated position for {symbol} ({side} {abs(quantity)})")
            return True
        except Exception as e:
            logging.error(f"Error updating position: {e}")
            return False

    async def close(self):
        await self.pool.close()
