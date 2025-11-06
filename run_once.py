import psutil
import os
import subprocess
import pygetwindow as gw
import win32com.client
import win32gui;
import win32con;

SCRIPT_NAME = "ConBoMoi.py"
WINDOW_KEYWORD = "Con Bọ Mới"  # Một phần tiêu đề cửa sổ app

def is_running(script_name):
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.info['name'] and "python" in p.info['name'].lower():
                if any(script_name in str(cmd) for cmd in p.info['cmdline']):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def focus_existing_window(keyword):
    """Kích hoạt thật sự cửa sổ app đang chạy (kể cả khi minimize)."""
    shell = win32com.client.Dispatch("WScript.Shell")

    for title in gw.getAllTitles():
        if keyword.lower() in title.lower():
            try:
                hwnd = win32gui.FindWindow(None, title)
                if hwnd:
                    # Restore nếu đang minimize
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    # Cho phép cửa sổ được lấy focus
                    shell.AppActivate(title)
                    print(f"Đã kích hoạt cửa sổ: {title}")
                    return True
            except Exception as e:
                print(f"Lỗi khi kích hoạt cửa sổ: {e}")
    return False

if is_running(SCRIPT_NAME):
    focus_existing_window(WINDOW_KEYWORD)
    exit(0)
else:
    subprocess.Popen(["python", SCRIPT_NAME], creationflags=subprocess.CREATE_NEW_CONSOLE)
