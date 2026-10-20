# Ubuntu: setup → init → prompt

Luồng dùng giữ nguyên: clone và setup một lần ở root Hub; mở folder dự án được
phép, chạy `ma init`; nhập prompt bình thường trong client đã kết nối MCP.
Không bắt buộc dùng terminal `ma run` cho từng yêu cầu.

## Máy Ubuntu đích cần gì?

- Python 3.11 trở lên, Git, shell POSIX; `python3` và `git` có trong PATH.
- Dependency và verifier của dự án đích đã có. Hub không tự cài dependency dự án.
- CLI chính thức của những provider muốn dùng, đăng nhập bằng tài khoản của bạn.
- Client chat nhận được MCP tool; nếu dùng @hub cần IDE hỗ trợ VS Code Chat API.
- Source được phép và dữ liệu synthetic đã được người dùng xác nhận.

Không giới hạn username, folder clone hoặc đường dẫn của máy phát triển.
Máy thiếu Python phù hợp phải cài từ nguồn hỗ trợ của hệ điều hành trước;
setup báo thiếu, không tự dùng sudo, thay Python hệ thống hoặc hạ sandbox.
Bằng chứng trên một máy không bảo đảm mọi phiên bản Ubuntu/CLI đều hoạt động.

## 1. Clone và setup từ đầu

```bash
mkdir -p ~/Project
cd ~/Project
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

Nếu folder đã có, không xóa/reset để giả làm clone mới; chọn folder trống khác khi
quay video. `python3 ma.py setup` tương đương, không phụ thuộc quyền executable.

Trong setup:

1. Chọn cả bốn CLI nếu muốn cấu hình đủ: codex, claude, copilot, antigravity.
   Không bắt buộc cả bốn cùng sẵn sàng. Thiếu CLI/login phải được ghi rõ.
2. Dùng INHERIT để giữ model mặc định riêng của từng provider; không ép cùng model ID.
3. Chọn cài launcher `ma`. Chạy lệnh export PATH mà setup in ra trong terminal của
   bạn, hoặc gọi launcher bằng đường dẫn tuyệt đối. Đây là bước cài một lần;
   script không tự sửa .bashrc/.profile. Terminal mới cần PATH đã được người dùng
   chủ động cấu hình; không được giả rằng parent shell tự nhận biến từ child process.
4. Chọn đúng client MCP đang dùng và xác nhận apply/backup. Refresh client theo yêu cầu.
   Nếu dùng Copilot Chat bridge, chọn cài @hub; chọn participant một lần, sau đó nhập
   prompt thường trong participant sticky. Không đồng nhất nó với chat Antigravity.

CLI mặc định được tìm qua PATH và thư mục native user-local `.local/bin`. Ví dụ
không chứa đường dẫn máy cá nhân: [providers.example.json](../examples/config/providers.example.json).
Máy dùng vị trí riêng có thể cấu hình command tương ứng; không copy home/config của
máy khác. Trạng thái auth/model/quota không nằm trong cấu hình mẫu và không tự nhận READY.

CLI và login chính thức:

| Provider | Lệnh CLI | Login người dùng |
|---|---|---|
| Codex | `codex` | `codex login` |
| Claude Code | `claude` | `claude auth login` |
| Copilot | `copilot` | `copilot login` |
| Antigravity | `agy` | Mở `agy`, hoàn tất luồng sign-in chính thức |

CLI phiên bản khác có thể đổi flag; setup dùng probe chính thức, không đọc file token.
Cài IDE/extension không có nghĩa CLI đã được cài. Các CLI cần quyền tài khoản/quota riêng.

## 2. Vào dự án và init

```bash
cd /duong/dan/source-duoc-phep
ma init
```

Repo cần Git baseline sạch, đã commit. Init không tự commit/stash/reset file người dùng.
Xác nhận phạm vi source/synthetic/no-API cho project. Chưa có verifier rõ ràng thì chỉ
định bằng `ma init --verify-command EXECUTABLE ARGS` (đặt option này cuối).
Baseline chạy trong worktree riêng; `--register-only` không được gọi là ready.

Home mặc định theo XDG user data; có thể chọn home riêng ngay từ setup bằng
`AGENT_HUB_HOME` hoặc `python3 ma.py --home PATH setup`. Launcher/MCP ghim cùng home;
không thay home tùy tiện khi init. Home phải ngoài source repo đã đăng ký.

## 3. Nhập prompt bình thường

Ví dụ: `Thêm chức năng lọc công việc theo trạng thái và từ khóa, giữ tương thích và bổ sung test.`
Client cần khớp workspace với project đã init, lấy checkpoint và gọi workflow_start.
Chỉ ghi nhận dispatch thành công khi có workflow ID/event của đúng project.
Cấu hình MCP/initialize instructions không tự chứng minh chat UI đã gọi tool.

Nếu host chat hết quota trước khi gọi tool, prompt mới có thể không tới Hub. MCP không
phải một ô chat độc lập. @hub không gọi host model trong handler, nhưng UI có thể chặn
request trước handler; phải kiểm trên IDE thật, không suy ra từ unit test.

## Checklist quay video

- Bắt đầu ở folder trống, quay lệnh clone thật; không dùng clone hoặc state đã init sẵn
  để nói rằng vừa cài từ đầu. Các CLI đã cài/login là prerequisite, nói rõ trong video.
- Quay setup ở root Hub; chọn provider/client và việc apply theo lựa chọn người dùng.
- Mở repo demo synthetic mới, quay ma init và baseline/MCP result.
- Gửi prompt trong client đã kết nối. Chỉ quay cảnh này khi đã xác minh UI dispatch.
- Hiện provider thật đã chạy, verifier output, review và phần code thay đổi đúng workflow. Dùng `ma diff`, rồi `ma accept ID`
  hoặc `@hub /accept ID` để áp dụng vào file dự án. Auto accept mặc định tắt.
- Không quay OAuth/device code, token, file config tài khoản hoặc dữ liệu người dùng.
- Chỉ demo nhiều-provider/quota-failover thật nếu đã quan sát; mô phỏng phải ghi rõ.
- Không tự cấp thêm model calls để quay lại. Rehearsal và lần quay mới cần budget rõ ràng.

## Bằng chứng và giới hạn

Xem [VERIFICATION.md](../VERIFICATION.md) và [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
Nguồn portable, launcher/temp-path tests và workflow thật là các bằng chứng khác nhau;
không dùng một bằng chứng để khẳng định toàn bộ máy Ubuntu hoặc mọi UI đều được hỗ trợ.
