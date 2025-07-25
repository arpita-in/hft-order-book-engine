#!/usr/bin/env python3
"""
HFT Order Book Performance Testing Suite
Comprehensive benchmarking system for measuring system performance under various loads.
"""

import argparse
import json
import random
import socket
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict, deque
import csv
import os
from datetime import datetime


@dataclass
class TestResult:
    """Individual test result data."""
    test_id: str
    client_id: str
    order_id: str
    send_time: float
    receive_time: Optional[float] = None
    latency_ms: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    trade_count: int = 0


@dataclass
class TestScenario:
    """Test scenario configuration."""
    name: str
    duration: int
    orders_per_second: int
    num_clients: int
    symbols: List[str]
    order_types: List[str]
    price_range: Tuple[float, float]
    quantity_range: Tuple[int, int]
    description: str = ""


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics."""
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    total_trades: int = 0
    total_volume: int = 0
    
    # Latency metrics
    latencies: List[float] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    
    # Throughput metrics
    actual_throughput: float = 0.0
    target_throughput: float = 0.0
    throughput_efficiency: float = 0.0
    
    # Error metrics
    error_rate: float = 0.0
    error_types: Dict[str, int] = field(default_factory=dict)
    
    # Time series data
    throughput_timeline: List[Tuple[float, float]] = field(default_factory=list)
    latency_timeline: List[Tuple[float, float]] = field(default_factory=list)


class PerformanceClient:
    """Client for sending orders and measuring performance."""
    
    def __init__(self, client_id: str, server_host: str = 'localhost', server_port: int = 8888):
        self.client_id = client_id
        self.server_host = server_host
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(5.0)
        
        # Response tracking
        self.responses: Dict[str, TestResult] = {}
        self.response_lock = threading.Lock()
        
        # Start response listener
        self.running = True
        self.response_thread = threading.Thread(target=self._listen_for_responses, daemon=True)
        self.response_thread.start()
    
    def _listen_for_responses(self):
        """Listen for responses from the server."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                response = json.loads(data.decode('utf-8'))
                
                with self.response_lock:
                    if response.get('order_id') in self.responses:
                        result = self.responses[response['order_id']]
                        result.receive_time = time.time()
                        result.latency_ms = (result.receive_time - result.send_time) * 1000
                        result.success = response.get('success', False)
                        result.trade_count = len(response.get('trades', []))
                        
                        if not result.success:
                            result.error_message = response.get('message', 'Unknown error')
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving response: {e}")
    
    def send_order(self, order_data: Dict) -> TestResult:
        """Send an order and return test result."""
        order_id = order_data.get('order_id', f"test_{int(time.time() * 1000000)}")
        
        # Create test result
        result = TestResult(
            test_id=f"test_{int(time.time())}",
            client_id=self.client_id,
            order_id=order_id,
            send_time=time.time()
        )
        
        # Store result for response tracking
        with self.response_lock:
            self.responses[order_id] = result
        
        # Send order
        try:
            order_json = json.dumps(order_data).encode('utf-8')
            self.socket.sendto(order_json, (self.server_host, self.server_port))
            return result
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            return result
    
    def close(self):
        """Close the client."""
        self.running = False
        self.socket.close()


class PerformanceTestSuite:
    """Comprehensive performance testing suite."""
    
    def __init__(self, server_host: str = 'localhost', server_port: int = 8888):
        self.server_host = server_host
        self.server_port = server_port
        self.results: List[TestResult] = []
        self.metrics = PerformanceMetrics()
        
        # Predefined test scenarios
        self.scenarios = {
            'smoke_test': TestScenario(
                name="Smoke Test",
                duration=10,
                orders_per_second=10,
                num_clients=1,
                symbols=['AAPL'],
                order_types=['LIMIT'],
                price_range=(100, 200),
                quantity_range=(1, 100),
                description="Basic functionality test"
            ),
            'low_load': TestScenario(
                name="Low Load Test",
                duration=30,
                orders_per_second=100,
                num_clients=2,
                symbols=['AAPL', 'GOOGL'],
                order_types=['LIMIT', 'MARKET'],
                price_range=(100, 200),
                quantity_range=(1, 100),
                description="Low load performance test"
            ),
            'medium_load': TestScenario(
                name="Medium Load Test",
                duration=60,
                orders_per_second=500,
                num_clients=5,
                symbols=['AAPL', 'GOOGL', 'MSFT', 'TSLA'],
                order_types=['LIMIT', 'MARKET'],
                price_range=(100, 200),
                quantity_range=(1, 100),
                description="Medium load performance test"
            ),
            'high_load': TestScenario(
                name="High Load Test",
                duration=120,
                orders_per_second=1000,
                num_clients=10,
                symbols=['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
                order_types=['LIMIT', 'MARKET'],
                price_range=(100, 200),
                quantity_range=(1, 100),
                description="High load performance test"
            ),
            'stress_test': TestScenario(
                name="Stress Test",
                duration=180,
                orders_per_second=2000,
                num_clients=20,
                symbols=['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'META', 'NVDA'],
                order_types=['LIMIT', 'MARKET'],
                price_range=(100, 200),
                quantity_range=(1, 100),
                description="Maximum stress test"
            )
        }
    
    def generate_order(self, scenario: TestScenario, client_id: str) -> Dict:
        """Generate a random order based on scenario."""
        order_type = random.choice(scenario.order_types)
        symbol = random.choice(scenario.symbols)
        side = random.choice(['BUY', 'SELL'])
        quantity = random.randint(*scenario.quantity_range)
        
        order = {
            'client_id': client_id,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'quantity': quantity,
            'order_id': f"{client_id}_{int(time.time() * 1000000)}"
        }
        
        if order_type == 'LIMIT':
            order['price'] = round(random.uniform(*scenario.price_range), 2)
        
        return order
    
    def run_scenario(self, scenario: TestScenario) -> PerformanceMetrics:
        """Run a specific test scenario."""
        print(f"\n🚀 Starting {scenario.name}")
        print(f"📊 Duration: {scenario.duration}s, Target: {scenario.orders_per_second} orders/sec")
        print(f"👥 Clients: {scenario.num_clients}, Symbols: {len(scenario.symbols)}")
        print(f"📝 Description: {scenario.description}")
        
        # Create clients
        clients = []
        for i in range(scenario.num_clients):
            client = PerformanceClient(f"perf_client_{i}", self.server_host, self.server_port)
            clients.append(client)
        
        # Calculate timing
        total_orders = scenario.duration * scenario.orders_per_second
        orders_per_client = total_orders // scenario.num_clients
        interval = 1.0 / (scenario.orders_per_second / scenario.num_clients)
        
        print(f"⏱️  Sending {total_orders} orders over {scenario.duration}s")
        print(f"📈 {orders_per_client} orders per client, {interval:.3f}s interval")
        
        # Start time
        start_time = time.time()
        results = []
        
        # Send orders
        with ThreadPoolExecutor(max_workers=scenario.num_clients) as executor:
            futures = []
            
            for client_idx, client in enumerate(clients):
                future = executor.submit(
                    self._client_worker,
                    client,
                    orders_per_client,
                    interval,
                    scenario
                )
                futures.append(future)
            
            # Collect results
            for future in as_completed(futures):
                client_results = future.result()
                results.extend(client_results)
        
        # Wait for remaining responses
        print("⏳ Waiting for remaining responses...")
        time.sleep(5)
        
        # Close clients
        for client in clients:
            client.close()
        
        # Calculate metrics
        end_time = time.time()
        actual_duration = end_time - start_time
        
        metrics = self._calculate_metrics(results, scenario, actual_duration)
        
        # Print results
        self._print_results(metrics, scenario)
        
        return metrics
    
    def _client_worker(self, client: PerformanceClient, num_orders: int, 
                      interval: float, scenario: TestScenario) -> List[TestResult]:
        """Worker function for each client."""
        results = []
        
        for i in range(num_orders):
            order = self.generate_order(scenario, client.client_id)
            result = client.send_order(order)
            results.append(result)
            
            # Sleep to maintain rate
            time.sleep(interval)
        
        return results
    
    def _calculate_metrics(self, results: List[TestResult], scenario: TestScenario, 
                          actual_duration: float) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        metrics = PerformanceMetrics()
        
        # Basic counts
        metrics.total_orders = len(results)
        metrics.successful_orders = sum(1 for r in results if r.success)
        metrics.failed_orders = metrics.total_orders - metrics.successful_orders
        metrics.total_trades = sum(r.trade_count for r in results)
        metrics.total_volume = sum(r.trade_count for r in results)  # Simplified
        
        # Latency calculations
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        if latencies:
            metrics.latencies = latencies
            metrics.avg_latency_ms = statistics.mean(latencies)
            metrics.p50_latency_ms = statistics.median(latencies)
            metrics.p95_latency_ms = np.percentile(latencies, 95)
            metrics.p99_latency_ms = np.percentile(latencies, 99)
            metrics.min_latency_ms = min(latencies)
            metrics.max_latency_ms = max(latencies)
        
        # Throughput calculations
        metrics.actual_throughput = metrics.total_orders / actual_duration
        metrics.target_throughput = scenario.orders_per_second
        metrics.throughput_efficiency = (metrics.actual_throughput / metrics.target_throughput) * 100
        
        # Error analysis
        metrics.error_rate = (metrics.failed_orders / metrics.total_orders) * 100
        error_types = defaultdict(int)
        for result in results:
            if not result.success and result.error_message:
                error_types[result.error_message] += 1
        metrics.error_types = dict(error_types)
        
        return metrics
    
    def _print_results(self, metrics: PerformanceMetrics, scenario: TestScenario):
        """Print formatted test results."""
        print(f"\n📊 {scenario.name} Results")
        print("=" * 50)
        
        # Order statistics
        print(f"📈 Orders: {metrics.total_orders:,} total, {metrics.successful_orders:,} successful")
        print(f"💰 Trades: {metrics.total_trades:,}, Volume: {metrics.total_volume:,}")
        print(f"❌ Errors: {metrics.failed_orders:,} ({metrics.error_rate:.2f}%)")
        
        # Throughput
        print(f"\n🚀 Throughput:")
        print(f"   Target: {metrics.target_throughput:.0f} orders/sec")
        print(f"   Actual: {metrics.actual_throughput:.2f} orders/sec")
        print(f"   Efficiency: {metrics.throughput_efficiency:.1f}%")
        
        # Latency
        if metrics.latencies:
            print(f"\n⏱️  Latency (ms):")
            print(f"   Average: {metrics.avg_latency_ms:.2f}")
            print(f"   Median (P50): {metrics.p50_latency_ms:.2f}")
            print(f"   P95: {metrics.p95_latency_ms:.2f}")
            print(f"   P99: {metrics.p99_latency_ms:.2f}")
            print(f"   Min: {metrics.min_latency_ms:.2f}")
            print(f"   Max: {metrics.max_latency_ms:.2f}")
        
        # Error details
        if metrics.error_types:
            print(f"\n❌ Error Details:")
            for error_type, count in metrics.error_types.items():
                print(f"   {error_type}: {count}")
    
    def run_all_scenarios(self) -> Dict[str, PerformanceMetrics]:
        """Run all predefined scenarios."""
        print("🏃‍♂️ Running Complete Performance Test Suite")
        print("=" * 60)
        
        all_results = {}
        
        for scenario_name, scenario in self.scenarios.items():
            try:
                metrics = self.run_scenario(scenario)
                all_results[scenario_name] = metrics
                
                # Brief pause between tests
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ Error running {scenario_name}: {e}")
                continue
        
        return all_results
    
    def generate_report(self, results: Dict[str, PerformanceMetrics], output_dir: str = "performance_reports"):
        """Generate comprehensive performance report."""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate CSV report
        csv_file = os.path.join(output_dir, f"performance_report_{timestamp}.csv")
        self._generate_csv_report(results, csv_file)
        
        # Generate charts
        charts_file = os.path.join(output_dir, f"performance_charts_{timestamp}.png")
        self._generate_charts(results, charts_file)
        
        # Generate summary
        summary_file = os.path.join(output_dir, f"performance_summary_{timestamp}.txt")
        self._generate_summary(results, summary_file)
        
        print(f"\n📄 Reports generated in '{output_dir}':")
        print(f"   📊 CSV Report: {csv_file}")
        print(f"   📈 Charts: {charts_file}")
        print(f"   📝 Summary: {summary_file}")
    
    def _generate_csv_report(self, results: Dict[str, PerformanceMetrics], filename: str):
        """Generate CSV performance report."""
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow([
                'Scenario', 'Total Orders', 'Successful Orders', 'Failed Orders',
                'Total Trades', 'Error Rate (%)', 'Target Throughput', 'Actual Throughput',
                'Efficiency (%)', 'Avg Latency (ms)', 'P50 Latency (ms)', 'P95 Latency (ms)',
                'P99 Latency (ms)', 'Min Latency (ms)', 'Max Latency (ms)'
            ])
            
            # Data
            for scenario_name, metrics in results.items():
                writer.writerow([
                    scenario_name, metrics.total_orders, metrics.successful_orders,
                    metrics.failed_orders, metrics.total_trades, metrics.error_rate,
                    metrics.target_throughput, metrics.actual_throughput,
                    metrics.throughput_efficiency, metrics.avg_latency_ms,
                    metrics.p50_latency_ms, metrics.p95_latency_ms, metrics.p99_latency_ms,
                    metrics.min_latency_ms, metrics.max_latency_ms
                ])
    
    def _generate_charts(self, results: Dict[str, PerformanceMetrics], filename: str):
        """Generate performance charts."""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('HFT Order Book Performance Test Results', fontsize=16)
        
        scenarios = list(results.keys())
        
        # Throughput comparison
        target_throughputs = [results[s].target_throughput for s in scenarios]
        actual_throughputs = [results[s].actual_throughput for s in scenarios]
        
        x = np.arange(len(scenarios))
        width = 0.35
        
        ax1.bar(x - width/2, target_throughputs, width, label='Target', alpha=0.8)
        ax1.bar(x + width/2, actual_throughputs, width, label='Actual', alpha=0.8)
        ax1.set_xlabel('Test Scenario')
        ax1.set_ylabel('Throughput (orders/sec)')
        ax1.set_title('Throughput Performance')
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Latency comparison
        avg_latencies = [results[s].avg_latency_ms for s in scenarios]
        p95_latencies = [results[s].p95_latency_ms for s in scenarios]
        p99_latencies = [results[s].p99_latency_ms for s in scenarios]
        
        ax2.bar(x - width, avg_latencies, width, label='Average', alpha=0.8)
        ax2.bar(x, p95_latencies, width, label='P95', alpha=0.8)
        ax2.bar(x + width, p99_latencies, width, label='P99', alpha=0.8)
        ax2.set_xlabel('Test Scenario')
        ax2.set_ylabel('Latency (ms)')
        ax2.set_title('Latency Performance')
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Error rates
        error_rates = [results[s].error_rate for s in scenarios]
        ax3.bar(scenarios, error_rates, alpha=0.8, color='red')
        ax3.set_xlabel('Test Scenario')
        ax3.set_ylabel('Error Rate (%)')
        ax3.set_title('Error Rates')
        ax3.tick_params(axis='x', rotation=45)
        ax3.grid(True, alpha=0.3)
        
        # Efficiency
        efficiencies = [results[s].throughput_efficiency for s in scenarios]
        ax4.bar(scenarios, efficiencies, alpha=0.8, color='green')
        ax4.set_xlabel('Test Scenario')
        ax4.set_ylabel('Efficiency (%)')
        ax4.set_title('Throughput Efficiency')
        ax4.tick_params(axis='x', rotation=45)
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _generate_summary(self, results: Dict[str, PerformanceMetrics], filename: str):
        """Generate text summary report."""
        with open(filename, 'w') as f:
            f.write("HFT Order Book Performance Test Summary\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for scenario_name, metrics in results.items():
                f.write(f"Scenario: {scenario_name}\n")
                f.write("-" * 30 + "\n")
                f.write(f"Total Orders: {metrics.total_orders:,}\n")
                f.write(f"Successful: {metrics.successful_orders:,}\n")
                f.write(f"Failed: {metrics.failed_orders:,}\n")
                f.write(f"Error Rate: {metrics.error_rate:.2f}%\n")
                f.write(f"Throughput: {metrics.actual_throughput:.2f} orders/sec\n")
                f.write(f"Efficiency: {metrics.throughput_efficiency:.1f}%\n")
                f.write(f"Avg Latency: {metrics.avg_latency_ms:.2f} ms\n")
                f.write(f"P99 Latency: {metrics.p99_latency_ms:.2f} ms\n\n")


def main():
    parser = argparse.ArgumentParser(description='HFT Order Book Performance Test Suite')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=8888, help='Server port')
    parser.add_argument('--scenario', choices=['smoke_test', 'low_load', 'medium_load', 'high_load', 'stress_test', 'all'],
                       default='all', help='Test scenario to run')
    parser.add_argument('--duration', type=int, help='Custom test duration (seconds)')
    parser.add_argument('--rate', type=int, help='Custom orders per second')
    parser.add_argument('--clients', type=int, help='Custom number of clients')
    parser.add_argument('--output-dir', default='performance_reports', help='Output directory for reports')
    
    args = parser.parse_args()
    
    # Create test suite
    test_suite = PerformanceTestSuite(args.host, args.port)
    
    if args.scenario == 'all':
        # Run all scenarios
        results = test_suite.run_all_scenarios()
        test_suite.generate_report(results, args.output_dir)
    else:
        # Run single scenario
        scenario = test_suite.scenarios[args.scenario]
        
        # Override with custom parameters if provided
        if args.duration:
            scenario.duration = args.duration
        if args.rate:
            scenario.orders_per_second = args.rate
        if args.clients:
            scenario.num_clients = args.clients
        
        metrics = test_suite.run_scenario(scenario)
        test_suite.generate_report({args.scenario: metrics}, args.output_dir)


if __name__ == '__main__':
    main() 