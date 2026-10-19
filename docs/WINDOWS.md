# Windows

## Chuẩn bị

- Windows 10/11, Python 3.11+ và Git trong PATH.
- Codex CLI cài/đăng nhập được trong terminal của chính bạn.
- Claude Code, GitHub Copilot CLI, Antigravity CLI là tùy chọn. Dùng tài liệu chính thức từng CLI;
  Hub không thu thập token hoặc trích đăng nhập từ ứng dụng khác.
- Antigravity IDE có thể làm giao diện MCP ngay cả khi chưa có agy CLI. Trong trường hợp đó,
  truyền prepared_plan/handoff qua MCP; pool nội bộ sẽ dùng CLI khác ở các bước cần quyết định.

## Khởi động

Giải nén ZIP nguồn vào thư mục cố định; mở Start-Hub.cmd. Không chép thư mục data/
hoặc cấu hình đường dẫn Linux sang Windows. Chọn Doctor và Offline Demo trước khi chạy thật.

Windows npm thường tạo codex.cmd/copilot.cmd. Hub không gửi prompt qua cmd.exe: nó tìm
native .exe trong npm optional package hoặc gọi node.exe với script entrypoint.
Nếu không tìm ra, sửa providers.<name>.command trong data/config.json bằng đường dẫn
native .exe hoặc array [node.exe, entry.js]. Không đặt câu lệnh ghép PowerShell/cmd vào command.
Doctor chỉ kiểm tra --version, chưa xác nhận auth và mọi flag của phiên bản CLI.

Claude và Copilot adapter được viết theo giao thức hiện tại, nhưng không có CLI đó trên
máy phát triển để kiểm chứng thật. Nếu flag thay đổi, provider sẽ bị loại khỏi pool và lỗi
được lưu rõ. Không tự cấp --allow-all-tools hoặc bypass sandbox để che lỗi.

## Đăng ký project bằng PowerShell 7

```powershell
python hub.py project-add my-app "D:\Code\my-app" --verify '[["node","--test"]]' --context '["README.md","src","test"]'
```

PowerShell 5.1 có thể làm mất quote JSON của native arguments. Có thể dùng Python trực tiếp
để đăng ký, tránh vấn đề quoting. Lưu file register_project.py UTF-8 trong root Hub rồi chạy:

```python
from agenthub.api import Hub
from agenthub.config import default_home
hub = Hub(default_home())
hub.store.add_project(
    'my-app', r'D:\Code\my-app',
    [['node', '--test']], ['README.md', 'src', 'test'],
)
```

## Tự chạy sau đăng nhập

scripts/install-autostart.ps1 tạo task AgentHubPrivate với tài khoản hiện tại, quyền Limited,
không admin. Task chỉ chạy khi đăng nhập, không đánh thức máy ngủ và không tự bật máy.
Task giữ nguyên path lúc cài; di chuyển thư mục thì chạy lại installer. remove-autostart.ps1
chỉ gỡ startup; dùng hub.py stop để dừng daemon đang chạy.

## Coverage

Không có máy Windows trong môi trường phát triển hiện tại. Đã chuẩn bị CI matrix Windows
và Linux nhưng chưa chạy trên GitHub. Khóa msvcrt, Win32 PID handle, taskkill /T, npm shim
và Task Scheduler cần xác nhận bằng offline demo/tests trên Windows của bạn.

CI mẫu ở `docs/github-actions-test.yml.example`. Chưa bật GitHub Actions vì token push thiếu scope workflow. Muốn bật, chép mẫu vào `.github/workflows/test.yml` và push bằng tài khoản/token có quyền workflow.

## Lệnh từ folder dự án

Chạy `scripts/install-command.ps1` một lần để thêm thư mục Hub vào PATH của user,
rồi mở terminal mới. Trong folder Git được phép, chạy `hub here` để đăng ký/khôi phục
trạng thái không tốn quota. Launcher `hub.cmd` giữ nguyên cwd của dự án, không cd vào Hub.
Nếu PATH có công cụ khác cùng tên, kiểm tra `where.exe hub` và gọi đúng `hub.cmd` bằng
đường dẫn tuyệt đối. Dùng `hub here --name my-app` ở lần đầu nếu muốn tên ngắn.
Lệnh test suy ra từ tên file tracked là gợi ý, không được thực thi lúc nhận diện.
Node/monorepo/loại không rõ cần `--verify`; xem ví dụ quoting CMD/PowerShell trong README.
Không nâng quyền hoặc đổi ExecutionPolicy nếu script PATH bị chặn: gọi hub.cmd trực tiếp.
