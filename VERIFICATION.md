# Kiểm chứng bản demo

## V2 — Windows, 2026-10-20

Bản rút gọn `ma agents list`: **110 unittest pass** trong 57.986 giây. Mặc định
hiển thị một dòng tiêu đề và một dòng mỗi agent; `--json` giữ đầy đủ chẩn đoán.
Kiểm thử probe giả xác minh `--check` vẫn lưu đủ cache, trạng thái UNKNOWN/disabled
không bị suy đoán, metadata dài/control character không tạo dòng thừa. Không gọi model.

Bản sửa Setup Wizard: **106 unittest pass** trong 54.469 giây. Chọn model policy
một lần cho toàn bộ agent đã bật, fallback AUTO chỉ xác nhận một lần; role mặc định
được giữ tự động. Advanced cho phép tùy chỉnh riêng và sửa role không hợp lệ ngay
tại ô nhập. Có regression cho chuỗi `blank keeps current` và trường hợp PATH cũ
đã có ma.cmd từ cùng checkout. Kiểm thử dùng input/probe/PATH giả, không gọi model.

- Python 3.13.15, Git 2.54.0.windows.1: **98 unittest pass** trong 55.011 giây.
- Gồm 51 regression test và 47 test V2: discovery/auth probe giả, model policy/fallback,
  selection/roles, context hash/version, không ghi metadata vào repo, CLI Unicode,
  MCP aliases/quyền/đệ quy, setup rollback, PATH ownership giả lập, migration SQLite,
  update fast-forward giả lập, monitoring từ event và giữ sandbox.
- `ma ... demo --simulate`: completed, leader failover quan sát được, 4 test fixture
  pass, source gốc không đổi, actual_model_calls=0.
- `setup.ps1` được parse cú pháp bằng PowerShell; launcher ma.cmd được chạy với repo
  synthetic có Unicode. Không chạy wizard cài PATH hoặc sửa MCP config thật trong phase này.
- Client configs/PATH trong test là file tạm hoặc mock. Chưa live-verify Codex/Claude/
  Copilot/Antigravity adapter, phiên đăng nhập, model catalog thật, hoặc chat/MCP IDE.
- Không chạy lại trên Linux trong phiên này; không tự bật CI GitHub Actions.
- Không tự commit, push, merge, migrate state thật, đổi security flags hay autostart.
- Xem [báo cáo từng phase](docs/V2_PHASE_REPORT.md). Các ghi chú V1 bên dưới là lịch sử.

## V1 history

Kiểm chứng Windows ngày 2026-10-19: Python 3.13.15, Git 2.54.0.windows.1,
51 unittest pass sau khi sửa test CRLF/LF và thêm policy cách ly theo yêu cầu.
Coverage mới gồm synthetic không yêu cầu cách ly, yêu cầu cách ly nhưng chưa xác nhận,
config cũ, kiểu boolean không hợp lệ và tiếp tục chặn mạng không giới hạn.
Không gọi model thật trong lần kiểm chứng này. Các ghi chú Linux bên dưới là lịch sử.

Môi trường phát triển: Linux, Python 3.12, Git, Codex CLI 0.163.0-alpha.10.2.

- 46 unittest pass sau khi thêm security gate, gồm retry/failover, quota wait,
  generation, context/cache, verification/repair, cleanup giữ code, daemon độc lập,
  timeout subprocess và security mặc định chặn/cấm unrestricted network.
- Thêm 7 test nhận diện dự án: chạy từ thư mục con/đường dẫn có khoảng trắng,
  đăng ký lặp khôi phục memory, tên folder trùng, repo không rõ, giữ cấu hình cũ,
  ngoài Git và CLI chạy từ cwd khác. Không gọi model hoặc chạy test của repo được nhận diện.
- Launcher hub.cmd và script PATH PowerShell chưa được chạy trực tiếp trên Windows.
- Demo offline dùng SQLite/Git worktree/test thật, model được mô phỏng; không tốn quota.
- Smoke test Codex thật trước khi bổ sung policy bảo mật: 1 lượt CLI sửa tiêu đề README
  trong fixture, 2 test pass; đã xuất ZIP, source gốc không đổi. Kết quả này không chứng
  minh cách ly dữ liệu thật và không áp dụng như bằng chứng sandbox của bản hiện tại.
- Windows: chuẩn bị adapter/locking/startup và CI Windows + Linux Python 3.11–3.13;
  chưa chạy Windows trực tiếp trong phiên phát triển. Không tuyên bố Windows đã pass.
- Claude/Copilot/Antigravity adapter chưa chạy model thật; CLI version/đăng nhập có thể
  cần điều chỉnh. IDE Antigravity không tự đảm bảo có lệnh agy.
- Chưa có ACL đọc file hoặc firewall do Hub triển khai. Gate chỉ kiểm tra xác nhận
  operator; cách ly OS theo yêu cầu của người dùng, xem docs/SECURITY.md.
- Retention không xóa dữ liệu user, source hoặc lịch sử global của provider.

Chạy lại: `python -m unittest discover -s tests -v` và `python hub.py demo --simulate`.

CI mẫu ở `docs/github-actions-test.yml.example`. Chưa bật GitHub Actions vì token push thiếu scope workflow. Muốn bật, chép mẫu vào `.github/workflows/test.yml` và push bằng tài khoản/token có quyền workflow.
