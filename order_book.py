import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import time
import uuid


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    CANCEL = "CANCEL"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    order_id: str
    client_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())


@dataclass
class Trade:
    trade_id: str
    buy_order_id: str
    sell_order_id: str
    symbol: str
    quantity: int
    price: float
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.trade_id is None:
            self.trade_id = str(uuid.uuid4())


class OrderBook:
    """
    High-performance order book with price-time priority matching.
    Uses heaps for efficient order management and matching.
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        
        # Buy orders: max heap (highest price first)
        self.buy_orders: List[Tuple[float, float, Order]] = []
        
        # Sell orders: min heap (lowest price first)  
        self.sell_orders: List[Tuple[float, float, Order]] = []
        
        # Order lookup by ID for quick access
        self.orders_by_id: Dict[str, Order] = {}
        
        # Client order tracking
        self.client_orders: Dict[str, List[str]] = defaultdict(list)
        
        # Trade history
        self.trades: List[Trade] = []
        
        # Statistics
        self.total_volume = 0
        self.total_trades = 0
    
    def add_order(self, order: Order) -> List[Trade]:
        """Add an order to the book and return any resulting trades."""
        if order.order_type == OrderType.CANCEL:
            return self._cancel_order(order)
        
        # Store order
        self.orders_by_id[order.order_id] = order
        self.client_orders[order.client_id].append(order.order_id)
        
        if order.order_type == OrderType.MARKET:
            return self._process_market_order(order)
        else:  # LIMIT order
            return self._process_limit_order(order)
    
    def _process_market_order(self, order: Order) -> List[Trade]:
        """Process a market order by matching against existing orders."""
        trades = []
        remaining_quantity = order.quantity
        
        if order.side == OrderSide.BUY:
            # Match against sell orders (lowest price first)
            while remaining_quantity > 0 and self.sell_orders:
                best_sell_price, best_sell_time, best_sell_order = self.sell_orders[0]
                
                if best_sell_order.quantity <= remaining_quantity:
                    # Full match
                    trade_quantity = best_sell_order.quantity
                    heapq.heappop(self.sell_orders)
                    del self.orders_by_id[best_sell_order.order_id]
                    
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=order.order_id,
                        sell_order_id=best_sell_order.order_id,
                        symbol=order.symbol,
                        quantity=trade_quantity,
                        price=best_sell_price
                    ))
                    
                    remaining_quantity -= trade_quantity
                else:
                    # Partial match
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=order.order_id,
                        sell_order_id=best_sell_order.order_id,
                        symbol=order.symbol,
                        quantity=remaining_quantity,
                        price=best_sell_price
                    ))
                    
                    best_sell_order.quantity -= remaining_quantity
                    remaining_quantity = 0
        else:  # SELL
            # Match against buy orders (highest price first)
            while remaining_quantity > 0 and self.buy_orders:
                best_buy_price, best_buy_time, best_buy_order = self.buy_orders[0]
                
                if best_buy_order.quantity <= remaining_quantity:
                    # Full match
                    trade_quantity = best_buy_order.quantity
                    heapq.heappop(self.buy_orders)
                    del self.orders_by_id[best_buy_order.order_id]
                    
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=best_buy_order.order_id,
                        sell_order_id=order.order_id,
                        symbol=order.symbol,
                        quantity=trade_quantity,
                        price=best_buy_price
                    ))
                    
                    remaining_quantity -= trade_quantity
                else:
                    # Partial match
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=best_buy_order.order_id,
                        sell_order_id=order.order_id,
                        symbol=order.symbol,
                        quantity=remaining_quantity,
                        price=best_buy_price
                    ))
                    
                    best_buy_order.quantity -= remaining_quantity
                    remaining_quantity = 0
        
        # Update statistics
        for trade in trades:
            self.trades.append(trade)
            self.total_volume += trade.quantity
            self.total_trades += 1
        
        return trades
    
    def _process_limit_order(self, order: Order) -> List[Trade]:
        """Process a limit order by matching and/or adding to book."""
        trades = []
        remaining_quantity = order.quantity
        
        if order.side == OrderSide.BUY:
            # Try to match against existing sell orders
            while (remaining_quantity > 0 and self.sell_orders and 
                   self.sell_orders[0][0] <= order.price):
                
                best_sell_price, best_sell_time, best_sell_order = self.sell_orders[0]
                
                if best_sell_order.quantity <= remaining_quantity:
                    # Full match
                    trade_quantity = best_sell_order.quantity
                    heapq.heappop(self.sell_orders)
                    del self.orders_by_id[best_sell_order.order_id]
                    
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=order.order_id,
                        sell_order_id=best_sell_order.order_id,
                        symbol=order.symbol,
                        quantity=trade_quantity,
                        price=best_sell_price
                    ))
                    
                    remaining_quantity -= trade_quantity
                else:
                    # Partial match
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=order.order_id,
                        sell_order_id=best_sell_order.order_id,
                        symbol=order.symbol,
                        quantity=remaining_quantity,
                        price=best_sell_price
                    ))
                    
                    best_sell_order.quantity -= remaining_quantity
                    remaining_quantity = 0
            
            # Add remaining quantity to buy book
            if remaining_quantity > 0:
                order.quantity = remaining_quantity
                # Use negative price for max heap behavior
                heapq.heappush(self.buy_orders, (-order.price, order.timestamp, order))
        
        else:  # SELL
            # Try to match against existing buy orders
            while (remaining_quantity > 0 and self.buy_orders and 
                   -self.buy_orders[0][0] >= order.price):
                
                best_buy_price, best_buy_time, best_buy_order = self.buy_orders[0]
                best_buy_price = -best_buy_price  # Convert back from negative
                
                if best_buy_order.quantity <= remaining_quantity:
                    # Full match
                    trade_quantity = best_buy_order.quantity
                    heapq.heappop(self.buy_orders)
                    del self.orders_by_id[best_buy_order.order_id]
                    
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=best_buy_order.order_id,
                        sell_order_id=order.order_id,
                        symbol=order.symbol,
                        quantity=trade_quantity,
                        price=best_buy_price
                    ))
                    
                    remaining_quantity -= trade_quantity
                else:
                    # Partial match
                    trades.append(Trade(
                        trade_id=None,  # Will be auto-generated
                        buy_order_id=best_buy_order.order_id,
                        sell_order_id=order.order_id,
                        symbol=order.symbol,
                        quantity=remaining_quantity,
                        price=best_buy_price
                    ))
                    
                    best_buy_order.quantity -= remaining_quantity
                    remaining_quantity = 0
            
            # Add remaining quantity to sell book
            if remaining_quantity > 0:
                order.quantity = remaining_quantity
                heapq.heappush(self.sell_orders, (order.price, order.timestamp, order))
        
        # Update statistics
        for trade in trades:
            self.trades.append(trade)
            self.total_volume += trade.quantity
            self.total_trades += 1
        
        return trades
    
    def _cancel_order(self, cancel_order: Order) -> List[Trade]:
        """Cancel an existing order."""
        # Extract the order ID from the cancel order
        # Assuming cancel_order.order_id contains the ID of the order to cancel
        order_to_cancel = self.orders_by_id.get(cancel_order.order_id)
        
        if not order_to_cancel:
            return []  # Order not found
        
        # Remove from appropriate heap
        if order_to_cancel.side == OrderSide.BUY:
            # Find and remove from buy orders
            for i, (price, timestamp, order) in enumerate(self.buy_orders):
                if order.order_id == cancel_order.order_id:
                    self.buy_orders.pop(i)
                    heapq.heapify(self.buy_orders)  # Re-heapify
                    break
        else:
            # Find and remove from sell orders
            for i, (price, timestamp, order) in enumerate(self.sell_orders):
                if order.order_id == cancel_order.order_id:
                    self.sell_orders.pop(i)
                    heapq.heapify(self.sell_orders)  # Re-heapify
                    break
        
        # Remove from tracking
        del self.orders_by_id[order_to_cancel.order_id]
        
        return []
    
    def get_best_bid(self) -> Optional[Tuple[float, int]]:
        """Get best bid (highest buy price and quantity)."""
        if not self.buy_orders:
            return None
        price, timestamp, order = self.buy_orders[0]
        return (-price, order.quantity)  # Convert back from negative
    
    def get_best_ask(self) -> Optional[Tuple[float, int]]:
        """Get best ask (lowest sell price and quantity)."""
        if not self.sell_orders:
            return None
        price, timestamp, order = self.sell_orders[0]
        return (price, order.quantity)
    
    def get_order_book_snapshot(self, depth: int = 10) -> Dict:
        """Get a snapshot of the order book up to specified depth."""
        buy_levels = []
        sell_levels = []
        
        # Get buy levels (highest price first)
        for i, (price, timestamp, order) in enumerate(self.buy_orders[:depth]):
            buy_levels.append({
                'price': -price,  # Convert back from negative
                'quantity': order.quantity,
                'order_id': order.order_id
            })
        
        # Get sell levels (lowest price first)
        for i, (price, timestamp, order) in enumerate(self.sell_orders[:depth]):
            sell_levels.append({
                'price': price,
                'quantity': order.quantity,
                'order_id': order.order_id
            })
        
        return {
            'symbol': self.symbol,
            'timestamp': time.time(),
            'buy_levels': buy_levels,
            'sell_levels': sell_levels,
            'best_bid': self.get_best_bid(),
            'best_ask': self.get_best_ask(),
            'total_volume': self.total_volume,
            'total_trades': self.total_trades
        }
    
    def get_statistics(self) -> Dict:
        """Get order book statistics."""
        return {
            'symbol': self.symbol,
            'total_orders': len(self.orders_by_id),
            'buy_orders': len(self.buy_orders),
            'sell_orders': len(self.sell_orders),
            'total_volume': self.total_volume,
            'total_trades': self.total_trades,
            'best_bid': self.get_best_bid(),
            'best_ask': self.get_best_ask()
        } 