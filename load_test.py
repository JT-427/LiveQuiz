#!/usr/bin/env python3
"""
流量測試工具 - 針對註冊 API (/api/users) 進行壓力測試
"""

import requests
import time
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
import argparse
from datetime import datetime


class LoadTestResult:
    """測試結果統計"""
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.error_messages = []
        self.start_time = None
        self.end_time = None
    
    def add_result(self, success: bool, response_time: float, error_msg: str = None):
        """添加測試結果"""
        self.total_requests += 1
        self.response_times.append(response_time)
        
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error_msg:
                self.error_messages.append(error_msg)
    
    def get_statistics(self) -> Dict:
        """獲取統計資訊"""
        if not self.response_times:
            return {}
        
        sorted_times = sorted(self.response_times)
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        stats = {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0,
            'total_time': total_time,
            'requests_per_second': self.total_requests / total_time if total_time > 0 else 0,
            'avg_response_time': sum(self.response_times) / len(self.response_times),
            'min_response_time': min(self.response_times),
            'max_response_time': max(self.response_times),
            'median_response_time': sorted_times[len(sorted_times) // 2],
            'p95_response_time': sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
            'p99_response_time': sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0,
        }
        
        return stats


def generate_random_name(length: int = 8) -> str:
    """生成隨機使用者名稱"""
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))


def generate_random_group_name(groups: List[str] = None) -> str:
    """生成隨機組名"""
    if groups:
        return random.choice(groups)
    
    # 預設組名
    default_groups = ['第1組', '第2組', '第3組', '第4組', '第5組', '未分組']
    return random.choice(default_groups)


def send_register_request(base_url: str, activity_id: int, name: str = None, 
                         group_name: str = None, timeout: int = 10) -> Tuple[bool, float, str]:
    """
    發送註冊請求
    
    Returns:
        (success, response_time, error_message)
    """
    if name is None:
        name = generate_random_name()
    
    url = f"{base_url}/api/users"
    payload = {
        "activity_id": activity_id,
        "name": name
    }
    
    if group_name:
        payload["group_name"] = group_name
    
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response_time = time.time() - start_time
        
        if response.status_code == 201:
            return (True, response_time, None)
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
            return (False, response_time, error_msg)
    
    except requests.exceptions.Timeout:
        response_time = time.time() - start_time
        return (False, response_time, "請求逾時")
    
    except requests.exceptions.ConnectionError:
        response_time = time.time() - start_time
        return (False, response_time, "連線錯誤")
    
    except Exception as e:
        response_time = time.time() - start_time
        return (False, response_time, f"發生錯誤: {str(e)}")


def run_load_test(base_url: str, activity_id: int, num_requests: int, 
                 concurrency: int, group_names: List[str] = None, 
                 delay_range: Tuple[float, float] = None) -> LoadTestResult:
    """
    執行流量測試
    
    Args:
        base_url: 系統基礎 URL (例如: http://localhost:5001)
        activity_id: 活動 ID
        num_requests: 總請求數
        concurrency: 並發數量
        group_names: 可選的組名列表
        delay_range: 每個請求之間的延遲範圍（秒），格式為 (min, max)
    
    Returns:
        LoadTestResult 物件
    """
    result = LoadTestResult()
    result.start_time = time.time()
    
    print(f"開始流量測試...")
    print(f"目標 URL: {base_url}/api/users")
    print(f"活動 ID: {activity_id}")
    print(f"總請求數: {num_requests}")
    print(f"並發數量: {concurrency}")
    print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        
        for i in range(num_requests):
            # 生成隨機組名（如果提供）
            group_name = None
            if group_names:
                group_name = generate_random_group_name(group_names)
            
            # 提交任務
            future = executor.submit(
                send_register_request,
                base_url,
                activity_id,
                name=f"測試使用者_{i}_{generate_random_name(6)}",
                group_name=group_name
            )
            futures.append(future)
            
            # 添加延遲（如果指定）
            if delay_range and i < num_requests - 1:
                delay = random.uniform(delay_range[0], delay_range[1])
                time.sleep(delay)
        
        # 收集結果
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                success, response_time, error_msg = future.result()
                result.add_result(success, response_time, error_msg)
                
                # 顯示進度
                if completed % max(1, num_requests // 10) == 0 or completed == num_requests:
                    progress = (completed / num_requests) * 100
                    print(f"進度: {completed}/{num_requests} ({progress:.1f}%) - "
                          f"成功: {result.successful_requests}, 失敗: {result.failed_requests}")
            
            except Exception as e:
                result.add_result(False, 0, f"執行錯誤: {str(e)}")
    
    result.end_time = time.time()
    return result


def print_statistics(result: LoadTestResult):
    """列印統計資訊"""
    stats = result.get_statistics()
    
    print("\n" + "=" * 60)
    print("測試結果統計")
    print("=" * 60)
    print(f"總請求數: {stats['total_requests']}")
    print(f"成功請求: {stats['successful_requests']}")
    print(f"失敗請求: {stats['failed_requests']}")
    print(f"成功率: {stats['success_rate']:.2f}%")
    print(f"\n總耗時: {stats['total_time']:.2f} 秒")
    print(f"請求速率: {stats['requests_per_second']:.2f} 請求/秒")
    print(f"\n回應時間統計:")
    print(f"  平均: {stats['avg_response_time']:.3f} 秒")
    print(f"  最小: {stats['min_response_time']:.3f} 秒")
    print(f"  最大: {stats['max_response_time']:.3f} 秒")
    print(f"  中位數: {stats['median_response_time']:.3f} 秒")
    print(f"  P95: {stats['p95_response_time']:.3f} 秒")
    print(f"  P99: {stats['p99_response_time']:.3f} 秒")
    
    if result.error_messages:
        print(f"\n錯誤訊息範例 (顯示前 5 個):")
        for i, error in enumerate(result.error_messages[:5], 1):
            print(f"  {i}. {error}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='流量測試工具 - 針對註冊 API 進行壓力測試',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 基本測試: 100 個請求, 10 個並發
  python load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10
  
  # 高壓力測試: 1000 個請求, 50 個並發
  python load_test.py -u http://localhost:5001 -a 1 -n 1000 -c 50
  
  # 指定組名
  python load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10 --groups "第1組,第2組,第3組"
  
  # 添加請求間延遲 (0.1 到 0.5 秒)
  python load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10 --delay 0.1 0.5
        """
    )
    
    parser.add_argument('-u', '--url', required=True,
                       help='系統基礎 URL (例如: http://localhost:5001)')
    parser.add_argument('-a', '--activity-id', type=int, required=True,
                       help='活動 ID')
    parser.add_argument('-n', '--num-requests', type=int, default=100,
                       help='總請求數 (預設: 100)')
    parser.add_argument('-c', '--concurrency', type=int, default=10,
                       help='並發數量 (預設: 10)')
    parser.add_argument('--groups', type=str,
                       help='組名列表，以逗號分隔 (例如: "第1組,第2組,第3組")')
    parser.add_argument('--delay', nargs=2, type=float, metavar=('MIN', 'MAX'),
                       help='每個請求之間的延遲範圍 (秒)')
    parser.add_argument('--timeout', type=int, default=10,
                       help='請求逾時時間 (秒) (預設: 10)')
    
    args = parser.parse_args()
    
    # 解析組名
    group_names = None
    if args.groups:
        group_names = [g.strip() for g in args.groups.split(',')]
    
    # 解析延遲範圍
    delay_range = None
    if args.delay:
        delay_range = (args.delay[0], args.delay[1])
    
    # 確保 URL 不包含尾部斜線
    base_url = args.url.rstrip('/')
    
    # 執行測試
    result = run_load_test(
        base_url=base_url,
        activity_id=args.activity_id,
        num_requests=args.num_requests,
        concurrency=args.concurrency,
        group_names=group_names,
        delay_range=delay_range
    )
    
    # 顯示結果
    print_statistics(result)


if __name__ == '__main__':
    main()

