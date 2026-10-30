# Multi Agents

[English](#english) | [Tiếng Việt](#tiếng-việt)

---

<a name="english"></a>
## English

Coordinate **Antigravity CLI**, **Codex CLI**, **Claude Code CLI**, and **Copilot CLI** for planning, implementation, verification, and code review. Install only the tools you need. Multi Agents runs locally, orchestrates tasks deterministically, preserves security boundaries, and requires only Python standard library and Git.

### Key Features

| Feature | Behavior |
|---|---|
| **Direct Task Dispatch** | Simply run `ma "your task"` to start, monitor live progress, and interactively accept verified changes. |
| **Live Editor Inspection** | Inspect the agent's isolated workspace in real-time while it codes using `ma open` or `ma open <path>`. |
| **Auto-Resolving Workflow ID** | Omit workflow IDs in commands (`ma status`, `ma accept`, `ma review`, `ma diff`, `ma retry`, etc.) to automatically target the latest workflow. |
| **ANSI Color Output** | Colored milestones and tables for clear status tracking (`completed` in green, `failed` in red, `waiting` in yellow). |
| **Durable Failover & Cooldowns** | Save checkpoints, switch to eligible providers, and manage provider cooldowns with `ma agents reset`. |
| **Isolated Worktrees & Verification** | Work in a temporary Git worktree, execute project verification commands (`npm test`, `pytest`), and review before applying. |
| **Native VS Code Review & Accept** | Review unified before/after diffs and accept changes all at once or file-by-file. |
| **Copilot Chat & MCP** | Submit tasks through Copilot Chat `@hub` or Hub MCP tools in connected clients. |

---

### Quick Start: setup → init → run

Requires **Git, Python >= 3.11** and at least one coding CLI (**Antigravity**, **Codex**, or **Claude**).

#### 1. Setup (Run once)

Clone into a directory and run the setup script:

**Windows — PowerShell:**
```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

**Ubuntu / Linux:**
```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

Select your preferred CLIs and integrations (such as the `ma` command launcher and VS Code `@hub` participant).

#### 2. Initialize your project

Navigate to any Git repository containing at least one commit and a working test/verification command:

```powershell
cd C:\Project\YourApp
ma init
```

Confirm the project scope and verification command when prompted.

#### 3. Dispatch a task

Dispatch directly from your terminal:

```powershell
ma "Build login form with client-side validation and write unit tests"
```

- Multi Agents watches progress live.
- When implementation and test verification pass, it prompts:
  `Apply 4 changed file(s) to project now? [Y/n]: `
- Enter `y` to apply changes immediately to your project working tree!

> [!IMPORTANT]
> **Always commit before dispatching the next task!**
> After accepting changes (`ma accept`), commit your code (`git commit -am "feat: description"`) before starting the next task. Multi Agents requires a clean Git baseline (`HEAD`) to branch isolated worktrees and guarantee uncommitted code is never overwritten.
> 
> **Standard workflow cycle:**
> ```powershell
> ma "Task 1: Add login form"
> ma accept
> git commit -am "feat: add login form"
> ma "Task 2: Add forgot password"
> ```

---

### Common CLI Commands

Run these inside your project directory (`ID` is optional and defaults to the latest workflow):

| Command | Description |
|---|---|
| `ma "<objective>"` | Dispatch a new task and follow progress live with interactive acceptance. |
| `ma status` | Show current status, milestones, and changed files for the latest workflow. |
| `ma status --watch` | Follow progress live in real time. |
| `ma open [file]` | Open the active workflow workspace or a specific file in VS Code to see agent code live. |
| `ma review [ID]` | Preview verified changes and file list before applying. |
| `ma diff [ID]` | Print the unified Git patch of generated changes. |
| `ma accept [ID]` | Apply verified changes into your project working directory. |
| `ma accept [ID] --file path` | Selectively accept specific files. |
| `ma auto-accept on` / `off` | Toggle automatic acceptance upon successful test verification. |
| `ma retry [ID]` | Resume a blocked or waiting workflow. |
| `ma cancel [ID]` | Cancel a workflow while preserving checkpoints. |
| `ma agents list` | Display status table of configured AI providers. |
| `ma agents reset [agent]` | Reset health cooldowns for all providers or a specific agent. |
| `ma doctor` | Check system diagnostics, Python, Git, and daemon status. |

---

### Copilot Chat `@hub` Commands

When using the VS Code `@hub` participant:

| Command | Purpose |
|---|---|
| `@hub <request>` | Submit work for the open project, e.g. `@hub Add forgot password form and tests`. |
| `@hub /status [ID]` | Check workflow state, call budget, and current provider. |
| `@hub /watch [ID]` | Stream live progress in VS Code. |
| `@hub /accept [ID]` | Apply completed changes to your project. |
| `@hub /retry [ID]` | Resume a blocked workflow. |
| `@hub /cancel [ID]` | Cancel the current workflow without deleting files. |
| `@hub /agents` | Check status of installed agent CLIs. |

---

<br/>

<a name="tiếng-việt"></a>
## Tiếng Việt

Điều phối linh hoạt các AI CLI hàng đầu: **Antigravity CLI**, **Codex CLI**, **Claude Code CLI** và **Copilot CLI** để tự động hóa toàn bộ quy trình: lập kế hoạch (planning), viết mã (implementation), chạy kiểm thử (verification) và đánh giá (code review). Multi Agents chạy hoàn toàn cục bộ, bảo mật ranh giới mã nguồn, sử dụng thư viện chuẩn Python và Git.

### Tính năng nổi bật

| Tính năng | Mô tả hoạt động |
|---|---|
| **Giao việc trực tiếp** | Gõ thẳng `ma "yêu cầu công việc"` để khởi chạy, theo dõi tiến trình trực quan và xác nhận nhận code `[Y/n]` ngay tại terminal. |
| **Mở Workspace xem trực tiếp code** | Dùng lệnh `ma open` hoặc `ma open <đường_dẫn_file>` để mở workspace tạm thời trong VS Code xem agent viết code theo thời gian thực. |
| **Tự động nhận diện Workflow mới nhất** | Không cần copy/paste mã ID; các lệnh `ma status`, `ma accept`, `ma review`, `ma diff`, `ma retry`... tự động chọn workflow gần nhất của dự án. |
| **Màu sắc ANSI trực quan** | Trạng thái hiển thị phân biệt bằng màu sắc rõ nét (`completed` màu xanh lá, `failed` màu đỏ, `waiting` màu vàng). |
| **Failover bền vững & Cooldown linh hoạt** | Lưu checkpoint khi gặp lỗi quota/tạm thời, tự động chuyển đổi agent và hỗ trợ xóa cooldown nhanh bằng `ma agents reset`. |
| **Cách ly an toàn trong Worktree & Tự kiểm thử** | Mọi thay đổi diễn ra trong Git worktree riêng biệt, tự động chạy lệnh test (`npm test`, `pytest`) trước khi bàn giao. |
| **Nghiệm thu linh hoạt** | Xem diff trước khi nhận, có thể chấp nhận toàn bộ (`ma accept`) hoặc từng file riêng lẻ. |
| **Hỗ trợ Chat `@hub` & MCP** | Tích hợp tiện lợi qua GitHub Copilot Chat `@hub` hoặc giao thức MCP. |

---

### Bắt đầu nhanh: setup → init → chạy tác vụ

Yêu cầu môi trường: **Git, Python >= 3.11** và ít nhất một AI CLI lập trình (**Antigravity**, **Codex**, hoặc **Claude**).

#### 1. Cài đặt ban đầu (Chỉ chạy 1 lần)

Tải repository về máy và chạy script setup:

**Trên Windows (PowerShell):**
```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

**Trên Ubuntu / Linux:**
```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

Giao diện terminal sẽ hiển thị danh sách để bạn chọn các CLI và tiện ích tích hợp (lệnh `ma`, VS Code `@hub`...).

#### 2. Khởi tạo dự án của bạn

Di chuyển vào thư mục dự án Git bất kỳ (đã có ít nhất 1 commit và có lệnh test):

```powershell
cd C:\Project\DuAnCuaBan
ma init
```

Xác nhận phạm vi source code và lệnh kiểm thử (`verify command`) theo hướng dẫn.

#### 3. Giao việc cho AI

Gõ trực tiếp yêu cầu từ cửa sổ dòng lệnh:

```powershell
ma "Thêm form quên mật khẩu, kiểm tra hợp lệ email và viết bài test"
```

- Multi Agents sẽ tự động phân tích và theo dõi tiến độ từng bước.
- Khi hoàn thành và vượt qua kiểm thử thành công, terminal sẽ hỏi:
  `Apply 4 changed file(s) to project now? [Y/n]: `
- Gõ `y` (hoặc Enter) để áp dụng ngay code mới vào dự án của bạn!

> [!IMPORTANT]
> **Bắt buộc commit code trước khi giao việc tiếp theo!**
> Sau khi nhận code (`ma accept`), hãy luôn commit thay đổi vào Git (`git commit -am "feat: mô tả"`) trước khi chạy yêu cầu kế tiếp. Multi Agents luôn dựa vào điểm mốc Git sạch (`HEAD`) để tạo worktree cách ly an toàn và đảm bảo không ghi đè lên các thay đổi dở dang của bạn.
> 
> **Chu trình làm việc chuẩn:**
> ```powershell
> ma "Task 1: Làm form đăng nhập"
> ma accept
> git commit -am "feat: add login form"
> ma "Task 2: Thêm chức năng quên mật khẩu"
> ```

---

### Bảng tra cứu lệnh CLI thường dùng

Thực thi trong thư mục dự án của bạn (`ID` là tùy chọn, mặc định lấy workflow mới nhất):

| Lệnh | Ý nghĩa |
|---|---|
| `ma "<nội dung>"` | Giao task mới và theo dõi trực tiếp, hỏi nghiệm thu khi xong. |
| `ma status` | Xem trạng thái chi tiết, các bước và danh sách file thay đổi gần nhất. |
| `ma status --watch` | Theo dõi tiến độ chạy của agent theo thời gian thực. |
| `ma open [file]` | Mở thư mục workspace hoặc file đang được agent chỉnh sửa trong VS Code. |
| `ma review [ID]` | Xem danh sách file và nội dung thay đổi trước khi nhận. |
| `ma diff [ID]` | In ra định dạng Git patch của toàn bộ thay đổi. |
| `ma accept [ID]` | Áp dụng toàn bộ code đã qua kiểm thử vào thư mục dự án. |
| `ma accept [ID] --file path` | Chỉ nhận một file cụ thể (có thể lặp lại nhiều file). |
| `ma auto-accept on` / `off` | Bật/tắt chế độ tự động nhận code ngay khi test pass thành công. |
| `ma retry [ID]` | Đánh thức và chạy tiếp workflow đang bị dừng hoặc chờ cooldown. |
| `ma cancel [ID]` | Hủy workflow hiện tại nhưng vẫn giữ nguyên checkpoint và code đã làm. |
| `ma agents list` | Liệt kê danh sách các AI CLI và trạng thái sẵn sàng. |
| `ma agents reset [tên_agent]` | Xóa trạng thái phạt cooldown cho tất cả hoặc riêng một agent. |
| `ma doctor` | Kiểm tra môi trường hệ thống, phiên bản Python, Git và tiến trình daemon. |

---

### Lệnh gọi trong Copilot Chat (`@hub`)

Nếu bạn sử dụng VS Code Copilot Chat có kết nối `@hub`:

| Lệnh | Mục đích |
|---|---|
| `@hub <yêu cầu>` | Giao task cho dự án đang mở, ví dụ: `@hub Thêm chức năng đổi mật khẩu và test`. |
| `@hub /status [ID]` | Kiểm tra trạng thái hiện tại, ngân sách cuộc gọi và agent đang xử lý. |
| `@hub /watch [ID]` | Theo dõi tiến độ trực tiếp trong khung chat. |
| `@hub /accept [ID]` | Áp dụng thay đổi đã hoàn thành vào dự án thông qua hộp thoại VS Code. |
| `@hub /retry [ID]` | Khởi động lại task sau khi khắc phục lỗi. |
| `@hub /cancel [ID]` | Hủy task đang chạy an toàn. |
| `@hub /agents` | Xem danh sách các AI agent đã được cài đặt và kích hoạt. |

---

## Giấy phép & Đóng góp (License & Contributions)

Dự án phát triển mã nguồn mở cục bộ. Mọi đóng góp, báo lỗi và ý kiến đóng góp vui lòng mở Issue hoặc Pull Request trên GitHub repository: [khang1604/multi_agents](https://github.com/khang1604/multi_agents).
