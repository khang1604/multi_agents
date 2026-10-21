# Multi Agents

[English](README.md) | **Tiếng Việt**

Điều phối Codex, Claude Code, Copilot CLI và Antigravity CLI để lập kế hoạch,
viết code, kiểm thử và review. Không cần cài đủ bốn; Codex/Claude đảm nhiệm sửa code.
Phần chính dùng Python standard library và Git.

## Tính năng

| Tính năng | Cách hoạt động |
|---|---|
| Phân vai và chọn mức công việc | Chọn công cụ phù hợp; giới hạn số lượt chạy CLI. |
| Đổi leader, chờ quota | Lưu checkpoint, chuyển công cụ đủ quyền hoặc chờ tới lịch thử lại; không tự tăng ngân sách. |
| Context chung, Handoff v2 | Bàn giao mục tiêu, việc đã thử, lý do loại hướng, ràng buộc và bước tiếp theo; kèm hash và bằng chứng test. |
| Trạng thái bền vững | SQLite lưu workflow, memory, checkpoint và trạng thái provider trên máy. |
| Worktree và verifier | Sửa trong bản làm việc riêng, chạy lệnh kiểm tra của dự án và review kết quả. |
| Xem và nhận code | Diff trong VS Code; Accept tất cả hoặc từng file. ZIP kiểm tra toàn vẹn vẫn được giữ để phục hồi. |
| Chat và MCP | Giao việc qua `@hub` trong Copilot Chat hoặc công cụ MCP của client đã kết nối. |
| Setup nhanh | Một bảng chọn CLI/kết nối, model INHERIT chung, kiểm tra đăng nhập và mở login chính thức khi cần. |

## Bắt đầu: setup → init → prompt

Cần **Git, Python >= 3.11** và ít nhất Codex CLI hoặc Claude Code CLI để sửa code.
Cài CLI cần dùng riêng; có extension IDE không có nghĩa đã có CLI.
Chỉ dùng source được phép, dữ liệu giả và API test được cho phép.

### 1. Setup một lần

Clone vào thư mục mới, rồi chạy setup tại thư mục Multi Agents:

**Windows — PowerShell:**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

**Ubuntu:**

```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

Setup mở **bảng chọn ngay trong terminal**, không tự mở cửa sổ VS Code.
Tick CLI và các mục muốn cài: lệnh `ma`, VS Code `@hub`, VS Code MCP;
Windows có thêm đánh thức hàng đợi. Chỉ mục được chọn mới được áp dụng.
INHERIT dùng model mặc định của từng CLI. Setup giữ backup cấu hình.
Kiểm tra auth không gọi model; `UNKNOWN` nghĩa là chưa xác minh, không phải chắc chắn chưa đăng nhập.
Dùng tùy chọn login chính thức trong setup nếu cần; không gửi token vào chat.

Sau khi cài/cập nhật extension Hub, chạy lệnh sau từ bất kỳ thư mục nào để
mở **giao diện Setup nhanh trong VS Code**:

```text
ma setup interface
```

Lệnh gửi yêu cầu mở màn hình, không tự áp dụng cấu hình. Cần lệnh `code` có trong
PATH và extension Hub được cài bằng cùng bản Hub/home đang dùng (profile VS Code mặc định).
Nếu chưa cài extension, chạy `ma setup` và tick **Kết nối VS Code @hub** trước.
Nếu chưa thấy màn hình, reload VS Code rồi chạy lại hoặc mở bằng Command Palette:


1. Nhấn `Ctrl+Shift+P` → **Multi Agents: Setup nhanh**.
2. Tick CLI/kết nối, chọn đăng nhập nếu cần và kiểm tra lại trạng thái.
3. Bấm **Áp dụng** một lần. Muốn chỉnh model/vai trò riêng: `ma setup --advanced`.

Sau khi cài lệnh, mở terminal mới trên Windows. Ubuntu: thêm thư mục launcher vào
PATH theo lệnh setup in ra; setup không tự sửa shell profile. Reload VS Code nếu được yêu cầu.
Nếu script không chạy, dùng `py -3 ma.py setup` (Windows) hoặc `python3 ma.py setup` (Ubuntu).

### 2. Init trong dự án

Mở repo Git đã có commit và lệnh kiểm tra chạy được, rồi chạy:

```text
ma init
```

Xác nhận đúng phạm vi source/dữ liệu khi được hỏi. Init chuẩn bị dự án, kiểm tra
verifier và kết nối; xử lý lỗi còn báo trước khi giao việc. Không chép Hub vào từng repo.

### 3. Viết prompt trong chat

Trong Copilot Chat đã cài Hub:

```text
@hub Thêm bộ lọc công việc theo trạng thái và từ khóa. Giữ cách gọi cũ, bổ sung test và review.
```

Hub trả mã công việc và tiến độ. Khi hoàn tất, chọn **Xem thay đổi** rồi
**Accept tất cả** hoặc **Accept từng file** để áp dụng vào dự án; không tự commit/push.
Chat khác cần nhận đúng công cụ MCP của Hub. Chỉ có mã công việc mới chứng minh yêu cầu đã tới Hub.

## Lệnh thường dùng

Chạy tại thư mục dự án, trừ setup/demo. `ID` là mã công việc.

| Lệnh | Công dụng |
|---|---|
| `ma setup` | Bảng chọn setup trong terminal; không tự mở giao diện VS Code. |
| `ma setup interface` | Mở giao diện Setup nhanh trong VS Code; chọn rồi bấm Áp dụng. |
| `ma setup --advanced` | Chỉnh riêng provider, model và vai trò. |
| `ma init` | Chuẩn bị hoặc kiểm tra lại dự án hiện tại. |
| `ma agents list --check` | Nhận diện CLI, kiểm tra trạng thái và lý do ngắn gọn; không gọi model. |
| `ma status --watch` / `ma logs` | Theo dõi tiến độ / xem các lượt và lỗi. |
| `ma handoff ID` | Xem bàn giao và bước tiếp theo. |
| `ma review ID` / `ma diff ID` | Liệt kê file kết quả / xem diff. |
| `ma accept ID` | Áp dụng toàn bộ kết quả hoàn tất. |
| `ma accept ID --file app/tasks.py` | Chỉ nhận file được chỉ định; có thể lặp `--file`. |
| `ma auto-accept on` / `off` / `status` | Chọn tự áp dụng riêng dự án; mặc định tắt. |
| `ma retry ID` / `ma cancel ID` | Tiếp tục trong ngân sách còn lại / dừng và giữ checkpoint. |
| `ma run "Yêu cầu của bạn"` | Giao việc qua terminal nếu muốn. |
| `ma doctor` / `ma --help` | Chẩn đoán / xem trợ giúp. |

Trong Copilot Chat dùng `@hub /agents`, `/status`, `/watch`, `/retry`, `/cancel`,
`/accept [ID]`, `/autoaccept on|off|status`. Với lệnh workflow, thêm ID để chọn việc cụ thể;
bỏ ID sẽ chọn việc gần nhất của dự án. Dừng theo dõi không hủy công việc.

Thử không gọi AI tại thư mục Multi Agents:

```bash
python3 ma.py demo --simulate
```

Windows thay `python3` bằng `py -3`. Demo giả lập provider, vẫn dùng Git và chạy test thật.

## Trạng thái và đóng góp

Dự án đang hoàn thiện; không cam kết mọi client hoặc máy đều chạy trơn tru.
Chat host hết quota có thể chặn prompt trước khi tới Hub; MCP không vượt qua được giới hạn đó.
Task đã tới Hub có thể chuyển CLI khác còn dùng được. Số lượt tính theo lần chạy CLI,
không phải số token hoặc chi phí chính xác. Ubuntu và Windows có bằng chứng kiểm thử riêng.

Đọc [kết quả kiểm chứng](VERIFICATION.md), [lỗi đã sửa và việc cần đóng góp](docs/KNOWN_ISSUES.md),
[hướng dẫn đóng góp](CONTRIBUTING.md), [Handoff v2](docs/HANDOFF.md) và [hướng dẫn chi tiết](docs/V2_GUIDE.md).
Đọc [global rules](GLOBAL_RULES.md) và [bảo mật](docs/SECURITY.md) trước khi chạy thật:
không dùng dữ liệu thật/secrets, giữ sandbox của CLI; cách ly OS khi người dùng yêu cầu.

Phát triển từ ý tưởng cá nhân và tham khảo [Maestro](https://github.com/RunMaestro/Maestro),
[agent-intern](https://github.com/SinanTufekci/agent-intern),
[Agent Deck](https://github.com/asheshgoplani/agent-deck),
[AI Maestro](https://github.com/23blocks-OS/ai-maestro).
