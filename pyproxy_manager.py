"""
Module quản lý PyProxy API và các chức năng liên quan.
"""
import os
import time
import json
import logging
import requests
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# Thiết lập logging
logger = logging.getLogger(__name__)

class PyProxyManager:
    """
    Lớp quản lý các chức năng liên quan đến PyProxy.
    """
    
    def __init__(self, access_key: str = "", access_secret: str = ""):
        """
        Khởi tạo PyProxyManager.
        
        Args:
            access_key: Khóa truy cập PyProxy
            access_secret: Khóa bí mật PyProxy
        """
        self.access_key = access_key
        self.access_secret = access_secret
        self.token = ""
        self.token_expire_time = 0
        self.last_proxy_update = 0
        self.proxy_update_interval = 3 * 60 * 60  # 3 giờ
        self.base_url = "https://api.pyproxy.com/g/open"
        self.proxy_url = "https://acq.iemoapi.com/getProxyIp"
        self.base_dir = Path(__file__).resolve().parent
        self.proxies_file = self.base_dir / "proxies.txt"
        
    def set_access_key(self, access_key: str, access_secret: str) -> None:
        """
        Thiết lập khóa truy cập PyProxy.
        
        Args:
            access_key: Khóa truy cập PyProxy
            access_secret: Khóa bí mật PyProxy
        """
        self.access_key = access_key
        self.access_secret = access_secret
        self.token = ""  # Reset token khi thay đổi access_key
        self.token_expire_time = 0
        
    def get_access_token(self) -> Tuple[bool, str]:
        """
        Lấy token truy cập từ PyProxy API.
        
        Returns:
            Tuple[bool, str]: (Thành công, Token hoặc thông báo lỗi)
        """
        if not self.access_key or not self.access_secret:
            return False, "Chưa thiết lập access_key hoặc access_secret"
        
        # Kiểm tra nếu token hiện tại vẫn còn hiệu lực
        current_time = int(time.time())
        if self.token and current_time < self.token_expire_time - 300:  # Trừ 5 phút để đảm bảo an toàn
            return True, self.token
            
        try:
            # Tạo timestamp
            timestamp = str(int(time.time()))
            
            # Tính toán sign
            sign_str = self.access_key + self.access_secret + timestamp
            sign = hashlib.sha256(sign_str.encode()).hexdigest()
            
            url = f"{self.base_url}/get_access_token"
            data = {
                "access_key": self.access_key,
                "sign": sign,
                "timestamp": timestamp
            }
            
            response = requests.post(url, data=data)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                ret_data = result.get("ret_data", {})
                self.token = ret_data.get("access_token", "")
                self.token_expire_time = ret_data.get("expire_time", 0)
                return True, self.token
            else:
                return False, f"Lỗi: {result.get('msg', 'Không xác định')}"
        except Exception as e:
            logger.error(f"Lỗi khi lấy token: {e}")
            return False, f"Lỗi kết nối: {str(e)}"
            
    def add_ip_whitelist(self, white_type: str = "other", mark: str = "") -> Tuple[bool, str]:
        """
        Thêm IP hiện tại vào whitelist.
        
        Args:
            white_type: Loại whitelist ("other" hoặc "unlimited")
            mark: Ghi chú cho IP
            
        Returns:
            Tuple[bool, str]: (Thành công, Thông báo)
        """
        if not self.token:
            success, message = self.get_access_token()
            if not success:
                return False, message
                
        try:
            # Lấy IP hiện tại
            ip_response = requests.get("https://api.ipify.org")
            current_ip = ip_response.text.strip()
            
            url = f"{self.base_url}/add_ip_white"
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {
                "white_type": white_type,
                "ip": current_ip,
                "mark": mark
            }
            
            response = requests.post(url, headers=headers, data=data)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                return True, f"Đã thêm IP {current_ip} vào whitelist"
            else:
                return False, f"Lỗi: {result.get('msg', 'Không xác định')}"
        except Exception as e:
            logger.error(f"Lỗi khi thêm IP vào whitelist: {e}")
            return False, f"Lỗi kết nối: {str(e)}"
            
    def get_proxy_host(self, proxy_type: str = "other") -> Tuple[bool, str]:
        """
        Lấy thông tin proxy host.
        
        Args:
            proxy_type: Loại proxy ("other" hoặc "unlimited")
            
        Returns:
            Tuple[bool, str]: (Thành công, Thông tin host hoặc thông báo lỗi)
        """
        try:
            url = f"{self.base_url}/get_user_proxy_host"
            data = {"proxy_type": proxy_type}
            
            response = requests.post(url, data=data)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                ret_data = result.get("ret_data", {})
                host_list = ret_data.get("list", [])
                
                if not host_list:
                    return False, "Không tìm thấy proxy host"
                
                host_info = host_list[0]
                host = host_info.get("host", "")
                port = host_info.get("port", "")
                region = host_info.get("server_region", "")
                
                return True, f"Host: {host}, Port: {port}, Region: {region}"
            else:
                return False, f"Lỗi: {result.get('msg', 'Không xác định')}"
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin proxy host: {e}")
            return False, f"Lỗi kết nối: {str(e)}"
            
    def get_proxy_list(self) -> Tuple[bool, Union[List[str], str]]:
        """
        Lấy danh sách proxy từ API.
        
        Returns:
            Tuple[bool, Union[List[str], str]]: (Thành công, Danh sách proxy hoặc thông báo lỗi)
        """
        try:
            params = {
                "protocol": "socks5",
                "num": 5000,
                "regions": "us",
                "lb": 1,
                "return_type": "txt"
            }
            
            response = requests.get(self.proxy_url, params=params)
            
            if response.status_code == 200:
                proxies = [line.strip() for line in response.text.split("\n") if line.strip()]
                return True, proxies
            else:
                return False, f"Lỗi: Mã trạng thái {response.status_code}"
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách proxy: {e}")
            return False, f"Lỗi kết nối: {str(e)}"
            
    def update_proxy_file(self) -> Tuple[bool, str]:
        """
        Cập nhật file proxies.txt với danh sách proxy mới.
        
        Returns:
            Tuple[bool, str]: (Thành công, Thông báo)
        """
        current_time = time.time()
        
        # Đã loại bỏ giới hạn thời gian cập nhật
        
        try:
            success, result = self.get_proxy_list()
        
            if not success:
                return False, result
        
            if not result or len(result) == 0:
                return False, "API trả về danh sách proxy trống"
        
            try:
                # Đảm bảo thư mục cha tồn tại
                os.makedirs(os.path.dirname(self.proxies_file), exist_ok=True)
        
                with open(self.proxies_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(result))
        
                self.last_proxy_update = current_time
                return True, f"Đã cập nhật {len(result)} proxy vào file {self.proxies_file}"
            except Exception as e:
                logger.error(f"Lỗi khi cập nhật file proxy: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False, f"Lỗi khi ghi file: {str(e)}"
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật proxy: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"Lỗi khi cập nhật proxy: {str(e)}"
            
    def get_remaining_traffic(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Lấy thông tin về lượng traffic còn lại.
        
        Returns:
            Tuple[bool, Dict[str, Any]]: (Thành công, Thông tin traffic hoặc thông báo lỗi)
        """
        if not self.token:
            success, message = self.get_access_token()
            if not success:
                return False, {"error": message}
                
        try:
            url = f"{self.base_url}/get_remaining_traffic"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.post(url, headers=headers)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                ret_data = result.get("ret_data", {})
                remaining_traffic = ret_data.get("remaining_traffic", 0)
                
                # Tạo đối tượng kết quả với định dạng phù hợp
                traffic_info = {
                    "remaining_traffic": remaining_traffic,
                    "total_traffic": 100,  # Giả định giá trị mặc định
                    "timestamp": int(time.time())
                }
                
                return True, traffic_info
            else:
                return False, {"error": f"Lỗi: {result.get('msg', 'Không xác định')}"}
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin traffic còn lại: {e}")
            return False, {"error": f"Lỗi kết nối: {str(e)}"}
            
    def get_purchase_history(self, page: int = 1, size: int = 8, order_id: str = "", 
                            start_time: str = "", end_time: str = "", pay_status: str = "") -> Tuple[bool, Dict[str, Any]]:
        """
        Lấy lịch sử mua proxy.
        
        Args:
            page: Số trang
            size: Kích thước trang
            order_id: ID đơn hàng
            start_time: Thời gian bắt đầu (định dạng: "YYYY-MM-DD HH:MM:SS")
            end_time: Thời gian kết thúc (định dạng: "YYYY-MM-DD HH:MM:SS")
            pay_status: Trạng thái thanh toán ("" = tất cả, "1" = đã thanh toán, "0" = chưa thanh toán)
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (Thành công, Lịch sử mua hoặc thông báo lỗi)
        """
        if not self.token:
            success, message = self.get_access_token()
            if not success:
                return False, {"error": message}
                
        try:
            url = f"{self.base_url}/residential/get_purchase_history"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            data = {
                "page": str(page),
                "size": str(size)
            }
            
            # Thêm các tham số tùy chọn nếu được cung cấp
            if order_id:
                data["order_id"] = order_id
            if start_time:
                data["start_time"] = start_time
            if end_time:
                data["end_time"] = end_time
            if pay_status:
                data["pay_status"] = pay_status
            
            response = requests.post(url, headers=headers, data=data)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                return True, result.get("ret_data", {})
            else:
                return False, {"error": f"Lỗi: {result.get('msg', 'Không xác định')}"}
        except Exception as e:
            logger.error(f"Lỗi khi lấy lịch sử mua: {e}")
            return False, {"error": f"Lỗi kết nối: {str(e)}"}
            
    def get_daily_traffic(self, start_time: str = "", end_time: str = "") -> Tuple[bool, Dict[str, Any]]:
        """
        Lấy thông tin về lượng traffic sử dụng trong ngày.
        
        Args:
            start_time: Thời gian bắt đầu (timestamp)
            end_time: Thời gian kết thúc (timestamp)
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (Thành công, Thông tin traffic hoặc thông báo lỗi)
        """
        if not self.token:
            success, message = self.get_access_token()
            if not success:
                return False, {"error": message}
                
        try:
            url = f"{self.base_url}/traffic_history/main_account_daily"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            data = {}
            if start_time:
                data["start_time"] = start_time
            if end_time:
                data["end_time"] = end_time
            
            response = requests.post(url, headers=headers, data=data)
            result = response.json()
            
            if result.get("code") == 1 and result.get("ret") == 0:
                # Định dạng lại dữ liệu để dễ sử dụng
                traffic_data = {
                    "list": result.get("ret_data", []),
                    "timestamp": int(time.time())
                }
                
                # Tính toán tổng traffic sử dụng trong ngày
                total_used = 0
                if traffic_data["list"]:
                    for day_data in traffic_data["list"]:
                        # Chuyển đổi từ byte sang GB
                        global_traffic = day_data.get("global", 0)
                        total_used += global_traffic / (1024 * 1024 * 1024)
                
                traffic_data["total_used_gb"] = round(total_used, 2)
                
                return True, traffic_data
            else:
                return False, {"error": f"Lỗi: {result.get('msg', 'Không xác định')}"}
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin traffic hàng ngày: {e}")
            return False, {"error": f"Lỗi kết nối: {str(e)}"}

