import logging
from pathlib import Path
import re
import subprocess
from typing import Optional, Union
import zipfile
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import undetected_chromedriver as uc

    
# Thiết lập logging
logger = logging.getLogger(__name__)

def create_proxy_auth_extension(profile_dir, proxy_host, proxy_port, proxy_user, proxy_pass):
    # Tạo thư mục extension riêng trong profile_dir để tránh xung đột
    plugin_dir = Path(profile_dir) / f"proxy_ext_{uuid.uuid4().hex}"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    zip_path = plugin_dir / 'proxy_auth.zip'
        
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth Extension",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        }
    }
    """

    background_js = f"""
    var config = {{
            mode: "fixed_servers",
            rules: {{
              singleProxy: {{
                scheme: "http",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
              }},
              bypassList: ["localhost"]
            }}
          }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

    chrome.webRequest.onAuthRequired.addListener(
      function(details) {{
        return {{
          authCredentials: {{
            username: "{proxy_user}",
            password: "{proxy_pass}"
          }}
        }};
      }},
      {{urls: ["<all_urls>"]}},
      ['blocking']
    );
    """

    with zipfile.ZipFile(zip_path, 'w') as zp:
        zp.writestr('manifest.json', manifest_json)
        zp.writestr('background.js', background_js)

    return zip_path

def chrome_options(
    proxy: Optional[str] = None, 
    profile_dir: Optional[Union[str, Path]] = None, 
    headless: Optional[str] = None, 
    x_coord: int = 0, 
    y_coord: int = 0
):
    options = uc.ChromeOptions()
    
    if profile_dir:
        options.add_argument(f"--user-data-dir={profile_dir}")
        
    if proxy and '@' in proxy:
        auth, addr = proxy.split('@', 1)
        proxy_user, proxy_pass = auth.split(':', 1)
        proxy_host, proxy_port = addr.split(':', 1)
        # Tạo extension proxy bên trong profile_dir
        plugin_zip = create_proxy_auth_extension(profile_dir, proxy_host, proxy_port, proxy_user, proxy_pass)
        options.add_extension(str(plugin_zip))
    elif proxy:
        options.add_argument(f"--proxy-server=http://{proxy}")
    
    if headless and headless.lower() == 'y':
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    else:
        options.add_argument(f"--window-position={x_coord},{y_coord}")
        options.add_argument("--window-size=500,500")
           
    # Các tùy chọn bổ sung để tránh phát hiện tự động hóa
    options.add_argument("--allow-pre-commit-input")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-sync")
    options.add_argument('--disable-extensions')
    options.add_argument("--incognito")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--password-store=basic")
    options.add_argument("--force-device-scale-factor=0.75")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-gaia-services")
    options.add_argument("--disable-application-cache")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--disable-software-rasterizer")

    logger.info(f"Thiết lập Chrome options với proxy: {proxy}, profile: {profile_dir}, headless: {headless}")
        
    # --- Kiểm tra orbital.exe ---
    chrome_versions_dir = Path("chrome_versions")
    orbital_path = chrome_versions_dir / "chrome.exe"
    orbital_driver = chrome_versions_dir / "chromedriver.exe"
    
    try:
        if orbital_path.exists() and orbital_driver.exists():
            logger.info(f"Phát hiện chrome.exe tại {orbital_path}")

            # --- Lấy version chính xác từ orbital.exe ---
            version = None
            try:
                result = subprocess.run(
                    [str(orbital_path), "--version"],
                    capture_output=True, text=True, check=True
                )
                version_output = result.stdout.strip()
                logger.info(f"Chrome version output: {version_output}")

                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", version_output)
                if match:
                    version = match.group(1)
                    logger.info(f"Đã phát hiện version: {version}")
                else:
                    logger.warning("Không tìm thấy chuỗi version hợp lệ trong output.")
            except Exception as e:
                logger.warning(f"Không lấy được version chrome.exe: {e}")

            # Dùng orbital làm binary chính
            options.binary_location = str(orbital_path)

            # --- Tải chromedriver tương ứng version ---
            driver_path = orbital_driver
            driver = uc.Chrome(options=options, driver_executable_path=driver_path)
            logger.info("Đã khởi chạy thành công orbital.exe cùng Chrome options.")
            return driver

        # --- Nếu không có orbital.exe thì dùng Chrome mặc định ---
        logger.info("Không phát hiện orbital.exe, dùng Chrome mặc định.")
        driver = uc.Chrome(
            options=options,
            driver_executable_path=ChromeDriverManager().install()
        )
        return driver

    except Exception as e:
        logger.error(f"Lỗi khi tạo Chrome driver: {e}", exc_info=True)
        return None