# Kiểm chứng bản demo

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
  operator; phải chuẩn bị môi trường OS test cách ly theo docs/SECURITY.md.
- Retention không xóa dữ liệu user, source hoặc lịch sử global của provider.

Chạy lại: `python -m unittest discover -s tests -v` và `python hub.py demo --simulate`.

CI mẫu ở `docs/github-actions-test.yml.example`. Chưa bật GitHub Actions vì token push thiếu scope workflow. Muốn bật, chép mẫu vào `.github/workflows/test.yml` và push bằng tài khoản/token có quyền workflow.
