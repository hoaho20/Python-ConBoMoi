"""Module cung cấp giao diện người dùng PyQt5 và lớp AutomationWorker cho ứng dụng tự động hóa."""
import itertools
import queue
import random
import sys
import os
import time
import json
import multiprocessing
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union, Callable
import psutil

from PyQt5.QtWidgets import (
   QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
   QPushButton, QLabel, QSpinBox, QComboBox, QTextEdit, QProgressBar,
   QFileDialog, QMessageBox, QTabWidget, QGroupBox, QRadioButton,
   QCheckBox, QLineEdit, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QObject, Qt
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QColor, QPalette

# Import các module cần thiết
from browser_automation import load_proxies, load_data, load_acc_amz, cleanup_browser_processes, worker_process

# Đảm bảo đường dẫn đúng cho pyproxy_manager
try:
   from pyproxy_manager import PyProxyManager
except ImportError:
   # Nếu không tìm thấy, thử thêm thư mục hiện tại vào sys.path
   sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
   try:
       from pyproxy_manager import PyProxyManager
   except ImportError:
       # Nếu vẫn không tìm thấy, tạo một lớp giả
       class PyProxyManager:
           def __init__(self, access_key="", access_secret=""):
               self.access_key = access_key
               self.access_secret = access_secret
               self.token = ""
               self.token_expire_time = 0
           
           def set_access_key(self, access_key, access_secret):
               self.access_key = access_key
               self.access_secret = access_secret
           
           def get_access_token(self):
               return False, "PyProxyManager không được cài đặt"
           
           def add_ip_whitelist(self, white_type="other", mark=""):
               return False, "PyProxyManager không được cài đặt"
           
           def update_proxy_file(self):
               return False, "PyProxyManager không được cài đặt"
           
           def get_remaining_traffic(self):
               return False, {"error": "PyProxyManager không được cài đặt"}
           
           def get_daily_traffic(self):
               return False, {"error": "PyProxyManager không được cài đặt"}
           
           def get_proxy_host(self):
               return False, "PyProxyManager không được cài đặt"
           
           def get_purchase_history(self, size=3):
               return False, {"error": "PyProxyManager không được cài đặt"}

# Thêm lớp LazyDataLoader để quản lý việc tải dữ liệu theo cách lazy loading
import atexit
import subprocess

class LazyDataLoader:
    """Quản lý việc tải dữ liệu theo cách lazy loading để tránh tải lại liên tục dữ liệu lớn"""
    
    def __init__(self):
        self.proxies = []
        self.data_items = []
        self.acc_items = []
        self.last_load_time = {
            "proxies": 0,
            "data": 0,
            "acc": 0
        }
        self.cache_valid_time = 300  # Cache có hiệu lực trong 5 phút
        
    def load_proxies(self, force=False):
        """Tải danh sách proxy với caching"""
        current_time = time.time()
        if force or not self.proxies or (current_time - self.last_load_time["proxies"] > self.cache_valid_time):
            self.proxies = load_proxies()
            self.last_load_time["proxies"] = current_time
        return self.proxies
    
    def load_data(self, force=False):
        """Tải dữ liệu với caching"""
        current_time = time.time()
        if force or not self.data_items or (current_time - self.last_load_time["data"] > self.cache_valid_time):
            self.data_items = load_data()
            self.last_load_time["data"] = current_time
        return self.data_items
    
    def load_acc(self, force=False):
        """Tải tài khoản với caching"""
        current_time = time.time()
        if force or not self.acc_items or (current_time - self.last_load_time["acc"] > self.cache_valid_time):
            self.acc_items = load_acc_amz()
            self.last_load_time["acc"] = current_time
        return self.acc_items
    
    def clear_cache(self):
        """Xóa tất cả dữ liệu đã cache"""
        self.proxies = []
        self.data_items = []
        self.acc_items = []
        self.last_load_time = {
            "proxies": 0,
            "data": 0,
            "acc": 0
        }
        
LOCK = multiprocessing.Lock()
        
class AutomationWorker:
   """
   Lớp quản lý các worker process cho tự động hóa trình duyệt.
   """
   
   def __init__(
       self, 
       signals: Any, 
       process_count: int, 
       headless: str,
       option: int = 1,  # Add option parameter
       proxies: Optional[List[str]] = None, 
       data: Optional[List[str]] = None, 
       acc: Optional[List[str]] = None
   ):
       """
       Khởi tạo AutomationWorker.
       
       Args:
           signals: Đối tượng signals từ PyQt5 để gửi thông báo
           process_count: Số lượng tiến trình cần chạy
           headless: Chế độ headless (không hiển thị giao diện)
           proxies: Danh sách các proxy (tùy chọn)
           data: Danh sách các mục dữ liệu (tùy chọn)
           acc: Danh sách các tài khoản (tùy chọn)
       """
       self.signals = signals
       self.process_count = process_count
       self.headless = headless
       self.option = option  # Store option
       self.proxies = proxies
       self.data = data
       self.acc = acc
       self.running = False
       self.total = 0
       self.processed = 0
       self.live = 0
       self.dead = 0
       self.processes = []  # Danh sách các process
       self.processed_data = []  # Danh sách dữ liệu đã xử lý
       self.process_data_map = {}
       
   def _drain_results(self, result_queue):
        """Lấy hết các kết quả có sẵn, cập nhật counters và emit progress."""
        while True:
            try:
                status, message, success = result_queue.get(block=False)
            except queue.Empty:
                break
            if status == "completed":
                count = len(message) if isinstance(message, (list, tuple)) else 1
                self.processed += count
                if success:
                    self.live += count
                else:
                    self.dead += count
                self.signals.progress.emit(
                    self.total,
                    self.processed,
                    self.live,
                    self.dead
                )
                self.signals.update_textboxes.emit()
                self.signals.log.emit(
                    f"Hoàn thành: {message} (success={success})", False
                )    
                
   def run(self) -> None:
       """Chạy quy trình tự động hóa với khởi động Chrome đồng thời."""
       self.running = True

       proxies = self.proxies if self.proxies else load_proxies()
       acc_amzs = self.acc if self.acc else load_acc_amz()
       # Nếu option == 1, cần data; nếu option == 2, bỏ qua data
       data_items = self.data if self.data is not None else load_data() if self.option == 1 else []

       if not proxies:
           self.signals.log.emit("No proxies found. Running without proxy.", True)
           proxies = [""]

       if not acc_amzs:
           self.signals.log.emit("No accounts found. Cannot continue.", True)
           self.signals.finished.emit()
           return

       if self.option == 1 and not data_items:  # Chỉ kiểm tra data nếu option == 1
           self.signals.log.emit("No data found. Cannot continue.", True)
           self.signals.finished.emit()
           return

       self.stop_all_processes()

       manager = multiprocessing.Manager()
       proxy_queue = manager.Queue()
       result_queue = manager.Queue()
       # thêm mảng dữ liệu và acc vào queue
       data_queue = manager.Queue()
       acc_queue = manager.Queue()

       for proxy in proxies:
           proxy_queue.put(proxy)

       # Chia dữ liệu thành các phần nhỏ để chia cho các process
       num_per_thread_data_1 = 30  #kiểm tra 6 thẻ 1 lúc option 1
       num_per_thread_acc_1 = 10 #kiểm tra 1 tài khoản 1 lúc option 1
       num_per_thread_2 = 3 #kiểm tra 3 tài khoản 1 lúc option 2
        
       if self.option == 1 or self.option == 4:        
           data_chunks = [data_items[i:i + num_per_thread_data_1] for i in range(0, len(data_items), num_per_thread_data_1)]
           acc_chunks = [acc_amzs[i:i + num_per_thread_acc_1] for i in range(0, len(acc_amzs), num_per_thread_acc_1)]
           random.shuffle(acc_chunks)
           # Set total to the total number of data items for option 1
           self.total = len(data_items)
           effective_processes = min(self.process_count, len(data_chunks))
           for chunk in data_chunks:
                data_queue.put(chunk)

       elif self.option == 2 or self.option == 3:
           acc_chunks = [acc_amzs[i:i + num_per_thread_2] for i in range(0, len(acc_amzs), num_per_thread_2)]
           data_chunks = [[]] * self.process_count
           # Set total to the total number of accounts for option 2
           self.total = len(acc_amzs)
           effective_processes = min(self.process_count, len(acc_chunks)) 

       if self.option == 1 or self.option == 4:
           total_process = len(data_chunks)
           self.signals.log.emit(f'Tổng số tiến trình cần chạy: {total_process}', False)
       else:
           total_process = len(acc_chunks)
           self.signals.log.emit(f'Tổng số tiến trình cần chạy: {total_process}', False)
                       
       for chunk in acc_chunks:
           acc_queue.put(chunk)

       if effective_processes < self.process_count:
           self.process_count = effective_processes 

       self.processed = self.live = self.dead = 0
       self.signals.progress.emit(self.total, 0, 0, 0)

       for i in range(total_process):
                if not self.running:
                    self.signals.log.emit("Đã dừng tạo tiến trình mới theo yêu cầu", False)
                    break

                while len(self.processes) >= self.process_count and self.running:
                    for p in self.processes:
                        if not p.is_alive():
                            p.join()
                            self.processes.remove(p)
                    time.sleep(0.1)
                
                if not self.running:
                    break 
                try:
                    if self.option == 1 or self.option == 4:
                        data_item = data_queue.get_nowait()
                    else:
                        data_item = []
                except queue.Empty:
                    break 
                if self.option == 1 or self.option == 4:
                    self.process_data_map[i] = data_item
                p = multiprocessing.Process(target=worker_process, args=(i, data_item, proxy_queue, acc_queue, result_queue, self.headless, self.option, LOCK))
                self.processes.append(p)
                p.start()
                self._drain_results(result_queue)      
                           
       while any(p.is_alive() for p in self.processes) or not result_queue.empty():
            self._drain_results(result_queue)
            time.sleep(0.1) 
            
       for p in self.processes:
                p.join()
              
       
       self.signals.log.emit(
            f"All processes completed. Processed {self.processed}/{self.total} "
            f"items. Success: {self.live}, Failed: {self.dead}", False
        )
       self.signals.log.emit("All data processed or automation stopped.", False)
       self.signals.finished.emit()
       self.running = False

   def stop_all_processes(self) -> None:
        """Dừng và xóa tất cả các process."""
        self.signals.log.emit("Đóng và xóa tất cả process...", False)

        killed_data = []

        if self.option == 1 or self.option == 4:
            for i, p in enumerate(self.processes):
                if p.is_alive() and i in self.process_data_map:
                    data_chunk = self.process_data_map[i]
                    if data_chunk:
                        killed_data.extend(data_chunk)
                        self.signals.log.emit(f"Đã thu thập {len(data_chunk)} mục dữ liệu từ process {i}", False)
        
        # Kết thúc tất cả các process
        for p in self.processes:
            if p.is_alive():
                try:
                    p.terminate()
                    self.signals.log.emit(f"Đã kết thúc process {p.pid}", False)
                except Exception as e:
                    self.signals.log.emit(f"Lỗi khi kết thúc process: {str(e)}", True)
       
       # Đợi tất cả process kết thúc
        for p in self.processes:
           try:
               p.join(timeout=10)
               if p.is_alive():
                   p.kill()
                   self.signals.log.emit(f"Đã buộc kết thúc process {p.pid}", False)
           except Exception as e:
               self.signals.log.emit(f"Lỗi khi join process: {str(e)}", True)
        if (self.option == 1 or self.option == 4) and killed_data:
            try:
                with open("output/unk.txt", 'a+', encoding='utf-8') as f:
                    for item in killed_data:
                        f.write(f"\n{item.strip()}")
                
                self.signals.log.emit(f"Đã ghi {len(killed_data)} mục dữ liệu từ các tiến trình bị kill vào unk_file", False)
            except Exception as e:
                self.signals.log.emit(f"Lỗi khi ghi dữ liệu vào file unk.txt: {str(e)}", True)
                
       # Dọn dẹp các process Chrome còn sót lại
        cleanup_browser_processes(option = self.option)
        self.signals.log.emit("Đã dọn dẹp tất cả process Chrome", False)

       # Kill chromedriver nếu còn chạy
        for proc in psutil.process_iter(attrs=["pid", "name"]):
           try:
               if "chromedriver" in proc.info["name"].lower():
                   proc.kill()
                   self.signals.log.emit(f"Đã buộc kết thúc chromedriver (PID: {proc.info['pid']})", False)
           except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
               pass

        self.signals.log.emit("Đã dọn dẹp chromedriver", False)

       # Thêm: Dọn dẹp các thư mục profile còn sót lại
        self.cleanup_leftover_profiles()

       # Xóa danh sách process
        self.processes = []   

   def cleanup_leftover_profiles(self) -> None:
        """Dọn dẹp các thư mục profile còn sót lại."""
        try:
            self.signals.log.emit(f"Dọn dẹp các thư mục profile còn sót lại", False)
            cleanup_browser_processes(option=self.option, cleanup_profiles=True)
            self.signals.log.emit("Đã dọn dẹp các thư mục profile", False)
        except Exception as e:
            self.signals.log.emit(f"Lỗi khi dọn dẹp các thư mục profile: {str(e)}", True)

   def stop(self) -> None:
       """Dừng quá trình tự động hóa."""
       if not self.running:
           return
           
       self.running = False
       self.stop_all_processes()
       self.signals.log.emit("Đã dừng tự động hóa", False)

class WorkerSignals(QObject):
   """Tín hiệu cho worker thread"""
   log = pyqtSignal(str, bool)  # message, is_error
   progress = pyqtSignal(int, int, int, int)  # total, processed, live, dead
   finished = pyqtSignal()
   update_textboxes = pyqtSignal()  # New signal for updating textboxes

class WorkerThread(QThread):
   """Thread để chạy tự động hóa"""
   def __init__(self, signals, process_count, headless, option=1, proxies=None, data=None, acc=None):
       super().__init__()
       self.signals = signals
       self.process_count = process_count
       self.headless = headless
       self.option = option  # Add option parameter
       self.proxies = proxies
       self.data = data
       self.acc = acc
       self.worker = AutomationWorker(signals, process_count, headless, option, proxies, data, acc)
       
   def run(self):
       """Chạy worker"""
       try:
           self.worker.run()
       except Exception as e:
           self.signals.log.emit(f"Lỗi trong worker thread: {str(e)}", True)
       finally:
           self.signals.finished.emit()
           
   def stop(self):
       """Dừng worker"""
       if self.worker:
           self.worker.stop()

class MainWindow(QMainWindow):
   """Cửa sổ chính của ứng dụng"""

   def force_clean(self):
       """Xóa file rác trên máy tính"""
       # Hiển thị hộp thoại cảnh báo
       warning_message = "Warning: This operation will delete the following temporary files:\n\n" \
                         "- Temporary files in Temp folder\n" \
                         "- Recent places files\n" \
                         "- Cache files\n" \
                         "- Files identified by Disk Cleanup\n" \
                         "- Files in Recycle Bin\n\n" \
                         "Are you sure you want to continue?"
       
       reply = QMessageBox.warning(self, "Cảnh báo", warning_message, 
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
       
       if reply == QMessageBox.No:
           return
       
       self.log_message("Starting cleanup of temporary files...", False)
       
       try:
           import tempfile
           import shutil
           import os
           import subprocess
           from pathlib import Path
           
           # 1. Xóa file trong thư mục Temp
           temp_dir = tempfile.gettempdir()
           self.log_message(f"Deleting files in Temp folder: {temp_dir}", False)
           try:
               for item in os.listdir(temp_dir):
                   item_path = os.path.join(temp_dir, item)
                   try:
                       if os.path.isfile(item_path):
                           os.unlink(item_path)
                       elif os.path.isdir(item_path):
                           shutil.rmtree(item_path, ignore_errors=True)
                   except Exception as e:
                       self.log_message(f"Không thể xóa {item_path}: {e}", True)
               self.log_message("Temp folder files deleted", False)
           except Exception as e:
               self.log_message(f"Error deleting files in Temp folder: {e}", True)
           
           # 2. Xóa file trong Recent places
           try:
               recent_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Recent")
               if os.path.exists(recent_dir):
                   self.log_message(f"Deleting files in Recent places: {recent_dir}", False)
                   for item in os.listdir(recent_dir):
                       item_path = os.path.join(recent_dir, item)
                       try:
                           if os.path.isfile(item_path):
                               os.unlink(item_path)
                       except Exception as e:
                           self.log_message(f"Không thể xóa {item_path}: {e}", True)
                   self.log_message("Recent places files deleted", False)
           except Exception as e:
               self.log_message(f"Error deleting files in Recent places: {e}", True)
           
           # 3. Xóa file trong bộ nhớ Cache
           try:
               cache_dirs = [
                   os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "INetCache"),
                   os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "WebCache")
               ]
               
               for cache_dir in cache_dirs:
                   if os.path.exists(cache_dir):
                       self.log_message(f"Deleting files in Cache: {cache_dir}", False)
                       for item in os.listdir(cache_dir):
                           item_path = os.path.join(cache_dir, item)
                           try:
                               if os.path.isfile(item_path):
                                   os.unlink(item_path)
                               elif os.path.isdir(item_path):
                                   shutil.rmtree(item_path, ignore_errors=True)
                           except Exception as e:
                               self.log_message(f"Không thể xóa {item_path}: {e}", True)
               self.log_message("Cache files deleted", False)
           except Exception as e:
               self.log_message(f"Error deleting files in Cache: {e}", True)
           
           # 4. Xóa file bằng Disk Cleanup (chỉ hoạt động trên Windows)
           if os.name == 'nt':
               try:
                   self.log_message("Running Disk Cleanup...", False)
                   subprocess.run(["cleanmgr", "/sagerun:1"], shell=True, check=False)
                   self.log_message("Disk Cleanup completed", False)
               except Exception as e:
                   self.log_message(f"Error running Disk Cleanup: {e}", True)
           
           # 5. Xóa file trong Recycle Bin (chỉ hoạt động trên Windows)
           if os.name == 'nt':
               try:
                   self.log_message("Emptying Recycle Bin...", False)
                   subprocess.run(["powershell", "-Command", "Clear-RecycleBin", "-Force", "-ErrorAction", "SilentlyContinue"], 
                                 shell=True, check=False)
                   self.log_message("Recycle Bin emptied", False)
               except Exception as e:
                   self.log_message(f"Error emptying Recycle Bin: {e}", True)
           
           self.log_message("Temporary files cleanup completed!", False)
           QMessageBox.information(self, "Completed", "Temporary files cleanup completed!")
           
       except Exception as e:
           self.log_message(f"Error during temporary files cleanup: {e}", True)
           QMessageBox.critical(self, "Error", f"An error occurred during temporary files cleanup: {e}")

   def __init__(self):
       super().__init__()
       self.setWindowTitle("Con Bọ Mới")
       self.setMinimumSize(800, 600)
       
       # Create status bar
       self.statusBar().showMessage("Initializing application...")
       
       # Dọn dẹp các thư mục profile còn sót lại từ lần chạy trước
       self.cleanup_profiles_on_startup()
       
       # Thiết lập giao diện
       self.setup_ui()
       
       # Khởi tạo worker thread
       self.worker_thread = None
       self.worker_signals = WorkerSignals()
       self.worker_signals.log.connect(self.log_message)
       self.worker_signals.progress.connect(self.update_progress)
       self.worker_signals.finished.connect(self.on_worker_finished)
       self.worker_signals.update_textboxes.connect(self.update_textboxes_from_files)
       
       # Khởi tạo PyProxy Manager
       self.pyproxy_manager = PyProxyManager()
       self.proxy_update_timer = QTimer(self)
       self.proxy_update_timer.timeout.connect(self.check_proxy_update)
       self.proxy_update_timer.start(30 * 60 * 1000)  # Kiểm tra mỗi 30 phút
       
       # Khởi tạo timer cập nhật thông tin PyProxy
       self.pyproxy_info_timer = QTimer(self)
       self.pyproxy_info_timer.timeout.connect(self.update_pyproxy_info)
       self.pyproxy_info_timer.start(5 * 60 * 1000)  # Cập nhật mỗi 5 phút
       
       # Initialize lazy data loader
       self.data_loader = LazyDataLoader()

       # Initialize network usage timer
       self.network_usage_timer = QTimer(self)
       self.network_usage_timer.timeout.connect(self.update_network_usage)
       self.network_usage_timer.start(5000)  # Thay đổi từ 2000 (2 giây) thành 5000 (5 giây)

       # Initialize file monitoring timer for auto-refresh
       self.file_monitor_timer = QTimer(self)
       self.file_monitor_timer.timeout.connect(self.check_files_for_changes)
       self.file_monitor_timer.start(10000)  # Check files every 10 seconds
       
       # Track file modification times
       self.file_mod_times = {
           "proxies": 0,
           "data": 0,
           "acc": 0
       }

       # PyProxy enabled flag (default to False)
       self.pyproxy_enabled = False
       
       # Register cleanup function to run on exit
       atexit.register(self.cleanup_on_exit)
       
       # Schedule data loading and proxy update after UI is shown
       QTimer.singleShot(100, self.initial_setup)

       # Thêm biến để theo dõi log trùng lặp
       self.last_log_message = ""
       self.duplicate_log_count = 0

   def initial_setup(self):
       """Perform initial setup tasks after UI is shown"""
       self.statusBar().showMessage("Loading data...")
       self.log_message("Starting initial application setup...", False)
       
       # Tải dữ liệu ban đầu
       self.load_initial_data_with_progress()
       
       # Check if PyProxy should be enabled based on saved settings
       self.load_pyproxy_settings()
       
       # Tự động cập nhật proxy sau khi khởi động (only if PyProxy is enabled)
       if self.pyproxy_enabled:
           QTimer.singleShot(1000, self.auto_update_proxy)

   def load_pyproxy_settings(self):
       """Load PyProxy settings from config file"""
       config_file = Path(__file__).resolve().parent / "pyproxy_config.json"
       if config_file.exists():
           try:
               with open(config_file, "r", encoding="utf-8") as f:
                   config = json.load(f)
                   self.pyproxy_enabled = config.get("enabled", False)
                   self.use_pyproxy_checkbox.setChecked(self.pyproxy_enabled)
                   
                   if self.pyproxy_enabled:
                       access_key = config.get("access_key", "")
                       access_secret = config.get("access_secret", "")
                       
                       if access_key and access_secret:
                           self.access_key_input.setText(access_key)
                           self.access_secret_input.setText(access_secret)
                           self.pyproxy_manager.set_access_key(access_key, access_secret)
                           self.log_message("Loaded PyProxy information from config file", False)
                   
                   self.update_pyproxy_ui_state()
           except Exception as e:
               self.log_message(f"Error loading PyProxy settings: {str(e)}", True)

   def closeEvent(self, event):
        """Handle application close event"""
        self.log_message("Closing application and cleaning up...", False)
        
        # Stop any running automation and wait for it to complete
        if self.worker_thread and self.worker_thread.isRunning():
            self.log_message("Stopping running automation before exit...", False)
            self.statusBar().showMessage("Stopping processes before exit...")
            
            # Stop the worker thread
            self.worker_thread.stop()
            
            # Wait for the worker to finish (with timeout)
            wait_start = time.time()
            while self.worker_thread.isRunning() and time.time() - wait_start < 30:  # 30 second timeout
                QApplication.processEvents()  # Keep UI responsive
                time.sleep(0.1)
            
            if self.worker_thread.isRunning():
                self.log_message("Worker thread did not stop gracefully, forcing termination", True)
        
        # Save any pending changes to files
        self.save_data()
        
        self.log_message("All automation processes stopped", False)
        self.statusBar().showMessage("Running cleanup script...")
        
        # Run the cleanup directly instead of using the script
        try:
            self.log_message("Running cleanup process...", False)
            cleanup_browser_processes(cleanup_profiles=True)
            self.log_message("Cleanup completed successfully", False)
        except Exception as e:
            self.log_message(f"Error during cleanup: {str(e)}", True)
        
        self.log_message("Application shutdown complete", False)
        
        # Accept the close event
        event.accept()

   def cleanup_on_exit(self):
        """Cleanup function that runs when the application exits"""
        try:
            # This is a fallback in case closeEvent doesn't run
            cleanup_browser_processes(cleanup_profiles=True)
        except:
            pass  # Silently fail on exit

   def cleanup_profiles_on_startup(self):
        """Dọn dẹp các thư mục profile còn sót lại từ lần chạy trước."""
        try:
            # Sử dụng hàm tích hợp từ browser_automation
            from browser_automation import cleanup_browser_processes
            cleanup_browser_processes(cleanup_profiles=True)
            print("Đã dọn dẹp các thư mục profile và process Chrome còn sót lại")
        except Exception as e:
            print(f"Lỗi khi dọn dẹp các thư mục profile: {e}")
   
   def auto_update_proxy(self):
       """Tự động lấy IP và cập nhật proxy khi khởi động"""
       if not self.pyproxy_enabled:
           self.log_message("PyProxy is disabled. Skipping automatic proxy update.", False)
           return
           
       self.statusBar().showMessage("Updating proxies...")
       self.log_message("Starting automatic proxy update...", False)
       
       # Kiểm tra xem đã có access key và access secret chưa
       if not self.pyproxy_manager.access_key or not self.pyproxy_manager.access_secret:
           # Thử đọc từ file cấu hình
           config_file = Path(__file__).resolve().parent / "pyproxy_config.json"
           if config_file.exists():
               try:
                   with open(config_file, "r", encoding="utf-8") as f:
                       config = json.load(f)
                       access_key = config.get("access_key", "")
                       access_secret = config.get("access_secret", "")
                       
                       if access_key and access_secret:
                           self.access_key_input.setText(access_key)
                           self.access_secret_input.setText(access_secret)
                           self.pyproxy_manager.set_access_key(access_key, access_secret)
                           self.log_message("Loaded PyProxy information from config file", False)
                       else:
                           self.log_message("Config file exists but does not contain valid access key", True)
                           self.create_sample_config_file(config_file)
                           return
               except Exception as e:
                   self.log_message(f"Error reading PyProxy config file: {str(e)}", True)
                   self.create_sample_config_file(config_file)
                   return
           else:
               self.log_message("PyProxy config file not found. Please enter Access Key and Access Secret in the Settings tab.", True)
               self.create_sample_config_file(config_file)
               return
       
       # Lấy token PyProxy
       try:
           success, message = self.pyproxy_manager.get_access_token()
           if not success:
               self.log_message(f"Cannot get PyProxy token: {message}", True)
               return
       except Exception as e:
           self.log_message(f"Error getting PyProxy token: {str(e)}", True)
           return
       
       # Tự động thêm IP vào whitelist
       try:
           success, message = self.pyproxy_manager.add_ip_whitelist()
           if success:
               self.log_message(message, False)
           else:
               self.log_message(f"Error adding IP to whitelist: {message}", True)
       except Exception as e:
           self.log_message(f"Error adding IP to whitelist: {str(e)}", True)
       
       # Cập nhật danh sách proxy
       try:
           success, message = self.pyproxy_manager.update_proxy_file()
           if success:
               self.log_message(message, False)
               # Tải lại danh sách proxy vào UI
               proxies = load_proxies()
               if proxies:
                   self.proxy_text.setText("\n".join(proxies))
                   self.log_message(f"Loaded {len(proxies)} proxies to interface", False)
               else:
                   self.log_message("No proxies loaded", True)
           else:
               self.log_message(f"Error updating proxies: {message}", True)
       except Exception as e:
           self.log_message(f"Error updating proxies: {str(e)}", True)
       
       # Cập nhật thông tin PyProxy
       try:
           self.update_pyproxy_info()
       except Exception as e:
           self.log_message(f"Error updating PyProxy info: {str(e)}", True)
       
       self.log_message("Automatic proxy update completed", False)
       self.statusBar().showMessage("Proxy update completed", 3000)

   def create_sample_config_file(self, config_file_path):
       """Tạo file cấu hình mẫu nếu không tồn tại"""
       try:
           sample_config = {
               "access_key": "",
               "access_secret": "",
               "enabled": False,
               "last_updated": time.time(),
               "note": "Vui lòng nhập Access Key và Access Secret của bạn trong tab Cài đặt, sau đó nhấn 'Lưu Access Key'"
           }
           
           # Đảm bảo thư mục cha tồn tại
           os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
           
           with open(config_file_path, "w", encoding="utf-8") as f:
               json.dump(sample_config, f, indent=4)
               
           self.log_message(f"Created sample config file at {config_file_path}", False)
           self.log_message("Please enter Access Key and Access Secret in the Settings tab, then click 'Save Access Key'", False)
       except Exception as e:
           self.log_message(f"Error creating sample config file: {str(e)}", True)

   def setup_ui(self):
       """Thiết lập giao diện người dùng"""
       # Widget chính
       central_widget = QWidget()
       self.setCentralWidget(central_widget)
       
       # Layout chính
       main_layout = QVBoxLayout(central_widget)
       
       # Tạo tabs
       tabs = QTabWidget()
       main_layout.addWidget(tabs)
       
       # Tab chính
       main_tab = QWidget()
       tabs.addTab(main_tab, "Main")
       
       # Layout cho tab chính
       main_tab_layout = QVBoxLayout(main_tab)
       
       # Phần cấu hình
       config_group = QGroupBox("Configuration")
       config_layout = QHBoxLayout(config_group)
       
       # Số lượng tiến trình
       process_layout = QVBoxLayout()
       process_label = QLabel("Number of processes:")
       self.process_spin = QSpinBox()
       self.process_spin.setRange(1, 500)
       self.process_spin.setValue(1)
       process_layout.addWidget(process_label)
       process_layout.addWidget(self.process_spin)
       config_layout.addLayout(process_layout)
       
       # Chế độ headless
       headless_layout = QVBoxLayout()
       headless_label = QLabel("Headless mode:")
       self.headless_combo = QComboBox()
       self.headless_combo.addItems(["No (show browser)", "Yes (hidden)"])
       headless_layout.addWidget(headless_label)
       headless_layout.addWidget(self.headless_combo)
       config_layout.addLayout(headless_layout)
       
       # Add option selection
       option_layout = QVBoxLayout()
       option_label = QLabel("Automation Option:")
       self.option_combo = QComboBox()
       self.option_combo.addItems(["Check CCN AMZ US", "Check Live Account AMZ US", "Check Live Account AMZ JP", "Check CCN AMZ JP"])
       option_layout.addWidget(option_label)
       option_layout.addWidget(self.option_combo)
       config_layout.addLayout(option_layout)
       
       # Thêm phần cấu hình vào layout chính
       main_tab_layout.addWidget(config_group)
       
       # Phần dữ liệu
       data_group = QGroupBox("Data")
       data_layout = QHBoxLayout(data_group)
       
       # Proxy
       proxy_layout = QVBoxLayout()
       proxy_header = QHBoxLayout()
       proxy_label = QLabel("Proxy:")
       self.proxy_count_label = QLabel("(0)")  # Thêm label hiển thị số lượng proxy
       proxy_upload_btn = QPushButton("Upload")
       proxy_upload_btn.clicked.connect(lambda: self.upload_file("proxy"))
       proxy_header.addWidget(proxy_label)
       proxy_header.addWidget(self.proxy_count_label)  # Thêm label vào layout
       proxy_header.addStretch()
       proxy_header.addWidget(proxy_upload_btn)
       self.proxy_text = QTextEdit()
       self.proxy_text.setPlaceholderText("One proxy per line")
       self.proxy_text.textChanged.connect(self.update_data_counts)  # Kết nối sự kiện textChanged
       proxy_layout.addLayout(proxy_header)
       proxy_layout.addWidget(self.proxy_text)
       data_layout.addLayout(proxy_layout)
       
       # Dữ liệu
       data_input_layout = QVBoxLayout()
       data_header = QHBoxLayout()
       data_label = QLabel("Data:")
       self.data_count_label = QLabel("(0)")  # Thêm label hiển thị số lượng data
       data_upload_btn = QPushButton("Upload")
       data_upload_btn.clicked.connect(lambda: self.upload_file("data"))
       data_header.addWidget(data_label)
       data_header.addWidget(self.data_count_label)  # Thêm label vào layout
       data_header.addStretch()
       data_header.addWidget(data_upload_btn)
       self.data_text = QTextEdit()
       self.data_text.setPlaceholderText("One data item per line")
       self.data_text.textChanged.connect(self.update_data_counts)  # Kết nối sự kiện textChanged
       data_input_layout.addLayout(data_header)
       data_input_layout.addWidget(self.data_text)
       data_layout.addLayout(data_input_layout)
       
       # Tài khoản
       acc_layout = QVBoxLayout()
       acc_header = QHBoxLayout()
       acc_label = QLabel("Accounts:")
       self.acc_count_label = QLabel("(0)")  # Thêm label hiển thị số lượng account
       acc_upload_btn = QPushButton("Upload")
       acc_upload_btn.clicked.connect(lambda: self.upload_file("acc"))
       acc_header.addWidget(acc_label)
       acc_header.addWidget(self.acc_count_label)  # Thêm label vào layout
       acc_header.addStretch()
       acc_header.addWidget(acc_upload_btn)
       self.acc_text = QTextEdit()
       self.acc_text.setPlaceholderText("One account per line")
       self.acc_text.textChanged.connect(self.update_data_counts)  # Kết nối sự kiện textChanged
       acc_layout.addLayout(acc_header)
       acc_layout.addWidget(self.acc_text)
       data_layout.addLayout(acc_layout)
       
       # Thêm phần dữ liệu vào layout chính
       main_tab_layout.addWidget(data_group)
       
       # Phần điều khiển
       control_layout = QHBoxLayout()
       
       # Nút bắt đầu
       self.start_button = QPushButton("Start")
       self.start_button.clicked.connect(self.start_automation)
       control_layout.addWidget(self.start_button)
       
       # Nút dừng
       self.stop_button = QPushButton("Stop")
       self.stop_button.clicked.connect(self.stop_automation)
       self.stop_button.setEnabled(False)
       control_layout.addWidget(self.stop_button)
       
       # Nút Force Clean
       self.clean_button = QPushButton("Force Clean")
       self.clean_button.clicked.connect(self.force_clean)
       control_layout.addWidget(self.clean_button)
       
       # Thêm phần điều khiển vào layout chính
       main_tab_layout.addLayout(control_layout)
       
       # Phần tiến trình
       progress_group = QGroupBox("Progress")
       progress_layout = QVBoxLayout(progress_group)
       
       # Thanh tiến trình
       self.progress_bar = QProgressBar()
       self.progress_bar.setRange(0, 100)
       self.progress_bar.setValue(0)
       progress_layout.addWidget(self.progress_bar)
       
       # Nhãn tiến trình
       self.progress_label = QLabel("0/0 accounts processed (0 successful, 0 failed)")
       progress_layout.addWidget(self.progress_label)
       
       # Thêm phần tiến trình vào layout chính
       main_tab_layout.addWidget(progress_group)
       
       # Phần log
       log_group = QGroupBox("Log")
       log_layout = QVBoxLayout(log_group)
       
       # Text log
       self.log_text = QTextEdit()
       self.log_text.setReadOnly(True)
       log_layout.addWidget(self.log_text)

       # Network traffic section
       network_group = QGroupBox("Network Traffic")
       network_layout = QVBoxLayout(network_group)

       # Network traffic progress bar
       network_traffic_layout = QHBoxLayout()
       network_traffic_label = QLabel("Current network usage:")
       self.network_traffic_bar = QProgressBar()
       self.network_traffic_bar.setRange(0, 100)
       self.network_traffic_bar.setValue(0)
       self.network_traffic_bar.setAlignment(Qt.AlignCenter)
       self.network_traffic_bar.setFormat("%p%")
       self.network_traffic_info = QLabel("0 Mbps")
       network_traffic_layout.addWidget(network_traffic_label)
       network_traffic_layout.addWidget(self.network_traffic_bar)
       network_traffic_layout.addWidget(self.network_traffic_info)
       network_layout.addLayout(network_traffic_layout)

       # Recommended processes section
       recommended_layout = QHBoxLayout()
       recommended_label = QLabel("Recommended processes:")
       self.recommended_processes_label = QLabel("Calculating...")
       recommended_layout.addWidget(recommended_label)
       recommended_layout.addWidget(self.recommended_processes_label)
       recommended_layout.addStretch()
       network_layout.addLayout(recommended_layout)

       # Add network group to main layout
       main_tab_layout.addWidget(network_group)
       
       # Thêm phần log vào layout chính
       main_tab_layout.addWidget(log_group)
       
       # Tab cài đặt
       settings_tab = QWidget()
       tabs.addTab(settings_tab, "Settings")
       
       # Layout cho tab cài đặt
       settings_layout = QVBoxLayout(settings_tab)
       
       # Phần PyProxy
       pyproxy_group = QGroupBox("PyProxy Settings")
       pyproxy_layout = QVBoxLayout(pyproxy_group)
       
       # Enable/Disable PyProxy
       pyproxy_enable_layout = QHBoxLayout()
       self.use_pyproxy_checkbox = QCheckBox("Enable PyProxy")
       self.use_pyproxy_checkbox.stateChanged.connect(self.toggle_pyproxy)
       pyproxy_enable_layout.addWidget(self.use_pyproxy_checkbox)
       pyproxy_enable_layout.addStretch()
       pyproxy_layout.addLayout(pyproxy_enable_layout)
       
       # Access Key
       access_key_layout = QHBoxLayout()
       access_key_label = QLabel("PyProxy Access Key:")
       self.access_key_input = QLineEdit()
       self.access_key_input.setPlaceholderText("Enter PyProxy Access Key")
       self.access_key_input.setEchoMode(QLineEdit.Password)
       access_key_layout.addWidget(access_key_label)
       access_key_layout.addWidget(self.access_key_input)
       pyproxy_layout.addLayout(access_key_layout)
       
       # Access Secret
       access_secret_layout = QHBoxLayout()
       access_secret_label = QLabel("PyProxy Access Secret:")
       self.access_secret_input = QLineEdit()
       self.access_secret_input.setPlaceholderText("Enter PyProxy Access Secret")
       self.access_secret_input.setEchoMode(QLineEdit.Password)
       access_secret_layout.addWidget(access_secret_label)
       access_secret_layout.addWidget(self.access_secret_input)
       pyproxy_layout.addLayout(access_secret_layout)
       
       # Nút lưu access key và whitelist IP
       pyproxy_buttons_layout = QHBoxLayout()
       save_key_button = QPushButton("Save Access Key")
       save_key_button.clicked.connect(self.save_access_key)
       whitelist_button = QPushButton("Whitelist IP")
       whitelist_button.clicked.connect(self.whitelist_ip)
       update_proxy_button = QPushButton("Update Proxy")
       update_proxy_button.clicked.connect(self.update_proxy_list)
       pyproxy_buttons_layout.addWidget(save_key_button)
       pyproxy_buttons_layout.addWidget(whitelist_button)
       pyproxy_buttons_layout.addWidget(update_proxy_button)
       pyproxy_layout.addLayout(pyproxy_buttons_layout)
       
       # Thêm các thanh tiến trình cho thông tin PyProxy
       pyproxy_traffic_group = QGroupBox("PyProxy Traffic Info")
       pyproxy_traffic_layout = QVBoxLayout(pyproxy_traffic_group)
       
       # Thanh tiến trình cho traffic còn lại
       remaining_traffic_layout = QHBoxLayout()
       remaining_traffic_label = QLabel("Remaining traffic:")
       self.remaining_traffic_bar = QProgressBar()
       self.remaining_traffic_bar.setRange(0, 100)
       self.remaining_traffic_bar.setValue(0)
       self.remaining_traffic_info = QLabel("0 / 0 GB")
       remaining_traffic_layout.addWidget(remaining_traffic_label)
       remaining_traffic_layout.addWidget(self.remaining_traffic_bar)
       remaining_traffic_layout.addWidget(self.remaining_traffic_info)
       pyproxy_traffic_layout.addLayout(remaining_traffic_layout)
       
       # Thông tin thêm về PyProxy
       self.pyproxy_info_label = QLabel("PyProxy info: No data available")
       pyproxy_traffic_layout.addWidget(self.pyproxy_info_label)
       
       # Thêm nhóm traffic vào layout PyProxy
       pyproxy_layout.addWidget(pyproxy_traffic_group)
       
       # Thêm phần PyProxy vào tab cài đặt
       settings_layout.addWidget(pyproxy_group)
       
       # Auto-refresh settings
       auto_refresh_group = QGroupBox("Auto-Refresh Settings")
       auto_refresh_layout = QVBoxLayout(auto_refresh_group)
       
       # Enable auto-refresh
       self.auto_refresh_checkbox = QCheckBox("Enable auto-refresh of data from files")
       self.auto_refresh_checkbox.setChecked(True)
       auto_refresh_layout.addWidget(self.auto_refresh_checkbox)
       
       # Refresh interval
       refresh_interval_layout = QHBoxLayout()
       refresh_interval_label = QLabel("Refresh interval (seconds):")
       self.refresh_interval_spin = QSpinBox()
       self.refresh_interval_spin.setRange(5, 300)
       self.refresh_interval_spin.setValue(10)
       self.refresh_interval_spin.valueChanged.connect(self.update_refresh_interval)
       refresh_interval_layout.addWidget(refresh_interval_label)
       refresh_interval_layout.addWidget(self.refresh_interval_spin)
       auto_refresh_layout.addLayout(refresh_interval_layout)
       
       # Add auto-refresh group to settings tab
       settings_layout.addWidget(auto_refresh_group)
       
       # Nút tải dữ liệu
       load_button = QPushButton("Reload data from files")
       load_button.clicked.connect(self.load_initial_data)
       settings_layout.addWidget(load_button)
       
       # Nút xóa cache
       clear_cache_button = QPushButton("Clear data cache")
       clear_cache_button.clicked.connect(self.clear_data_cache)
       settings_layout.addWidget(clear_cache_button)
       
       # Nút lưu dữ liệu
       save_button = QPushButton("Save data to files")
       save_button.clicked.connect(self.save_data)
       settings_layout.addWidget(save_button)

       # Thêm tùy chọn Always on top
       always_on_top_layout = QHBoxLayout()
       self.always_on_top_checkbox = QCheckBox("Always on top")
       self.always_on_top_checkbox.stateChanged.connect(self.toggle_always_on_top)
       always_on_top_layout.addWidget(self.always_on_top_checkbox)
       settings_layout.addLayout(always_on_top_layout)
       
       # Thêm khoảng trống
       settings_layout.addStretch()
   
   def toggle_pyproxy(self, state):
       """Toggle PyProxy functionality on/off"""
       self.pyproxy_enabled = (state == Qt.Checked)
       self.update_pyproxy_ui_state()
       
       # Save the setting to config file
       config_file = Path(__file__).resolve().parent / "pyproxy_config.json"
       try:
           if config_file.exists():
               with open(config_file, "r", encoding="utf-8") as f:
                   config = json.load(f)
           else:
               config = {}
               
           config["enabled"] = self.pyproxy_enabled
           
           with open(config_file, "w", encoding="utf-8") as f:
               json.dump(config, f, indent=4)
               
           self.log_message(f"PyProxy {'enabled' if self.pyproxy_enabled else 'disabled'}", False)
       except Exception as e:
           self.log_message(f"Error saving PyProxy setting: {str(e)}", True)
   
   def update_pyproxy_ui_state(self):
       """Update UI elements based on PyProxy enabled state"""
       enabled = self.pyproxy_enabled
       self.access_key_input.setEnabled(enabled)
       self.access_secret_input.setEnabled(enabled)
       self.remaining_traffic_bar.setEnabled(enabled)
       self.pyproxy_info_label.setEnabled(enabled)
       
       # Find all PyProxy-related buttons and enable/disable them
       for widget in self.findChildren(QPushButton):
           if widget.text() in ["Save Access Key", "Whitelist IP", "Update Proxy"]:
               widget.setEnabled(enabled)
   
   def update_refresh_interval(self, value):
       """Update the file monitoring timer interval"""
       self.file_monitor_timer.setInterval(value * 1000)
       self.log_message(f"Auto-refresh interval set to {value} seconds", False)
   
   def check_files_for_changes(self):
       """Check if any data files have changed and update UI if needed"""
       if not self.auto_refresh_checkbox.isChecked():
           return
           
       try:
           base_dir = Path(__file__).resolve().parent
           
           # Kiểm tra nhanh thời gian sửa đổi trước khi đọc nội dung file
           files_to_check = [
               ("proxies", base_dir / "proxies.txt"),
               ("data", base_dir / "data.txt"),
               ("acc", base_dir / "acc_amz.txt")
           ]
           
           for file_type, file_path in files_to_check:
               if not file_path.exists():
                   continue
                   
               try:
                   mod_time = file_path.stat().st_mtime
                   if mod_time > self.file_mod_times[file_type]:
                       self.file_mod_times[file_type] = mod_time
                       self.log_message(f"{file_type.capitalize()} file changed, updating UI", False)
                       
                       # Chỉ đọc file khi cần thiết
                       if file_type == "proxies":
                           proxies = load_proxies()
                           self.proxy_text.setText("\n".join(proxies))
                       elif file_type == "data":
                           data_items = load_data()
                           self.data_text.setText("\n".join(data_items))
                       elif file_type == "acc":
                           acc_items = load_acc_amz()
                           self.acc_text.setText("\n".join(acc_items))
               except Exception as e:
                   self.log_message(f"Error checking {file_type} file: {str(e)}", True)
       except Exception as e:
           self.log_message(f"Error checking file changes: {str(e)}", True)
       self.update_data_counts()
   
   def update_textboxes_from_files(self):
       """Update textboxes from files during automation"""
       try:
           # Force update from files
           self.check_files_for_changes()
       except Exception as e:
           self.log_message(f"Error updating textboxes: {str(e)}", True)
   
   def upload_file(self, file_type):
       """Tải lên file dữ liệu"""
       file_path, _ = QFileDialog.getOpenFileName(self, f"Chọn file {file_type}", "", "Text Files (*.txt);;All Files (*)")
       if not file_path:
           return
           
       try:
           with open(file_path, 'r', encoding='utf-8') as f:
               content = f.read()
               
           if file_type == "proxy":
               self.proxy_text.setText(content)
               self.log_message(f"Uploaded proxy file: {file_path}", False)
               # Cập nhật cache
               self.data_loader.proxies = [line.strip() for line in content.split("\n") if line.strip()]
               self.data_loader.last_load_time["proxies"] = time.time()
               # Save to default file
               self.save_to_file("proxies.txt", content)
           elif file_type == "data":
               self.data_text.setText(content)
               self.log_message(f"Uploaded data file: {file_path}", False)
               # Cập nhật cache
               self.data_loader.data_items = [line.strip() for line in content.split("\n") if line.strip()]
               self.data_loader.last_load_time["data"] = time.time()
               # Save to default file
               self.save_to_file("data.txt", content)
           elif file_type == "acc":
               self.acc_text.setText(content)
               self.log_message(f"Uploaded account file: {file_path}", False)
               # Cập nhật cache
               self.data_loader.acc_items = [line.strip() for line in content.split("\n") if line.strip()]
               self.data_loader.last_load_time["acc"] = time.time()
               # Save to default file
               self.save_to_file("acc_amz.txt", content)
       except Exception as e:
           self.log_message(f"Error uploading {file_type} file: {str(e)}", True)
       self.update_data_counts()
   
   def save_to_file(self, filename, content):
       """Save content to a file and update modification time"""
       try:
           base_dir = Path(__file__).resolve().parent
           file_path = base_dir / filename
           
           with open(file_path, "w", encoding="utf-8") as f:
               f.write(content)
           
           # Update file modification time
           if "proxies" in filename:
               self.file_mod_times["proxies"] = file_path.stat().st_mtime
           elif "data" in filename:
               self.file_mod_times["data"] = file_path.stat().st_mtime
           elif "acc" in filename:
               self.file_mod_times["acc"] = file_path.stat().st_mtime
               
           self.log_message(f"Saved content to {filename}", False)
       except Exception as e:
           self.log_message(f"Error saving to {filename}: {str(e)}", True)
       
   def load_initial_data(self):
       """Tải dữ liệu ban đầu từ file với lazy loading"""
       try:
           self.log_message("Loading data from files...", False)
           
           # Sử dụng lazy loading với force=True để đảm bảo dữ liệu mới
           proxies = self.data_loader.load_proxies(force=True)
           data_items = self.data_loader.load_data(force=True)
           acc_items = self.data_loader.load_acc(force=True)
           
           # Cập nhật UI nếu có dữ liệu
           if proxies:
               self.proxy_text.setText("\n".join(proxies))
               self.log_message(f"Loaded {len(proxies)} proxies", False)
           
           if data_items:
               self.data_text.setText("\n".join(data_items))
               self.log_message(f"Loaded {len(data_items)} data items", False)
           
           if acc_items:
               self.acc_text.setText("\n".join(acc_items))
               self.log_message(f"Loaded {len(acc_items)} accounts", False)
           
           # Update file modification times
           base_dir = Path(__file__).resolve().parent
           
           proxies_file = base_dir / "proxies.txt"
           if proxies_file.exists():
               self.file_mod_times["proxies"] = proxies_file.stat().st_mtime
               
           data_file = base_dir / "data.txt"
           if data_file.exists():
               self.file_mod_times["data"] = data_file.stat().st_mtime
               
           acc_file = base_dir / "acc_amz.txt"
           if acc_file.exists():
               self.file_mod_times["acc"] = acc_file.stat().st_mtime
           
           self.log_message("Data loaded successfully", False)
       except Exception as e:
           self.log_message(f"Error loading data: {str(e)}", True)
       self.update_data_counts()

   def load_initial_data_with_progress(self):
       """Tải dữ liệu ban đầu từ file với hiển thị tiến trình"""
       try:
           self.statusBar().showMessage("Loading proxies...")
           self.log_message("Loading data from files...", False)
           
           # Sử dụng lazy loading với force=True để đảm bảo dữ liệu mới
           proxies = self.data_loader.load_proxies(force=True)
           if proxies:
               self.proxy_text.setText("\n".join(proxies))
               self.log_message(f"Loaded {len(proxies)} proxies", False)
               self.statusBar().showMessage(f"Loaded {len(proxies)} proxies", 2000)
           else:
               self.log_message("No proxies found", False)
               self.statusBar().showMessage("No proxies found", 2000)
           
           # Tải dữ liệu
           self.statusBar().showMessage("Loading data items...")
           data_items = self.data_loader.load_data(force=True)
           if data_items:
               self.data_text.setText("\n".join(data_items))
               self.log_message(f"Loaded {len(data_items)} data items", False)
               self.statusBar().showMessage(f"Loaded {len(data_items)} data items", 2000)
           else:
               self.log_message("No data items found", False)
               self.statusBar().showMessage("No data items found", 2000)
           
           # Tải tài khoản
           self.statusBar().showMessage("Loading accounts...")
           acc_items = self.data_loader.load_acc(force=True)
           if acc_items:
               self.acc_text.setText("\n".join(acc_items))
               self.log_message(f"Loaded {len(acc_items)} accounts", False)
               self.statusBar().showMessage(f"Loaded {len(acc_items)} accounts", 2000)
           else:
               self.log_message("No accounts found", False)
               self.statusBar().showMessage("No accounts found", 2000)
           
           # Update file modification times
           base_dir = Path(__file__).resolve().parent
           
           proxies_file = base_dir / "proxies.txt"
           if proxies_file.exists():
               self.file_mod_times["proxies"] = proxies_file.stat().st_mtime
               
           data_file = base_dir / "data.txt"
           if data_file.exists():
               self.file_mod_times["data"] = data_file.stat().st_mtime
               
           acc_file = base_dir / "acc_amz.txt"
           if acc_file.exists():
               self.file_mod_times["acc"] = acc_file.stat().st_mtime
           
           self.log_message("Data loaded successfully", False)
           self.statusBar().showMessage("Ready", 3000)
       except Exception as e:
           self.log_message(f"Error loading data: {str(e)}", True)
           self.statusBar().showMessage(f"Error loading data: {str(e)}", 5000)
       self.update_data_counts()
   
   def clear_data_cache(self):
       """Xóa cache dữ liệu và tải lại từ file"""
       try:
           self.data_loader.clear_cache()
           self.log_message("Data cache cleared", False)
           self.load_initial_data()
       except Exception as e:
           self.log_message(f"Error clearing data cache: {str(e)}", True)
   
   def save_data(self):
       """Lưu dữ liệu vào file"""
       try:
           base_dir = Path(__file__).resolve().parent
           
           # Lưu proxy
           proxy_content = self.proxy_text.toPlainText()
           with open(base_dir / "proxies.txt", "w", encoding="utf-8") as f:
               f.write(proxy_content)
           self.file_mod_times["proxies"] = (base_dir / "proxies.txt").stat().st_mtime
           
           # Lưu dữ liệu
           data_content = self.data_text.toPlainText()
           with open(base_dir / "data.txt", "w", encoding="utf-8") as f:
               f.write(data_content)
           self.file_mod_times["data"] = (base_dir / "data.txt").stat().st_mtime
           
           # Lưu tài khoản
           acc_content = self.acc_text.toPlainText()
           with open(base_dir / "acc_amz.txt", "w", encoding="utf-8") as f:
               f.write(acc_content)
           self.file_mod_times["acc"] = (base_dir / "acc_amz.txt").stat().st_mtime
           
           # Cập nhật cache
           self.data_loader.proxies = [line.strip() for line in proxy_content.split("\n") if line.strip()]
           self.data_loader.data_items = [line.strip() for line in data_content.split("\n") if line.strip()]
           self.data_loader.acc_items = [line.strip() for line in acc_content.split("\n") if line.strip()]
           
           current_time = time.time()
           self.data_loader.last_load_time = {
               "proxies": current_time,
               "data": current_time,
               "acc": current_time
           }
           
           self.log_message("Data saved to files", False)
       except Exception as e:
           self.log_message(f"Error saving data: {str(e)}", True)

   def update_network_usage(self):
       """Update network usage and recommended process count"""
       try:
           import psutil

           # Get current network stats
           net_io = psutil.net_io_counters()

           # Store current bytes sent/received
           if not hasattr(self, 'last_bytes_sent'):
               self.last_bytes_sent = net_io.bytes_sent
               self.last_bytes_recv = net_io.bytes_recv
               self.last_net_check = time.time()
               return

           # Calculate network usage
           current_time = time.time()
           time_elapsed = current_time - self.last_net_check

           if time_elapsed < 1:  # Ensure at least 1 second has passed
               return

           bytes_sent = net_io.bytes_sent - self.last_bytes_sent
           bytes_recv = net_io.bytes_recv - self.last_bytes_recv

           # Calculate speed in Mbps (megabits per second)
           total_bytes = bytes_sent + bytes_recv
           speed_mbps = (total_bytes * 8) / (time_elapsed * 1000000)

           # Update progress bar (assuming 100 Mbps is max)
           max_mbps = 100
           percent = min(100, (speed_mbps / max_mbps) * 100)
           self.network_traffic_bar.setValue(int(percent))
           self.network_traffic_bar.setFormat(f"{int(percent)}%")
           self.network_traffic_info.setText(f"{speed_mbps:.2f} Mbps")

           # Set color based on usage
           if speed_mbps < 30:
               color = "green"
           elif speed_mbps < 70:
               color = "orange"
           else:
               color = "red"

           self.network_traffic_bar.setStyleSheet(f"""
               QProgressBar::chunk {{
                   background-color: {color};
               }}
           """)

           # Calculate recommended process count based on network and CPU
           cpu_count = psutil.cpu_count(logical=False) or 1  # Physical cores

           # Get data count
           data_count = len([line.strip() for line in self.data_text.toPlainText().split("\n") if line.strip()])

           # Calculate recommended processes
           # Base formula: min(data_count, cpu_count * network_factor)
           network_factor = 1.0
           if speed_mbps < 10:
               network_factor = 1.0  # Full capacity
           elif speed_mbps < 30:
               network_factor = 0.8  # 80% capacity
           elif speed_mbps < 50:
               network_factor = 0.6  # 60% capacity
           else:
               network_factor = 0.4  # 40% capacity

           recommended = min(data_count, max(1, int(cpu_count * network_factor)))
           self.recommended_processes_label.setText(f"{recommended} (based on {cpu_count} CPU cores and {speed_mbps:.2f} Mbps)")

           # Update for next check
           self.last_bytes_sent = net_io.bytes_sent
           self.last_bytes_recv = net_io.bytes_recv
           self.last_net_check = current_time

       except Exception as e:
           self.log_message(f"Error updating network usage: {str(e)}", True)
           self.recommended_processes_label.setText("Error calculating")

   def start_automation(self):
       """Bắt đầu quá trình tự động hóa"""
       if self.worker_thread and self.worker_thread.isRunning():
           return
       
       # Tạm dừng các timer không cần thiết khi đang chạy tự động hóa
       self.network_usage_timer.stop()
       self.file_monitor_timer.stop()
    
       # Lấy cấu hình
       process_count = self.process_spin.value()
       headless = "y" if self.headless_combo.currentIndex() == 1 else "n"
    
       # Lấy dữ liệu từ text fields trước, nếu trống thì sử dụng lazy loader
       proxies = [line.strip() for line in self.proxy_text.toPlainText().split("\n") if line.strip()]
       if not proxies:
           proxies = self.data_loader.load_proxies()
           self.log_message("Using cached proxies", False)
    
       acc_items = [line.strip() for line in self.acc_text.toPlainText().split("\n") if line.strip()]
       if not acc_items:
           acc_items = self.data_loader.load_acc()
           self.log_message("Using cached accounts", False)
    
       # Lấy option đã chọn
       selected_option = self.option_combo.currentIndex() + 1
    
       # Đối với data, chỉ tải nếu option == 1
       if selected_option == 1 or selected_option == 4:
           with open("data.txt", "r", encoding="utf-8") as f:
            data_items = [line.strip() for line in self.data_text.toPlainText().split("\n") if line.strip()]#f.readlines()
           if not data_items:
               data_items = self.data_loader.load_data()
               self.log_message("Using cached data items", False)
       else:
           data_items = []
    
       data_count = len(data_items)
       acc_count = len(acc_items)
    
       # Kiểm tra dữ liệu
       if selected_option == 1 or selected_option == 4:
           if data_count == 0:
               self.log_message("No data. Please enter data.", True)
               return
           self.log_message(f"Starting with {data_count} data items", False)
       else:
           if acc_count == 0:
               self.log_message("No accounts. Please enter accounts.", True)
               return
           self.log_message(f"Starting with {acc_count} accounts", False)
    
       # Cập nhật UI
       self.start_button.setEnabled(False)
       self.stop_button.setEnabled(True)
       self.progress_bar.setValue(0)
    
       if selected_option == 1 or selected_option == 4:
           self.progress_label.setText(f"0/{data_count} data items processed (0 successful, 0 failed)")
       else:
           self.progress_label.setText(f"0/{acc_count} accounts processed (0 successful, 0 failed)")
    
       # Save data to files before starting
       self.save_data()
    
       # Tạo và khởi động worker thread
       self.worker_thread = WorkerThread(
           self.worker_signals, 
           process_count, 
           headless,
           selected_option,
           proxies, 
           data_items, 
           acc_items
       )
       self.worker_thread.start()
    
       self.log_message(f"Starting automation with {process_count} processes", False)
   
   def stop_automation(self):
       """Dừng quá trình tự động hóa"""
       if not self.worker_thread or not self.worker_thread.isRunning():
           return
       
       self.log_message("Stopping automation...", False)
       self.worker_thread.stop()
   
   @pyqtSlot(str, bool)
   def log_message(self, message, is_error):
       """Ghi log vào text box với cơ chế gộp log trùng lặp"""
       timestamp = time.strftime("%H:%M:%S")
       
       # Kiểm tra xem log có trùng với log trước đó không
       if message == self.last_log_message:
           self.duplicate_log_count += 1
           
           # Cập nhật log cuối cùng thay vì thêm log mới
           if self.duplicate_log_count > 1:
               # Tìm và cập nhật log cuối cùng
               cursor = self.log_text.textCursor()
               cursor.movePosition(QTextCursor.End)
               cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
               cursor.removeSelectedText()
               
               # Tạo log mới với số lần lặp
               if is_error:
                   formatted_message = f"<span style='color:red;'>[{timestamp}] ERROR: {message} (x{self.duplicate_log_count})</span>"
               else:
                   formatted_message = f"<span style='color:black;'>[{timestamp}] INFO: {message} (x{self.duplicate_log_count})</span>"
               
               self.log_text.insertHtml(formatted_message)
               return
       else:
           # Reset bộ đếm nếu log khác
           self.last_log_message = message
           self.duplicate_log_count = 1
       
       # Tạo định dạng cho log
       if is_error:
           formatted_message = f"<span style='color:red;'>[{timestamp}] ERROR: {message}</span>"
       else:
           formatted_message = f"<span style='color:black;'>[{timestamp}] INFO: {message}</span>"
       
       # Thêm vào log
       self.log_text.append(formatted_message)
       
       # Giới hạn số dòng log (giữ 1000 dòng gần nhất)
       document = self.log_text.document()
       if document.blockCount() > 1000:
           cursor = QTextCursor(document.findBlockByNumber(0))
           cursor.select(QTextCursor.BlockUnderCursor)
           cursor.removeSelectedText()
           cursor.deleteChar()
       
       # Cuộn xuống cuối
       cursor = self.log_text.textCursor()
       cursor.movePosition(QTextCursor.End)
       self.log_text.setTextCursor(cursor)
   
   @pyqtSlot(int, int, int, int)
   def update_progress(self, total, processed, live, dead):
       """Cập nhật thanh tiến trình"""
       if total > 0:
           percent = int((processed / total) * 100)
           self.progress_bar.setValue(percent)
        
           # Get the selected option
           selected_option = self.option_combo.currentIndex() + 1
        
           if selected_option == 1 or selected_option == 4:
               self.progress_label.setText(f"{processed}/{total} data items processed ({live} successful, {dead} failed)")
           else:
               self.progress_label.setText(f"{processed}/{total} accounts processed ({live} successful, {dead} failed)")
   
   @pyqtSlot()
   def on_worker_finished(self):
       """Xử lý khi worker hoàn thành"""
       self.start_button.setEnabled(True)
       self.stop_button.setEnabled(False)
       self.log_message("Tự động hóa đã hoàn thành", False)
       
       # Khởi động lại các timer
       self.network_usage_timer.start(5000)
       self.file_monitor_timer.start(self.refresh_interval_spin.value() * 1000)
       
   def save_access_key(self):
       """Lưu PyProxy Access Key và Access Secret"""
       if not self.pyproxy_enabled:
           self.log_message("PyProxy is disabled. Enable it first.", True)
           return
           
       access_key = self.access_key_input.text().strip()
       access_secret = self.access_secret_input.text().strip()
       
       if not access_key or not access_secret:
           self.log_message("Access Key and Access Secret cannot be empty", True)
           return
           
       self.pyproxy_manager.set_access_key(access_key, access_secret)
       success, message = self.pyproxy_manager.get_access_token()
       
       if success:
           # Lưu thông tin vào file cấu hình
           config_file = Path(__file__).resolve().parent / "pyproxy_config.json"
           try:
               # Load existing config if it exists
               if config_file.exists():
                   with open(config_file, "r", encoding="utf-8") as f:
                       config = json.load(f)
               else:
                   config = {}
                   
               config["access_key"] = access_key
               config["access_secret"] = access_secret
               config["enabled"] = self.pyproxy_enabled
               config["last_updated"] = time.time()
               
               with open(config_file, "w", encoding="utf-8") as f:
                   json.dump(config, f, indent=4)
               self.log_message("PyProxy information saved to config file", False)
           except Exception as e:
               self.log_message(f"Error saving config file: {str(e)}", True)
           
           self.log_message(f"Access Key saved and token obtained successfully", False)
           self.update_pyproxy_info()
           
           # Tự động cập nhật proxy sau khi lưu access key
           self.auto_update_proxy()
       else:
           self.log_message(f"Error getting token: {message}", True)
   
   def whitelist_ip(self):
       """Thêm IP hiện tại vào whitelist"""
       if not self.pyproxy_enabled:
           self.log_message("PyProxy is disabled. Enable it first.", True)
           return
           
       success, message = self.pyproxy_manager.add_ip_whitelist()
       
       if success:
           self.log_message(message, False)
       else:
           self.log_message(f"Error adding IP to whitelist: {message}", True)
   
   def update_proxy_list(self):
       """Cập nhật danh sách proxy từ API"""
       if not self.pyproxy_enabled:
           self.log_message("PyProxy is disabled. Enable it first.", True)
           return
           
       success, message = self.pyproxy_manager.update_proxy_file()
       
       if success:
           self.log_message(message, False)
           # Tải lại danh sách proxy vào UI
           proxies = load_proxies()
           self.proxy_text.setText("\n".join(proxies))
           # Update file modification time
           proxies_file = Path(__file__).resolve().parent / "proxies.txt"
           if proxies_file.exists():
               self.file_mod_times["proxies"] = proxies_file.stat().st_mtime
       else:
           self.log_message(f"Error updating proxies: {message}", True)
   
   def check_proxy_update(self):
       """Kiểm tra và cập nhật proxy theo thời gian"""
       if not self.pyproxy_enabled or not self.pyproxy_manager.access_key:
           return
           
       success, message = self.pyproxy_manager.update_proxy_file()
       
       if success:
           self.log_message(message, False)
           # Tải lại danh sách proxy vào UI nếu đang hiển thị
           proxies = load_proxies()
           self.proxy_text.setText("\n".join(proxies))   
           # Update file modification time
           proxies_file = Path(__file__).resolve().parent / "proxies.txt"
           if proxies_file.exists():
               self.file_mod_times["proxies"] = proxies_file.stat().st_mtime


   def set_progress_bar_color(self, progress_bar, percent):
       """Đặt màu cho thanh tiến trình dựa trên phần trăm"""
       style_sheet = """
            QProgressBar {
            border: 1px solid #bbb;
            border-radius: 4px;
            text-align: center;
            color: white;  /* Màu chữ xanh nước biển */
            font-size: 14px;
            font-weight: bold;
            background-color: #ff9800;  /* Màu nền xanh nước biển */
            }
            QProgressBar::chunk {
                background-color: #2196F3;  /* Màu thanh tiến trình cam */
                border-radius: 4px;  /* Bo góc để đẹp hơn */
            }
            """
       progress_bar.setStyleSheet(style_sheet)

   def update_pyproxy_info(self):
       """Cập nhật thông tin PyProxy"""
       if not self.pyproxy_enabled or not self.pyproxy_manager.access_key:
           return
       
       # Lấy lịch sử mua
       success_history, history_data = self.pyproxy_manager.get_purchase_history(size=3)
       
       info_text = "Thông tin PyProxy:\n"
       
       # Cập nhật thanh tiến trình balance và all_buy
       if success_history:
           if isinstance(history_data, dict) and "error" not in history_data:                
               remaining_traffic = history_data.get("balance", 0) / 1000  # Chuyển từ MB sang GB
               total_traffic = history_data.get("all_buy", 0) / 1000  # Chuyển từ MB sang GB
               remaining = 0
               if total_traffic > 0:
                   remaining = (remaining_traffic / total_traffic) * 100
               
               # Cập nhật thanh tiến trình
               self.remaining_traffic_bar.setValue(int(remaining))
               self.remaining_traffic_info.setText(f"{remaining_traffic:.2f} / {total_traffic:.2f} GB")
               
               # Đặt màu cho thanh tiến trình
               self.set_progress_bar_color(self.remaining_traffic_bar, 100 - remaining)
               
               info_text += f"Balance: {remaining_traffic:.2f} GB\n"
               info_text += f"Tổng đã mua: {total_traffic:.2f} GB\n"
               info_text += f"Còn lại: {remaining:.2f}%\n"
           else:
               error_msg = history_data.get('error', '') or history_data.get('error', 'Lỗi không xác định')
               info_text += f"Không thể lấy thông tin: {error_msg}\n"

       self.pyproxy_info_label.setText(info_text)

   def toggle_always_on_top(self, state):
       """Bật/tắt chế độ luôn hiển thị trên cùng"""
       if state == Qt.Checked:
           self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
           self.log_message("Always on top enabled", False)
       else:
           self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
           self.log_message("Always on top disabled", False)
       self.show()  # Cần hiển thị lại cửa sổ sau khi thay đổi flags

   def update_data_counts(self):
       """Cập nhật số lượng dữ liệu hiển thị bên cạnh các nhãn"""
       try:
           # Đếm số dòng không trống trong mỗi textbox
           proxy_count = len([line for line in self.proxy_text.toPlainText().split('\n') if line.strip()])
           data_count = len([line for line in self.data_text.toPlainText().split('\n') if line.strip()])
           acc_count = len([line for line in self.acc_text.toPlainText().split('\n') if line.strip()])
           
           # Cập nhật các label
           self.proxy_count_label.setText(f"({proxy_count})")
           self.data_count_label.setText(f"({data_count})")
           self.acc_count_label.setText(f"({acc_count})")
       except Exception as e:
           self.log_message(f"Error updating data counts: {str(e)}", True)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Thiết lập style
    app.setStyle("Fusion")
    
    # Tạo palette với màu sắc hiện đại
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 250))
    palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(245, 245, 255))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(0, 0, 0))
    palette.setColor(QPalette.Button, QColor(240, 240, 250))
    palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Highlight, QColor(100, 100, 200))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

