"""Local terminal menu; monitoring does not call an AI model."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agenthub.api import Hub
from agenthub.config import default_home
from agenthub.service import start_daemon, stop_daemon, daemon_status
from hub import doctor, make_demo


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Cần Python 3.11 trở lên.')
    hub = Hub(default_home())
    while True:
        print('\nAGENT HUB PRIVATE — Auto / tiết kiệm quota')
        print('1 Kiểm tra CLI   2 Tạo demo   3 Giao việc   4 Tiến độ')
        print('5 Bật bộ điều phối   6 Dừng   7 Cấu hình MCP   8 Demo không tốn quota   0 Thoát menu')
        choice = input('Chọn: ').strip()
        try:
            if choice == '0':
                print('Đóng menu không dừng daemon. Chọn 6 nếu muốn dừng.')
                return
            if choice == '1': show(doctor(hub))
            elif choice == '2': show(make_demo(hub))
            elif choice == '3':
                projects = hub.store.all('SELECT name,path FROM projects')
                show(projects)
                project = input('Tên dự án: ').strip()
                objective = input('Yêu cầu: ').strip()
                key = input('Mã yêu cầu duy nhất (ví dụ todo-filter-1): ').strip()
                show(hub.start(project, objective, key))
            elif choice == '4':
                show({'daemon': daemon_status(hub.store.home), 'workflows': hub.store.all(
                    'SELECT id,status,phase,leader,complexity,calls,max_calls,workspace,error FROM workflows ORDER BY updated DESC LIMIT 20')})
            elif choice == '5': show(start_daemon(hub.store.home))
            elif choice == '6': show(stop_daemon(hub.store.home))
            elif choice == '7':
                subprocess.run([sys.executable, str(ROOT/'hub.py'), '--home', str(hub.store.home), 'mcp-config'], check=True)
            elif choice == '8':
                from agenthub.simulation import simulate
                show(simulate())
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            print('Lỗi:', error)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except (KeyboardInterrupt, EOFError): print('\nĐã đóng menu; daemon giữ nguyên trạng thái.')
