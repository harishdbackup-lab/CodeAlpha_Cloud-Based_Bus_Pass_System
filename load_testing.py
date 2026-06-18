"""
Load Testing and Performance Testing for Bus Pass System
Simulates high-traffic scenarios and concurrent bookings
"""

import requests
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

BASE_URL = 'http://localhost:5000'


class LoadTester:
    """Load testing utility"""
    
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.results = {
            'successful': [],
            'failed': [],
            'response_times': []
        }
        self.lock = threading.Lock()
    
    def register_passenger(self, email):
        """Register a test passenger"""
        try:
            response = requests.post(
                f'{self.base_url}/api/auth/register',
                json={
                    'phone_number': f'98765432{str(int(time.time()))[-2:]}',
                    'first_name': 'Test',
                    'last_name': 'User',
                    'email': email,
                    'password': 'TestPass123!'
                },
                timeout=10
            )
            return response.status_code == 201, response.json()
        except Exception as e:
            return False, str(e)
    
    def login_passenger(self, email):
        """Login a test passenger"""
        try:
            response = requests.post(
                f'{self.base_url}/api/auth/login',
                json={
                    'email': email,
                    'password': 'TestPass123!'
                },
                timeout=10
            )
            if response.status_code == 200:
                return True, response.json()['access_token']
            return False, None
        except Exception as e:
            return False, None
    
    def search_schedules(self, source, destination, date):
        """Search for schedules"""
        try:
            start_time = time.time()
            response = requests.get(
                f'{self.base_url}/api/search/schedules',
                params={'source': source, 'destination': destination, 'date': date},
                timeout=10
            )
            response_time = time.time() - start_time
            
            with self.lock:
                if response.status_code == 200:
                    self.results['successful'].append('search')
                    self.results['response_times'].append(response_time)
                    schedules = response.json().get('schedules', [])
                    return True, schedules
                else:
                    self.results['failed'].append('search')
                    return False, []
        except Exception as e:
            with self.lock:
                self.results['failed'].append('search')
            return False, []
    
    def create_booking(self, schedule_id, num_seats, token):
        """Create a booking"""
        try:
            start_time = time.time()
            response = requests.post(
                f'{self.base_url}/api/bookings/create',
                json={'schedule_id': schedule_id, 'num_seats': num_seats},
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            response_time = time.time() - start_time
            
            with self.lock:
                self.results['response_times'].append(response_time)
                if response.status_code == 201:
                    self.results['successful'].append('booking')
                    return True, response.json()
                else:
                    self.results['failed'].append('booking')
                    return False, None
        except Exception as e:
            with self.lock:
                self.results['failed'].append('booking')
            return False, None
    
    def simulate_concurrent_bookings(self, num_users=50, num_bookings_per_user=3):
        """Simulate concurrent booking requests"""
        print(f"\n=== Simulating {num_users} concurrent users ===")
        print(f"Each user will attempt {num_bookings_per_user} bookings\n")
        
        # First, create test users
        print("Creating test users...")
        tokens = []
        for i in range(num_users):
            email = f"test_user_{int(time.time())}_{i}@test.com"
            success, _ = self.register_passenger(email)
            if success:
                success, token = self.login_passenger(email)
                if success:
                    tokens.append(token)
        
        print(f"Created {len(tokens)} test users\n")
        
        # Search for available schedules
        print("Searching for schedules...")
        success, schedules = self.search_schedules('Mumbai', 'Pune', '2024-12-25')
        if not schedules:
            print("No schedules found for testing")
            return
        
        schedule_id = schedules[0]['id']
        print(f"Found schedule: {schedule_id}\n")
        
        # Simulate concurrent bookings
        print(f"Simulating {len(tokens) * num_bookings_per_user} concurrent booking requests...\n")
        
        def booking_worker(user_idx, booking_idx):
            if user_idx < len(tokens):
                self.create_booking(schedule_id, 1, tokens[user_idx])
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for i in range(len(tokens)):
                for j in range(num_bookings_per_user):
                    future = executor.submit(booking_worker, i, j)
                    futures.append(future)
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error: {e}")
        
        total_time = time.time() - start_time
        
        # Print results
        self.print_results(total_time)
    
    def print_results(self, total_time):
        """Print test results"""
        total_requests = len(self.results['successful']) + len(self.results['failed'])
        success_rate = (len(self.results['successful']) / total_requests * 100) if total_requests > 0 else 0
        
        print("\n" + "="*50)
        print("LOAD TEST RESULTS")
        print("="*50)
        print(f"Total Requests: {total_requests}")
        print(f"Successful: {len(self.results['successful'])}")
        print(f"Failed: {len(self.results['failed'])}")
        print(f"Success Rate: {success_rate:.2f}%")
        print(f"Total Time: {total_time:.2f} seconds")
        print(f"Requests/Second: {total_requests/total_time:.2f}")
        
        if self.results['response_times']:
            response_times = self.results['response_times']
            print(f"\nResponse Time Statistics:")
            print(f"  Min: {min(response_times):.3f}s")
            print(f"  Max: {max(response_times):.3f}s")
            print(f"  Mean: {statistics.mean(response_times):.3f}s")
            print(f"  Median: {statistics.median(response_times):.3f}s")
            if len(response_times) > 1:
                print(f"  StdDev: {statistics.stdev(response_times):.3f}s")
        
        print("="*50)


if __name__ == '__main__':
    print("Bus Pass System - Load Testing")
    print("Ensure server is running on http://localhost:5000\n")
    
    try:
        # Check server health
        response = requests.get(f'{BASE_URL}/health', timeout=5)
        if response.status_code == 200:
            print("Server is running. Starting load test...\n")
            
            tester = LoadTester()
            # Simulate 50 concurrent users with 3 bookings each
            tester.simulate_concurrent_bookings(num_users=50, num_bookings_per_user=3)
        else:
            print("Server is not responding correctly")
    
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server at http://localhost:5000")
        print("Please ensure the server is running:")
        print("  1. pip install -r requirements.txt")
        print("  2. python app.py")
