from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import time
import threading
from typing import Dict, Any
import logging

# Import our order book components
from order_book import OrderBook, Order, OrderType, OrderSide
from udp_server import UDPOrderServer

app = Flask(__name__)
app.config['SECRET_KEY'] = 'hft-order-book-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global server instance
udp_server = None
server_thread = None

# Statistics tracking
dashboard_stats = {
    'start_time': time.time(),
    'total_orders': 0,
    'total_trades': 0,
    'total_volume': 0,
    'peak_throughput': 0
}

def start_udp_server():
    """Start the UDP server in a separate thread."""
    global udp_server
    udp_server = UDPOrderServer(host='localhost', port=8888)
    udp_server.start()

def get_order_book_snapshots() -> Dict[str, Any]:
    """Get snapshots of all order books."""
    if not udp_server:
        return {}
    
    snapshots = {}
    for symbol, order_book in udp_server.order_processor.order_books.items():
        snapshots[symbol] = order_book.get_order_book_snapshot(depth=10)
    
    return snapshots

def get_server_statistics() -> Dict[str, Any]:
    """Get comprehensive server statistics."""
    if not udp_server:
        return dashboard_stats
    
    stats = udp_server.get_statistics()
    
    # Calculate current throughput
    current_time = time.time()
    elapsed = current_time - dashboard_stats['start_time']
    current_throughput = stats['total_orders_processed'] / elapsed if elapsed > 0 else 0
    
    # Update peak throughput
    if current_throughput > dashboard_stats['peak_throughput']:
        dashboard_stats['peak_throughput'] = current_throughput
    
    return {
        'uptime_seconds': elapsed,
        'total_orders_processed': stats['total_orders_processed'],
        'current_throughput': current_throughput,
        'peak_throughput': dashboard_stats['peak_throughput'],
        'order_books': stats['order_books'],
        'total_trades': sum(ob.get('total_trades', 0) for ob in stats['order_books'].values()),
        'total_volume': sum(ob.get('total_volume', 0) for ob in stats['order_books'].values())
    }

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')

@app.route('/api/statistics')
def api_statistics():
    """Get server statistics."""
    return jsonify(get_server_statistics())

@app.route('/api/orderbook/<symbol>')
def api_orderbook(symbol):
    """Get order book for a specific symbol."""
    if not udp_server or symbol not in udp_server.order_processor.order_books:
        return jsonify({'error': 'Symbol not found'}), 404
    
    order_book = udp_server.order_processor.order_books[symbol]
    return jsonify(order_book.get_order_book_snapshot(depth=20))

@app.route('/api/orderbook')
def api_all_orderbooks():
    """Get all order books."""
    return jsonify(get_order_book_snapshots())

@app.route('/api/orders', methods=['POST'])
def api_submit_order():
    """Submit an order via REST API."""
    try:
        order_data = request.json
        
        # Validate required fields
        required_fields = ['client_id', 'symbol', 'side', 'order_type', 'quantity']
        for field in required_fields:
            if field not in order_data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create order object
        order = Order(
            order_id=order_data.get('order_id'),
            client_id=order_data['client_id'],
            symbol=order_data['symbol'],
            side=OrderSide(order_data['side'].upper()),
            order_type=OrderType(order_data['order_type'].upper()),
            quantity=int(order_data['quantity']),
            price=float(order_data['price']) if order_data.get('price') else None
        )
        
        # Process the order
        if udp_server:
            success, message, trades = udp_server.order_processor.process_order(order)
            
            # Emit real-time updates
            socketio.emit('order_update', {
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
            })
            
            # Emit order book updates
            socketio.emit('orderbook_update', get_order_book_snapshots())
            
            return jsonify({
                'order_id': order.order_id,
                'success': success,
                'message': message,
                'trades': len(trades)
            })
        else:
            return jsonify({'error': 'Server not running'}), 503
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/symbols')
def api_symbols():
    """Get list of available symbols."""
    if not udp_server:
        return jsonify([])
    
    return jsonify(list(udp_server.order_processor.order_books.keys()))

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to HFT Order Book Dashboard'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f"Client disconnected: {request.sid}")

@socketio.on('request_statistics')
def handle_request_statistics():
    """Send statistics to client."""
    emit('statistics_update', get_server_statistics())

@socketio.on('request_orderbook')
def handle_request_orderbook():
    """Send order book data to client."""
    emit('orderbook_update', get_order_book_snapshots())

def broadcast_updates():
    """Background thread to broadcast updates."""
    while True:
        try:
            if udp_server:
                # Broadcast statistics
                socketio.emit('statistics_update', get_server_statistics())
                
                # Broadcast order book updates
                socketio.emit('orderbook_update', get_order_book_snapshots())
            
            time.sleep(1)  # Update every second
        except Exception as e:
            print(f"Error in broadcast thread: {e}")

if __name__ == '__main__':
    # Start UDP server in background
    print("🚀 Starting UDP Order Server...")
    server_thread = threading.Thread(target=start_udp_server, daemon=True)
    server_thread.start()
    
    # Wait a moment for server to start
    time.sleep(2)
    
    # Start broadcast thread
    broadcast_thread = threading.Thread(target=broadcast_updates, daemon=True)
    broadcast_thread.start()
    
    print("🌐 Starting Web Dashboard...")
    print("📊 Dashboard available at: http://localhost:5000")
    print("📡 UDP Server running on: localhost:8888")
    
    # Start Flask app
    socketio.run(app, host='0.0.0.0', port=5000, debug=True) 