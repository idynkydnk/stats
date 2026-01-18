#!/usr/bin/env python3
"""
Performance Benchmarking Script for Stats App

Usage:
    python benchmark.py [--url BASE_URL] [--runs N] [--save FILENAME]

Examples:
    python benchmark.py                           # Test localhost:5000
    python benchmark.py --url https://mysite.com  # Test production site
    python benchmark.py --runs 5 --save before    # 5 runs, save to before_benchmark.json
"""

import requests
import time
import argparse
import json
from datetime import datetime
from statistics import mean, stdev
from concurrent.futures import ThreadPoolExecutor
import sys

# ANSI colors for terminal output
class Colors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def color_time(seconds):
    """Color-code time based on speed."""
    ms = seconds * 1000
    if ms < 200:
        return f"{Colors.GREEN}{ms:.0f}ms{Colors.END}"
    elif ms < 500:
        return f"{Colors.YELLOW}{ms:.0f}ms{Colors.END}"
    elif ms < 1000:
        return f"{Colors.RED}{ms:.0f}ms{Colors.END}"
    else:
        return f"{Colors.RED}{Colors.BOLD}{ms:.0f}ms{Colors.END}"

# Key routes to benchmark (most important/frequently used)
ROUTES = [
    # Main pages
    ('/', 'Homepage'),
    ('/stats/2025/', 'Stats 2025'),
    ('/stats/2026/', 'Stats 2026'),
    
    # Dashboard
    ('/dashboard/', 'Dashboard'),
    ('/combined_dashboard/', 'Combined Dashboard'),
    
    # Player pages
    ('/player_list/', 'Player List'),
    ('/player_trends/', 'Player Trends'),
    
    # Games listing
    ('/games/', 'Games List'),
    ('/vollis_games/', 'Vollis Games'),
    ('/one_v_one_games/', 'One v One Games'),
    ('/other_games/', 'Other Games'),
    
    # Stats pages
    ('/vollis_stats/', 'Vollis Stats'),
    ('/one_v_one_stats/', 'One v One Stats'),
    ('/other_stats/', 'Other Stats'),
    ('/volleyball_stats/', 'Volleyball Stats'),
    ('/advanced_stats/', 'Advanced Stats'),
    
    # Rankings
    ('/glicko_rankings/', 'Glicko Rankings'),
    ('/trueskill_rankings/', 'TrueSkill Rankings'),
    
    # Other
    ('/kobs/', 'KOBs'),
    ('/tournaments/', 'Tournaments'),
    ('/top_teams/', 'Top Teams'),
    ('/game_hub', 'Game Hub'),
]

def benchmark_route(base_url, route, name, runs=3, session=None):
    """Benchmark a single route with multiple runs."""
    url = f"{base_url.rstrip('/')}{route}"
    times = []
    errors = []
    
    req = session if session else requests
    
    for i in range(runs):
        try:
            start = time.perf_counter()
            response = req.get(url, timeout=30)
            elapsed = time.perf_counter() - start
            
            if response.status_code == 200:
                times.append(elapsed)
            else:
                errors.append(f"HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            errors.append("Timeout")
        except requests.exceptions.ConnectionError:
            errors.append("Connection Error")
        except Exception as e:
            errors.append(str(e))
    
    return {
        'route': route,
        'name': name,
        'times': times,
        'avg': mean(times) if times else None,
        'min': min(times) if times else None,
        'max': max(times) if times else None,
        'stdev': stdev(times) if len(times) > 1 else 0,
        'errors': errors,
        'runs': runs,
        'successful_runs': len(times),
    }

def run_benchmark(base_url, runs=3, verbose=True):
    """Run benchmark on all routes."""
    results = []
    session = requests.Session()  # Reuse connection
    
    if verbose:
        print(f"\n{Colors.BOLD}🚀 Starting Performance Benchmark{Colors.END}")
        print(f"   URL: {base_url}")
        print(f"   Runs per route: {runs}")
        print(f"   Routes to test: {len(ROUTES)}")
        print("-" * 60)
    
    for i, (route, name) in enumerate(ROUTES, 1):
        if verbose:
            print(f"[{i:2}/{len(ROUTES)}] Testing {name}...", end=" ", flush=True)
        
        result = benchmark_route(base_url, route, name, runs, session)
        results.append(result)
        
        if verbose:
            if result['avg']:
                print(color_time(result['avg']))
            else:
                print(f"{Colors.RED}FAILED{Colors.END} ({', '.join(result['errors'])})")
    
    return results

def print_summary(results):
    """Print a summary of benchmark results."""
    print(f"\n{Colors.BOLD}📊 BENCHMARK RESULTS{Colors.END}")
    print("=" * 70)
    
    # Sort by average time (slowest first)
    sorted_results = sorted(
        [r for r in results if r['avg'] is not None],
        key=lambda x: x['avg'],
        reverse=True
    )
    
    # Header
    print(f"{'Route':<35} {'Avg':>10} {'Min':>10} {'Max':>10}")
    print("-" * 70)
    
    for r in sorted_results:
        avg_str = color_time(r['avg'])
        min_str = f"{r['min']*1000:.0f}ms"
        max_str = f"{r['max']*1000:.0f}ms"
        print(f"{r['name']:<35} {avg_str:>20} {min_str:>10} {max_str:>10}")
    
    # Failed routes
    failed = [r for r in results if r['avg'] is None]
    if failed:
        print(f"\n{Colors.RED}Failed routes:{Colors.END}")
        for r in failed:
            print(f"  - {r['name']}: {', '.join(r['errors'])}")
    
    # Statistics
    successful = [r['avg'] for r in results if r['avg'] is not None]
    if successful:
        print(f"\n{Colors.BOLD}📈 SUMMARY{Colors.END}")
        print("-" * 40)
        print(f"  Total routes tested: {len(results)}")
        print(f"  Successful: {len(successful)}")
        print(f"  Failed: {len(failed)}")
        print(f"  Fastest: {min(successful)*1000:.0f}ms")
        print(f"  Slowest: {max(successful)*1000:.0f}ms")
        print(f"  Average: {mean(successful)*1000:.0f}ms")
        print(f"  Total time: {sum(successful)*1000:.0f}ms")
        
        # Identify slow pages (>500ms)
        slow = [r for r in sorted_results if r['avg'] > 0.5]
        if slow:
            print(f"\n{Colors.YELLOW}⚠️  SLOW PAGES (>500ms):{Colors.END}")
            for r in slow:
                print(f"  - {r['name']}: {r['avg']*1000:.0f}ms")

def save_results(results, filename):
    """Save benchmark results to JSON file in benchmarks folder."""
    import os
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    benchmarks_dir = os.path.join(script_dir, 'benchmarks')
    
    # Create benchmarks directory if it doesn't exist
    os.makedirs(benchmarks_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    full_filename = f"benchmark_{timestamp}.json" if filename == 'auto' else f"{filename}_benchmark.json"
    filepath = os.path.join(benchmarks_dir, full_filename)
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'results': results,
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\n💾 Results saved to: {filepath}")

def compare_results(before_file, after_file):
    """Compare two benchmark result files."""
    import os
    
    # Check if files exist as-is, or look in benchmarks folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    benchmarks_dir = os.path.join(script_dir, 'benchmarks')
    
    if not os.path.exists(before_file):
        before_file = os.path.join(benchmarks_dir, before_file)
    if not os.path.exists(after_file):
        after_file = os.path.join(benchmarks_dir, after_file)
    
    with open(before_file) as f:
        before = json.load(f)
    with open(after_file) as f:
        after = json.load(f)
    
    print(f"\n{Colors.BOLD}📊 COMPARISON: {before_file} vs {after_file}{Colors.END}")
    print("=" * 80)
    print(f"{'Route':<35} {'Before':>12} {'After':>12} {'Change':>15}")
    print("-" * 80)
    
    before_dict = {r['route']: r for r in before['results']}
    after_dict = {r['route']: r for r in after['results']}
    
    improvements = []
    regressions = []
    
    for route in before_dict:
        if route in after_dict:
            b = before_dict[route]
            a = after_dict[route]
            
            if b['avg'] and a['avg']:
                change = ((a['avg'] - b['avg']) / b['avg']) * 100
                change_str = f"{change:+.1f}%"
                
                if change < -10:
                    change_str = f"{Colors.GREEN}{change_str}{Colors.END}"
                    improvements.append((b['name'], change))
                elif change > 10:
                    change_str = f"{Colors.RED}{change_str}{Colors.END}"
                    regressions.append((b['name'], change))
                
                print(f"{b['name']:<35} {b['avg']*1000:>10.0f}ms {a['avg']*1000:>10.0f}ms {change_str:>20}")
    
    print("\n" + "-" * 80)
    if improvements:
        print(f"{Colors.GREEN}✅ Improved:{Colors.END}")
        for name, change in sorted(improvements, key=lambda x: x[1]):
            print(f"   {name}: {change:.1f}%")
    if regressions:
        print(f"{Colors.RED}❌ Regressed:{Colors.END}")
        for name, change in sorted(regressions, key=lambda x: x[1], reverse=True):
            print(f"   {name}: +{change:.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Benchmark Flask app performance')
    parser.add_argument('--url', default='http://127.0.0.1:5000', 
                        help='Base URL to benchmark (default: http://127.0.0.1:5000)')
    parser.add_argument('--runs', type=int, default=3,
                        help='Number of runs per route (default: 3)')
    parser.add_argument('--save', type=str, nargs='?', const='auto',
                        help='Save results to benchmarks folder (e.g., "before" saves to before_benchmark.json, or just --save for auto timestamp)')
    parser.add_argument('--compare', nargs=2, metavar=('BEFORE', 'AFTER'),
                        help='Compare two benchmark files')
    
    args = parser.parse_args()
    
    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return
    
    # Check if server is reachable
    try:
        requests.get(args.url, timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"{Colors.RED}Error: Cannot connect to {args.url}{Colors.END}")
        print(f"Make sure your Flask app is running: python stats.py")
        sys.exit(1)
    
    results = run_benchmark(args.url, runs=args.runs)
    print_summary(results)
    
    if args.save:
        filename = f"{args.save}_benchmark.json"
        save_results(results, filename)

if __name__ == '__main__':
    main()
