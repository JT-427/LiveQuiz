#!/usr/bin/env python3
"""
Socket.IO 流量測試工具 - 針對 WebSocket 連接和事件進行壓力測試
"""

import socketio
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
import argparse
from datetime import datetime
from collections import defaultdict
import queue


class SocketTestResult:
    """Socket.IO 測試結果統計"""
    def __init__(self):
        self.total_clients = 0
        self.connected_clients = 0
        self.disconnected_clients = 0
        self.failed_connections = 0
        
        # 事件統計
        self.events_sent = defaultdict(int)
        self.events_received = defaultdict(int)
        self.events_failed = defaultdict(int)
        
        # 時間統計
        self.connection_times = []
        self.event_response_times = defaultdict(list)
        
        # 錯誤訊息
        self.error_messages = []
        
        self.start_time = None
        self.end_time = None
        
        # 客戶端狀態
        self.client_states = {}  # {client_id: {'connected': bool, 'events_sent': int, 'events_received': int}}
    
    def add_connection(self, client_id: str, success: bool, connection_time: float, error_msg: str = None):
        """記錄連接結果"""
        self.total_clients += 1
        self.connection_times.append(connection_time)
        
        if success:
            self.connected_clients += 1
            if client_id not in self.client_states:
                self.client_states[client_id] = {
                    'connected': True,
                    'events_sent': 0,
                    'events_received': 0
                }
        else:
            self.failed_connections += 1
            if error_msg:
                self.error_messages.append(error_msg)
    
    def add_disconnection(self, client_id: str):
        """記錄斷線"""
        self.disconnected_clients += 1
        if client_id in self.client_states:
            self.client_states[client_id]['connected'] = False
    
    def add_event_sent(self, client_id: str, event_name: str, success: bool = True):
        """記錄發送的事件"""
        self.events_sent[event_name] += 1
        if client_id in self.client_states:
            self.client_states[client_id]['events_sent'] += 1
        if not success:
            self.events_failed[event_name] += 1
    
    def add_event_received(self, client_id: str, event_name: str, response_time: float = None):
        """記錄接收到的事件"""
        self.events_received[event_name] += 1
        if client_id in self.client_states:
            self.client_states[client_id]['events_received'] += 1
        if response_time is not None:
            self.event_response_times[event_name].append(response_time)
    
    def get_statistics(self) -> Dict:
        """獲取統計資訊"""
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        # 計算事件總數
        total_events_sent = sum(self.events_sent.values())
        total_events_received = sum(self.events_received.values())
        
        stats = {
            'total_clients': self.total_clients,
            'connected_clients': self.connected_clients,
            'disconnected_clients': self.disconnected_clients,
            'failed_connections': self.failed_connections,
            'connection_success_rate': (self.connected_clients / self.total_clients * 100) if self.total_clients > 0 else 0,
            'total_time': total_time,
            'total_events_sent': total_events_sent,
            'total_events_received': total_events_received,
            'events_sent': dict(self.events_sent),
            'events_received': dict(self.events_received),
            'events_failed': dict(self.events_failed),
        }
        
        # 連接時間統計
        if self.connection_times:
            sorted_times = sorted(self.connection_times)
            stats['connection_time'] = {
                'avg': sum(self.connection_times) / len(self.connection_times),
                'min': min(self.connection_times),
                'max': max(self.connection_times),
                'median': sorted_times[len(sorted_times) // 2],
                'p95': sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
                'p99': sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0,
            }
        
        # 事件回應時間統計
        stats['event_response_times'] = {}
        for event_name, times in self.event_response_times.items():
            if times:
                sorted_times = sorted(times)
                stats['event_response_times'][event_name] = {
                    'avg': sum(times) / len(times),
                    'min': min(times),
                    'max': max(times),
                    'median': sorted_times[len(sorted_times) // 2],
                    'p95': sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
                    'p99': sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0,
                }
        
        return stats


class SocketClient:
    """Socket.IO 客戶端封裝"""
    def __init__(self, client_id: str, server_url: str, result: SocketTestResult, 
                 activity_id: Optional[int] = None, client_type: str = 'user'):
        self.client_id = client_id
        self.server_url = server_url
        self.result = result
        self.activity_id = activity_id
        self.client_type = client_type  # 'user', 'display', 'admin'
        self.sio = None
        self.connected = False
        self.disconnect_reason = None
        self.event_queue = queue.Queue()
        self.received_events = {}
        
    def connect(self, timeout: int = 10) -> Tuple[bool, float, str]:
        """連接到 Socket.IO 伺服器"""
        start_time = time.time()
        try:
            # 設定 headers（針對 ngrok 或其他需要特殊 header 的情況）
            headers = {}
            # 如果 URL 包含 ngrok，可能需要設置 bypass 標頭
            if 'ngrok' in self.server_url.lower():
                headers['ngrok-skip-browser-warning'] = 'true'
            
            # 初始化 Client，不使用 timeout 參數
            self.sio = socketio.Client(reconnection=False)
            
            # 設定事件處理器
            @self.sio.on('connect')
            def on_connect():
                self.connected = True
                self.result.add_event_received(self.client_id, 'connect')
            
            @self.sio.on('disconnect')
            def on_disconnect():
                self.connected = False
                self.result.add_disconnection(self.client_id)
            
            @self.sio.on('connected')
            def on_connected(data):
                self.result.add_event_received(self.client_id, 'connected')
                self.event_queue.put(('connected', data, time.time()))
            
            @self.sio.on('joined_activity')
            def on_joined_activity(data):
                self.result.add_event_received(self.client_id, 'joined_activity')
                self.event_queue.put(('joined_activity', data, time.time()))
            
            @self.sio.on('display_joined')
            def on_display_joined(data):
                self.result.add_event_received(self.client_id, 'display_joined')
                self.event_queue.put(('display_joined', data, time.time()))
            
            @self.sio.on('activity_updated')
            def on_activity_updated(data):
                self.result.add_event_received(self.client_id, 'activity_updated')
                self.event_queue.put(('activity_updated', data, time.time()))
            
            @self.sio.on('user_joined')
            def on_user_joined(data):
                self.result.add_event_received(self.client_id, 'user_joined')
                self.event_queue.put(('user_joined', data, time.time()))
            
            @self.sio.on('answer_submitted')
            def on_answer_submitted(data):
                self.result.add_event_received(self.client_id, 'answer_submitted')
                self.event_queue.put(('answer_submitted', data, time.time()))
            
            @self.sio.on('timer_update')
            def on_timer_update(data):
                self.result.add_event_received(self.client_id, 'timer_update')
                self.event_queue.put(('timer_update', data, time.time()))
            
            @self.sio.on('display_update')
            def on_display_update(data):
                self.result.add_event_received(self.client_id, 'display_update')
                self.event_queue.put(('display_update', data, time.time()))
            
            # 連接到伺服器（帶上 headers）
            # 注意：socketio.Client.connect() 可能不支援 wait_timeout 參數
            # 我們使用簡單的 connect() 然後手動等待
            try:
                if headers:
                    self.sio.connect(self.server_url, headers=headers)
                else:
                    self.sio.connect(self.server_url)
            except Exception as connect_err:
                # 如果連接時就出錯，直接返回
                connection_time = time.time() - start_time
                return (False, connection_time, f"連接失敗: {str(connect_err)[:100]}")
            
            # 等待連接確認
            connection_timeout = timeout
            check_interval = 0.1
            elapsed = 0
            while not self.connected and elapsed < connection_timeout:
                time.sleep(check_interval)
                elapsed += check_interval
            
            connection_time = time.time() - start_time
            
            if self.connected:
                return (True, connection_time, None)
            else:
                return (False, connection_time, "連接超時")
        
        except socketio.exceptions.ConnectionError as e:
            connection_time = time.time() - start_time
            return (False, connection_time, f"連接錯誤: {str(e)}")
        except Exception as e:
            connection_time = time.time() - start_time
            error_msg = str(e)
            # 截斷過長的錯誤訊息
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            return (False, connection_time, f"發生錯誤: {error_msg}")
    
    def emit_event(self, event_name: str, data: Dict = None, wait_response: bool = False, 
                   timeout: float = 5.0) -> Tuple[bool, float]:
        """發送事件"""
        if not self.connected or not self.sio:
            return (False, 0)
        
        start_time = time.time()
        try:
            if wait_response:
                # 等待回應
                callback_received = threading.Event()
                response_data = [None]
                
                def callback(*args):
                    response_data[0] = args
                    callback_received.set()
                
                self.sio.emit(event_name, data or {}, callback=callback)
                
                if callback_received.wait(timeout):
                    response_time = time.time() - start_time
                    self.result.add_event_sent(self.client_id, event_name, True)
                    return (True, response_time)
                else:
                    response_time = time.time() - start_time
                    self.result.add_event_sent(self.client_id, event_name, False)
                    return (False, response_time)
            else:
                self.sio.emit(event_name, data or {})
                response_time = time.time() - start_time
                self.result.add_event_sent(self.client_id, event_name, True)
                return (True, response_time)
        
        except Exception as e:
            response_time = time.time() - start_time
            self.result.add_event_sent(self.client_id, event_name, False)
            return (False, response_time)
    
    def disconnect(self):
        """斷開連接"""
        if self.sio and self.connected:
            try:
                self.sio.disconnect()
            except:
                pass
            self.connected = False


def run_client_test(client: SocketClient, num_events: int, event_interval: float = None) -> bool:
    """執行單個客戶端測試"""
    # 連接
    success, conn_time, error_msg = client.connect()
    client.result.add_connection(client.client_id, success, conn_time, error_msg)
    
    if not success:
        return False
    
    # 根據客戶端類型發送不同的事件
    if client.client_type == 'user':
        # 使用者客戶端：加入活動
        if client.activity_id:
            client.emit_event('join_activity', {'activity_id': client.activity_id})
    elif client.client_type == 'display':
        # 顯示客戶端：加入顯示
        client.emit_event('join_display')
    
    # 發送指定數量的事件
    for i in range(num_events):
        # 可以發送各種事件進行測試
        if client.client_type == 'user' and client.activity_id:
            # 使用者可以發送計時器廣播等（模擬管理員行為）
            if random.random() < 0.1:  # 10% 機率發送計時器事件
                client.emit_event('broadcast_timer', {
                    'activity_id': client.activity_id,
                    'time_remaining': random.randint(0, 60)
                })
        
        # 延遲
        if event_interval and i < num_events - 1:
            time.sleep(random.uniform(event_interval * 0.5, event_interval * 1.5))
    
    # 保持連接一段時間（模擬真實使用情境）
    time.sleep(1)
    
    # 斷開連接
    client.disconnect()
    return True


def run_socket_load_test(server_url: str, num_clients: int, concurrency: int,
                         activity_id: Optional[int] = None, client_type: str = 'user',
                         num_events_per_client: int = 5, event_interval: float = None,
                         connection_delay_range: Tuple[float, float] = None) -> SocketTestResult:
    """
    執行 Socket.IO 流量測試
    
    Args:
        server_url: 伺服器 URL (例如: http://localhost:5001)
        num_clients: 客戶端總數
        concurrency: 並發數量
        activity_id: 活動 ID（可選）
        client_type: 客戶端類型 ('user', 'display', 'admin')
        num_events_per_client: 每個客戶端發送的事件數
        event_interval: 事件之間的間隔（秒）
        connection_delay_range: 連接之間的延遲範圍（秒）
    
    Returns:
        SocketTestResult 物件
    """
    result = SocketTestResult()
    result.start_time = time.time()
    
    print(f"開始 Socket.IO 流量測試...")
    print(f"伺服器 URL: {server_url}")
    print(f"客戶端類型: {client_type}")
    print(f"總客戶端數: {num_clients}")
    print(f"並發數量: {concurrency}")
    if activity_id:
        print(f"活動 ID: {activity_id}")
    print(f"每個客戶端事件數: {num_events_per_client}")
    print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    clients = []
    for i in range(num_clients):
        client_id = f"{client_type}_{i}"
        client = SocketClient(
            client_id=client_id,
            server_url=server_url,
            result=result,
            activity_id=activity_id,
            client_type=client_type
        )
        clients.append(client)
    
    # 使用線程池執行測試
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        
        for i, client in enumerate(clients):
            # 添加連接延遲
            if connection_delay_range and i > 0:
                delay = random.uniform(connection_delay_range[0], connection_delay_range[1])
                time.sleep(delay)
            
            future = executor.submit(run_client_test, client, num_events_per_client, event_interval)
            futures.append(future)
        
        # 收集結果
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                future.result()
                
                # 顯示進度
                if completed % max(1, num_clients // 10) == 0 or completed == num_clients:
                    progress = (completed / num_clients) * 100
                    print(f"進度: {completed}/{num_clients} ({progress:.1f}%) - "
                          f"已連接: {result.connected_clients}, 失敗: {result.failed_connections}")
            
            except Exception as e:
                print(f"客戶端執行錯誤: {str(e)}")
    
    result.end_time = time.time()
    return result


def print_statistics(result: SocketTestResult):
    """列印統計資訊"""
    stats = result.get_statistics()
    
    print("\n" + "=" * 60)
    print("Socket.IO 測試結果統計")
    print("=" * 60)
    
    print(f"\n【連接統計】")
    print(f"總客戶端數: {stats['total_clients']}")
    print(f"成功連接: {stats['connected_clients']}")
    print(f"失敗連接: {stats['failed_connections']}")
    print(f"斷線數: {stats['disconnected_clients']}")
    print(f"連接成功率: {stats['connection_success_rate']:.2f}%")
    
    if stats.get('connection_time'):
        ct = stats['connection_time']
        print(f"\n連接時間統計:")
        print(f"  平均: {ct['avg']:.3f} 秒")
        print(f"  最小: {ct['min']:.3f} 秒")
        print(f"  最大: {ct['max']:.3f} 秒")
        print(f"  中位數: {ct['median']:.3f} 秒")
        print(f"  P95: {ct['p95']:.3f} 秒")
        print(f"  P99: {ct['p99']:.3f} 秒")
    
    print(f"\n【事件統計】")
    print(f"總發送事件數: {stats['total_events_sent']}")
    print(f"總接收事件數: {stats['total_events_received']}")
    print(f"\n發送事件詳細:")
    for event_name, count in stats['events_sent'].items():
        failed = stats['events_failed'].get(event_name, 0)
        print(f"  {event_name}: {count} (失敗: {failed})")
    
    print(f"\n接收事件詳細:")
    for event_name, count in stats['events_received'].items():
        print(f"  {event_name}: {count}")
    
    if stats.get('event_response_times'):
        print(f"\n【事件回應時間統計】")
        for event_name, times in stats['event_response_times'].items():
            print(f"  {event_name}:")
            print(f"    平均: {times['avg']:.3f} 秒")
            print(f"    最小: {times['min']:.3f} 秒")
            print(f"    最大: {times['max']:.3f} 秒")
            print(f"    中位數: {times['median']:.3f} 秒")
            print(f"    P95: {times['p95']:.3f} 秒")
            print(f"    P99: {times['p99']:.3f} 秒")
    
    print(f"\n【測試時間】")
    print(f"總耗時: {stats['total_time']:.2f} 秒")
    
    if result.error_messages:
        print(f"\n【錯誤訊息範例】(顯示前 5 個)")
        for i, error in enumerate(result.error_messages[:5], 1):
            print(f"  {i}. {error}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Socket.IO 流量測試工具 - 針對 WebSocket 連接和事件進行壓力測試',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 基本測試: 100 個使用者客戶端, 10 個並發
  python socket_load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10
  
  # 高壓力測試: 1000 個客戶端, 50 個並發
  python socket_load_test.py -u http://localhost:5001 -a 1 -n 1000 -c 50
  
  # 測試顯示客戶端
  python socket_load_test.py -u http://localhost:5001 -n 50 -c 10 --type display
  
  # 指定每個客戶端發送的事件數
  python socket_load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10 -e 20
  
  # 添加事件間延遲
  python socket_load_test.py -u http://localhost:5001 -a 1 -n 100 -c 10 --event-interval 0.5
        """
    )
    
    parser.add_argument('-u', '--url', required=True,
                       help='伺服器 URL (例如: http://localhost:5001)')
    parser.add_argument('-a', '--activity-id', type=int,
                       help='活動 ID（使用者客戶端需要）')
    parser.add_argument('-n', '--num-clients', type=int, default=100,
                       help='客戶端總數 (預設: 100)')
    parser.add_argument('-c', '--concurrency', type=int, default=10,
                       help='並發數量 (預設: 10)')
    parser.add_argument('-t', '--type', type=str, default='user',
                       choices=['user', 'display', 'admin'],
                       help='客戶端類型 (預設: user)')
    parser.add_argument('-e', '--num-events', type=int, default=5,
                       help='每個客戶端發送的事件數 (預設: 5)')
    parser.add_argument('--event-interval', type=float,
                       help='事件之間的間隔（秒）')
    parser.add_argument('--connection-delay', nargs=2, type=float, metavar=('MIN', 'MAX'),
                       help='連接之間的延遲範圍（秒）')
    parser.add_argument('--timeout', type=int, default=10,
                       help='連接逾時時間（秒）(預設: 10)')
    
    args = parser.parse_args()
    
    # 驗證參數
    if args.type == 'user' and not args.activity_id:
        parser.error("使用者客戶端需要指定活動 ID (-a/--activity-id)")
    
    # 解析延遲範圍
    connection_delay_range = None
    if args.connection_delay:
        connection_delay_range = (args.connection_delay[0], args.connection_delay[1])
    
    # 確保 URL 不包含尾部斜線
    server_url = args.url.rstrip('/')
    
    # 執行測試
    result = run_socket_load_test(
        server_url=server_url,
        num_clients=args.num_clients,
        concurrency=args.concurrency,
        activity_id=args.activity_id,
        client_type=args.type,
        num_events_per_client=args.num_events,
        event_interval=args.event_interval,
        connection_delay_range=connection_delay_range
    )
    
    # 顯示結果
    print_statistics(result)


if __name__ == '__main__':
    main()

