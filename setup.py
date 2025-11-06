import os
import sys
import subprocess
import platform
import urllib.request
import time
from pathlib import Path

def install_vcredist2012() -> None:
    url = "https://download.microsoft.com/download/1/6/b/16b06f60-3b20-4ff2-b699-5e9b7962f9ae/VSU_4/vcredist_x86.exe"
    file_path = os.path.join(os.getcwd(), "vcredist_x86.exe")

    print("\U0001F4E0 Đang tải Visual C++ 2012 Redistributable...")
    urllib.request.urlretrieve(url, file_path)
    print("✅ Tải xuống hoàn tất.")

    print("⚙️ Đang cài đặt tự động...")
    try:
        cmd = f'Start-Process "{file_path}" -ArgumentList "/quiet", "/norestart" -Verb RunAs'
        subprocess.run(["powershell", "-Command", cmd], shell=True, check=True)
        print("✅ Cài đặt hoàn tất.")
    except subprocess.CalledProcessError as e:
        print("❌ Lỗi khi cài đặt:", e)

def install_requirements() -> bool:
    print("🔄 Đang cập nhật pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    print("✅ Đã cập nhật pip thành công!")
    
    requirements = [
        "selenium", "setuptools", "psutil", "colorama", "PyQt5", "pyotp", "python-telegram-bot==20.6", "ua_generator", "webdriver_manager", "undetected-chromedriver", "faker"
    ]
    
    print("📦 Đang cài đặt các gói cần thiết...")
    for package in requirements:
        if package != "python-telegram-bot==20.6":
            print(f"⚙️ Đang cài đặt {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package])
                print(f"✅ Đã cài đặt thành công {package}")
            except subprocess.CalledProcessError:
                print(f"❌ Không thể cài đặt {package}.")            
                return False
    
    return True

def create_directories() -> bool:
    base_dir = Path(__file__).resolve().parent
    directories = ["profiles"]
    
    print("📂 Đang tạo các thư mục...")
    for directory in directories:
        dir_path = base_dir / directory
        dir_path.mkdir(exist_ok=True)
        print(f"✅ Đã tạo thư mục: {dir_path}")
    
    files = ["proxies.txt", "data.txt", "acc_amz.txt"]
    for file in files:
        file_path = base_dir / file
        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                pass
            print(f"📝 Đã tạo file trống: {file_path}")
    
    return True

def main() -> None:
    print("╔════════════════════════════════════════════════════════╗")
    print("║               Auto Farm Setup                          ║")
    print("╠════════════════════════════════════════════════════════╣")
    print("║ Script này sẽ cài đặt các gói cần thiết và             ║")
    print("║ tạo các thư mục cần thiết cho ứng dụng.                ║")
    print("╚════════════════════════════════════════════════════════╝")
    
    if platform.system() == "Windows":
        install_vcredist2012()
    
    if not install_requirements():
        print("❌ Không thể cài đặt các gói cần thiết. Vui lòng thử lại.")
        return
    
    if not create_directories():
        print("❌ Không thể tạo các thư mục. Vui lòng kiểm tra quyền truy cập.")
        return
    
    print("═" * 60)
    print("🎉 THIẾT LẬP HOÀN TẤT! 🎉")
    print("🔥 Bạn có thể chạy ứng dụng cách mở file:")
    print("   👉 ConBoMoi.pyw")
    print("═" * 60)
    
    for i in range(10, 0, -1):
        print(f"⏳ Đóng chương trình sau {i} giây...", end="\r", flush=True)
        time.sleep(1)
    
    print("\n👋 Tạm biệt!")
    os._exit(0)

if __name__ == "__main__":
    main()
