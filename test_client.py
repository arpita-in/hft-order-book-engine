import json
import random
import socket
import time
import threading
from typing import Dict, List
import argparse


class OrderClient:
    """Test client for sending orders to the UDP order server."""
    
    def __init__(self, server_host: str = 'localhost', server_port: int = 8888):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(5.0)
        
        # Statistics
        self.orders_sent = 0
        self.responses_received = 0
        self.start_time = time.time()
        
        # Response tracking
        self.responses: List[Dict] = []
        self.response_lock = threading.Lock()
        
        # Start response listener thread
        self.running = True
        self.response_thread = threading.Thread(target=self._listen_for_responses)
        self.response_thread.daemon = True
        self.response_thread.start()
    
    def _listen_for_responses(self):
        """Listen for responses from the server."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                response = json.loads(data.decode('utf-8'))
                
                with self.response_lock:
                    self.responses.append(response)
                    self.responses_received += 1
                
                # Print trade notifications
                if response.get('trades'):
                    for trade in response['trades']:
                        print(f"💰 Trade: {trade['quantity']} @ ${trade['price']:.2f}")
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error receiving response: {e}")
    
    def send_order(self, order_data: Dict) -> bool:
        """Send an order to the server."""
        try:
            order_json = json.dumps(order_data).encode('utf-8')
            self.socket.sendto(order_json, (self.server_host, self.server_port))
            self.orders_sent += 1
            return True
        except Exception as e:
            print(f"Error sending order: {e}")
            return False
    
    def send_limit_order(self, client_id: str, symbol: str, side: str, 
                        quantity: int, price: float) -> bool:
        """Send a limit order."""
        order = {
            'client_id': client_id,
            'symbol': symbol,
            'side': side.upper(),
            'order_type': 'LIMIT',
            'quantity': quantity,
            'price': price
        }
        return self.send_order(order)
    
    def send_market_order(self, client_id: str, symbol: str, side: str, 
                         quantity: int) -> bool:
        """Send a market order."""
        order = {
            'client_id': client_id,
            'symbol': symbol,
            'side': side.upper(),
            'order_type': 'MARKET',
            'quantity': quantity
        }
        return self.send_order(order)
    
    def send_cancel_order(self, client_id: str, order_id: str) -> bool:
        """Send a cancel order."""
        order = {
            'client_id': client_id,
            'order_id': order_id,
            'symbol': 'AAPL',  # Default symbol for cancel
            'side': 'BUY',     # Default side for cancel
            'order_type': 'CANCEL',
            'quantity': 0
        }
        return self.send_order(order)
    
    def run_performance_test(self, duration: int = 30, orders_per_second: int = 100):
        """Run a performance test for specified duration."""
        print(f"🚀 Starting performance test: {orders_per_second} orders/sec for {duration} seconds")
        
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN']
        sides = ['BUY', 'SELL']
        order_types = ['LIMIT', 'MARKET']
        
        start_time = time.time()
        order_count = 0
        
        while time.time() - start_time < duration:
            # Calculate target orders for this second
            elapsed = time.time() - start_time
            target_orders = int(elapsed * orders_per_second)
            
            # Send orders to catch up to target
            while order_count < target_orders:
                symbol = random.choice(symbols)
                side = random.choice(sides)
                order_type = random.choice(order_types)
                client_id = f"client_{random.randint(1, 10)}"
                
                if order_type == 'LIMIT':
                    price = round(random.uniform(100, 200), 2)
                    quantity = random.randint(1, 100)
                    self.send_limit_order(client_id, symbol, side, quantity, price)
                else:  # MARKET
                    quantity = random.randint(1, 100)
                    self.send_market_order(client_id, symbol, side, quantity)
                
                order_count += 1
            
            # Small sleep to prevent overwhelming
            time.sleep(0.01)
        
        # Print final statistics
        self.print_statistics()
    
    def run_scenario_test(self):
        """Run a scenario test with specific order sequences."""
        print("🎭 Running scenario test...")
        
        # Scenario 1: Basic limit orders
        print("📝 Scenario 1: Basic limit orders")
        self.send_limit_order("client1", "AAPL", "BUY", 100, 150.00)
        time.sleep(0.1)
        self.send_limit_order("client2", "AAPL", "SELL", 50, 150.00)
        time.sleep(0.1)
        
        # Scenario 2: Market order matching
        print("📝 Scenario 2: Market order matching")
        self.send_market_order("client3", "AAPL", "BUY", 25)
        time.sleep(0.1)
        
        # Scenario 3: Multiple orders at same price
        print("📝 Scenario 3: Multiple orders at same price")
        self.send_limit_order("client4", "AAPL", "BUY", 75, 151.00)
        time.sleep(0.1)
        self.send_limit_order("client5", "AAPL", "BUY", 50, 151.00)
        time.sleep(0.1)
        self.send_limit_order("client6", "AAPL", "SELL", 100, 151.00)
        time.sleep(0.1)
        
        # Scenario 4: Cross-symbol orders
        print("📝 Scenario 4: Cross-symbol orders")
        self.send_limit_order("client7", "GOOGL", "BUY", 200, 2500.00)
        time.sleep(0.1)
        self.send_limit_order("client8", "GOOGL", "SELL", 100, 2500.00)
        time.sleep(0.1)
        
        print("✅ Scenario test completed")
        time.sleep(2)  # Wait for responses
        self.print_statistics()
    
    def print_statistics(self):
        """Print client statistics."""
        elapsed = time.time() - self.start_time
        throughput = self.orders_sent / elapsed if elapsed > 0 else 0
        
        print(f"\n📊 Client Statistics:")
        print(f"   Orders sent: {self.orders_sent}")
        print(f"   Responses received: {self.responses_received}")
        print(f"   Throughput: {throughput:.2f} orders/sec")
        print(f"   Response rate: {(self.responses_received/self.orders_sent*100):.1f}%" if self.orders_sent > 0 else "   Response rate: 0%")
        
        # Show recent responses
        with self.response_lock:
            if self.responses:
                print(f"\n📨 Recent responses:")
                for response in self.responses[-5:]:  # Last 5 responses
                    status = "✅" if response.get('success') else "❌"
                    print(f"   {status} {response.get('message', 'No message')}")
    
    def close(self):
        """Close the client."""
        self.running = False
        self.socket.close()


def main():
    parser = argparse.ArgumentParser(description='UDP Order Client')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=8888, help='Server port')
    parser.add_argument('--test', choices=['performance', 'scenario'], 
                       default='scenario', help='Test type')
    parser.add_argument('--duration', type=int, default=30, 
                       help='Performance test duration (seconds)')
    parser.add_argument('--rate', type=int, default=100, 
                       help='Orders per second for performance test')
    
    args = parser.parse_args()
    
    client = OrderClient(args.host, args.port)
    
    try:
        if args.test == 'performance':
            client.run_performance_test(args.duration, args.rate)
        else:
            client.run_scenario_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
    finally:
        client.close()


if __name__ == "__main__":
    main() 