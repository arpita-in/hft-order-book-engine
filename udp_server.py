import json
import socket
import threading
import time
from queue import Queue, Empty
from typing import Dict, Optional, Tuple
import logging

from order_book import Order, OrderType, OrderSide, OrderBook


class OrderProcessor:
    """Handles order processing and matching engine logic."""
    
    def __init__(self):
        self.order_books: Dict[str, OrderBook] = {}
        self.lock = threading.Lock()
        
        # Statistics
        self.total_orders_processed = 0
        self.start_time = time.time()
        self.last_throughput_log = time.time()
    
    def get_or_create_order_book(self, symbol: str) -> OrderBook:
        """Get existing order book or create new one for symbol."""
        with self.lock:
            if symbol not in self.order_books:
                self.order_books[symbol] = OrderBook(symbol)
            return self.order_books[symbol]
    
    def process_order(self, order: Order) -> Tuple[bool, str, list]:
        """
        Process an order and return (success, message, trades).
        
        Returns:
            - success: bool indicating if order was accepted
            - message: description of what happened
            - trades: list of trades that occurred
        """
        try:
            order_book = self.get_or_create_order_book(order.symbol)
            trades = order_book.add_order(order)
            
            self.total_orders_processed += 1
            
            # Log throughput every second
            current_time = time.time()
            if current_time - self.last_throughput_log >= 1.0:
                elapsed = current_time - self.start_time
                throughput = self.total_orders_processed / elapsed
                print(f"📊 Throughput: {throughput:.2f} orders/sec | "
                      f"Total: {self.total_orders_processed} orders")
                self.last_throughput_log = current_time
            
            if trades:
                return True, f"Order executed with {len(trades)} trades", trades
            else:
                return True, "Order accepted", []
                
        except Exception as e:
            logging.error(f"Error processing order: {e}")
            return False, f"Error: {str(e)}", []


class UDPOrderServer:
    """
    Multithreaded UDP server for order processing.
    
    Architecture:
    - Main thread: UDP socket listener
    - Processing thread: Order matching engine
    - Response thread: Send acknowledgments back to clients
    """
    
    def __init__(self, host: str = 'localhost', port: int = 8888):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        
        # Threading components
        self.order_processor = OrderProcessor()
        self.order_queue = Queue()  # Orders from network to processor
        self.response_queue = Queue()  # Responses from processor to network
        
        # Threads
        self.processing_thread = None
        self.response_thread = None
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    def start(self):
        """Start the UDP server and all worker threads."""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.host, self.port))
            self.socket.settimeout(1.0)  # 1 second timeout for graceful shutdown
            
            self.running = True
            
            # Start worker threads
            self.processing_thread = threading.Thread(target=self._processing_worker)
            self.response_thread = threading.Thread(target=self._response_worker)
            
            self.processing_thread.start()
            self.response_thread.start()
            
            logging.info(f"🚀 UDP Order Server started on {self.host}:{self.port}")
            logging.info("📊 Processing threads started")
            
            # Main network loop
            self._network_loop()
            
        except Exception as e:
            logging.error(f"Failed to start server: {e}")
            self.stop()
    
    def stop(self):
        """Stop the server and all threads."""
        logging.info("🛑 Shutting down UDP Order Server...")
        self.running = False
        
        if self.socket:
            self.socket.close()
        
        # Wait for threads to finish
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
        
        if self.response_thread and self.response_thread.is_alive():
            self.response_thread.join(timeout=5)
        
        logging.info("✅ Server shutdown complete")
    
    def _network_loop(self):
        """Main network loop - receives orders from clients."""
        logging.info("📡 Listening for orders...")
        
        while self.running:
            try:
                data, client_address = self.socket.recvfrom(4096)
                
                # Parse order from JSON
                try:
                    order_data = json.loads(data.decode('utf-8'))
                    order = self._parse_order(order_data)
                    
                    # Add to processing queue with client info
                    self.order_queue.put((order, client_address))
                    
                except json.JSONDecodeError as e:
                    logging.error(f"Invalid JSON from {client_address}: {e}")
                    self._send_error_response(client_address, "Invalid JSON format")
                
                except Exception as e:
                    logging.error(f"Error parsing order from {client_address}: {e}")
                    self._send_error_response(client_address, f"Parse error: {str(e)}")
            
            except socket.timeout:
                # Timeout is expected for graceful shutdown
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"Network error: {e}")
    
    def _processing_worker(self):
        """Worker thread that processes orders from the queue."""
        logging.info("⚙️ Processing worker started")
        
        while self.running:
            try:
                # Get order from queue (with timeout for graceful shutdown)
                order, client_address = self.order_queue.get(timeout=1.0)
                
                # Process the order
                success, message, trades = self.order_processor.process_order(order)
                
                # Create response
                response = {
                    'order_id': order.order_id,
                    'success': success,
                    'message': message,
                    'trades': [
                        {
                            'trade_id': trade.trade_id,
                            'quantity': trade.quantity,
                            'price': trade.price,
                            'timestamp': trade.timestamp
                        } for trade in trades
                    ],
                    'timestamp': time.time()
                }
                
                # Send to response queue
                self.response_queue.put((response, client_address))
                
            except Empty:
                # Timeout - continue loop
                continue
            except Exception as e:
                logging.error(f"Processing error: {e}")
    
    def _response_worker(self):
        """Worker thread that sends responses back to clients."""
        logging.info("📤 Response worker started")
        
        while self.running:
            try:
                # Get response from queue (with timeout for graceful shutdown)
                response, client_address = self.response_queue.get(timeout=1.0)
                
                # Send response back to client
                try:
                    response_data = json.dumps(response).encode('utf-8')
                    self.socket.sendto(response_data, client_address)
                    
                except Exception as e:
                    logging.error(f"Failed to send response to {client_address}: {e}")
                
            except Empty:
                # Timeout - continue loop
                continue
            except Exception as e:
                logging.error(f"Response error: {e}")
    
    def _parse_order(self, order_data: dict) -> Order:
        """Parse order from JSON data."""
        # Validate required fields
        required_fields = ['client_id', 'symbol', 'side', 'order_type', 'quantity']
        for field in required_fields:
            if field not in order_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Parse enums
        try:
            side = OrderSide(order_data['side'].upper())
            order_type = OrderType(order_data['order_type'].upper())
        except ValueError as e:
            raise ValueError(f"Invalid enum value: {e}")
        
        # Create order
        order = Order(
            order_id=order_data.get('order_id'),
            client_id=order_data['client_id'],
            symbol=order_data['symbol'],
            side=side,
            order_type=order_type,
            quantity=int(order_data['quantity']),
            price=float(order_data['price']) if order_data.get('price') else None
        )
        
        return order
    
    def _send_error_response(self, client_address: Tuple[str, int], error_message: str):
        """Send error response to client."""
        try:
            error_response = {
                'success': False,
                'message': error_message,
                'timestamp': time.time()
            }
            response_data = json.dumps(error_response).encode('utf-8')
            self.socket.sendto(response_data, client_address)
        except Exception as e:
            logging.error(f"Failed to send error response: {e}")
    
    def get_statistics(self) -> dict:
        """Get server statistics."""
        stats = {
            'total_orders_processed': self.order_processor.total_orders_processed,
            'uptime_seconds': time.time() - self.order_processor.start_time,
            'order_books': {}
        }
        
        # Add order book statistics
        for symbol, order_book in self.order_processor.order_books.items():
            stats['order_books'][symbol] = order_book.get_statistics()
        
        return stats


if __name__ == "__main__":
    # Start the server
    server = UDPOrderServer()
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n🛑 Received interrupt signal")
        server.stop() 