# Multi Agents

[English](#english) | [Tiếng Việt](#tiếng-việt)

---

<a name="english"></a>

## English

**Multi Agents** is a lightweight, local multi-agent orchestrator that coordinates **Antigravity CLI**, **GitHub Copilot CLI**, **OpenAI Codex CLI**, and **Claude Code CLI** for automated planning, implementation, verification, and code review.

- **100% Local & Zero Bloat:** Requires only Python standard library (>= 3.11) and Git. No heavy runtime dependencies.
- **Isolated Worktrees:** All agent changes occur inside a detached Git worktree; your active project files remain untouched until you accept.
- **Automated Verification:** Runs your project's test suite (`npm test`, `pytest`, etc.) automatically before delivery.
- **Failover Resilience:** Automatically switches to an alternate available agent if one hits a quota limit or error.

---

### 🚀 3-Step Quick Start (1 Minute)

#### Step 1: Install once

Clone the repository and run the setup script:

**Windows (PowerShell or Command Prompt):**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
# Or double-click setup.cmd
```

**Linux / macOS:**

```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

_The setup automatically configures your `PATH` and creates launcher shims. Open a new terminal to start using `ma`._

#### Step 2: Dispatch a task in any project

Navigate to any project directory (Git or non-Git) and run your task directly:

```powershell
cd C:\Project\YourApp
ma "Add user profile page with avatar upload and automated tests"
```

#### Step 3: Accept verified changes

1. Multi Agents coordinates the agents:
   - **Planner** (e.g., Antigravity) analyzes requirements and builds the execution plan.
   - **Worker** (e.g., Copilot / Codex / Claude) writes the code.
   - **Verifier** runs your local tests automatically (`Tests: X/X passed`).
2. When completed, simply confirm:
   ```text
   Apply 4 changed file(s) to project now? [Y/n]: y
   ```
   _(Or type `ma accept` anytime)_. The changes are immediately merged into your project!

---

### 🛠️ Common Scenarios & How-To

- **Inspect code while the agent is typing:**
  Run `ma open` to open the agent's live temporary workspace in VS Code.
- **Review changes before accepting:**
  Run `ma diff` to inspect the full Git patch of generated code.
- **When status shows `Needs review`:**
  If changes are large, Multi Agents avoids wasting AI tokens and pauses safely for your review. Run `ma diff` to inspect, then `ma accept` to apply.
- **Provider quota exhaustion or network timeout:**
  - `ma agents reset`: Clears cooldown penalties for all agents.
  - `ma retry`: Resumes the paused workflow immediately.
- **Check system health:**
  Run `ma doctor` to verify Python, Git, and installed agent CLIs.

---

### 📋 CLI Command Reference

_All commands automatically target the latest workflow if no `[workflow_id]` is provided._

| Command                       | Description                                                                  |
| ----------------------------- | ---------------------------------------------------------------------------- |
| **`ma "<prompt>"`**           | Dispatch a new task, watch live execution, and interactively accept results. |
| **`ma status`**               | Display current workflow state, active agent, and modified files.            |
| **`ma watch`**                | Follow live progress in real time.                                           |
| **`ma open [file]`**          | Open the isolated worktree or a specific file in VS Code.                    |
| **`ma diff`**                 | Print the unified Git patch of all pending changes.                          |
| **`ma accept`**               | Apply completed, verified changes to your working project.                   |
| **`ma accept --file <path>`** | Selectively apply specific files only.                                       |
| **`ma auto-accept on / off`** | Toggle automatic acceptance upon successful test verification.               |
| **`ma retry`**                | Immediately resume a paused, waiting, or failed workflow.                    |
| **`ma cancel`**               | Safely cancel the running workflow while preserving progress checkpoints.    |
| **`ma agents list`**          | List all configured AI CLI providers and their readiness status.             |
| **`ma agents reset`**         | Clear cooldown locks for all providers (or a specific provider).             |
| **`ma doctor`**               | Diagnose system setup, Python version, Git path, and agent availability.     |
| **`ma setup`**                | Open interactive CLI configuration dashboard.                                |

---

### 💬 VS Code Copilot Chat (`@hub`) Integration

If you enabled the VS Code Chat Participant during setup:

| Command        | Action                                                                   |
| -------------- | ------------------------------------------------------------------------ |
| `@hub <task>`  | Dispatch a task directly from VS Code chat (e.g. `@hub Add unit tests`). |
| `@hub /status` | Check current workflow state and agent milestones.                       |
| `@hub /watch`  | Stream live task execution inside the chat pane.                         |
| `@hub /accept` | Apply verified changes with one click.                                   |
| `@hub /retry`  | Resume a waiting or failed workflow.                                     |
| `@hub /agents` | View status of installed agent CLIs.                                     |

---

<br/>

<a name="tiếng-việt"></a>

## Tiếng Việt

**Multi Agents** là công cụ điều phối đa tác tử (Multi-Agent Orchestrator) cục bộ, kết hợp sức mạnh của **Antigravity CLI**, **GitHub Copilot CLI**, **OpenAI Codex CLI** và **Claude Code CLI** để tự động hóa toàn bộ quy trình: lập kế hoạch (planning), viết mã (implementation), chạy kiểm thử (verification) và đánh giá (review).

- **100% Cục bộ & Nhẹ nhàng:** Chỉ sử dụng thư viện chuẩn của Python (>= 3.11) và Git. Không cài đặt thư viện ngoài cồng kềnh.
- **An toàn tuyệt đối với Git Worktree:** Mọi thay đổi code diễn ra trong thư mục nhánh tạm thời; mã nguồn chính của bạn không bị ảnh hưởng cho đến khi bạn đồng ý nhận code.
- **Tự động chạy bài kiểm thử:** Tự động kích hoạt test suite của dự án (`npm test`, `pytest`, v.v.) và chỉ bàn giao khi bài test vượt qua.
- **Tự phục hồi lỗi (Failover):** Tự động chuyển giao công việc cho agent khác nếu một agent gặp lỗi quota, mạng hoặc format.

---

### 🚀 Bắt Đầu Nhanh 3 Bước (Chỉ 1 Phút)

#### Bước 1: Cài đặt (Chỉ chạy 1 lần duy nhất)

Tải repository về máy và chạy script cài đặt:

**Trên Windows (PowerShell hoặc Command Prompt):**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
# Hoặc nhấp đúp vào setup.cmd
```

**Trên Linux / macOS:**

```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

_Script cài đặt sẽ tự động thiết lập đường dẫn `PATH` vào hệ thống. Sau khi cài xong, hãy mở cửa sổ terminal mới để sử dụng lệnh `ma`._

#### Bước 2: Giao việc tại bất kỳ dự án nào

Mở terminal tại thư mục dự án của bạn (hỗ trợ cả Git và non-Git) và giao việc trực tiếp:

```powershell
cd C:\Project\DuAnCuaBan
ma "Tạo trang thông tin người dùng với chức năng upload avatar và viết unit test"
```

#### Bước 3: Nghiệm thu & nhận code

1. Hệ thống tự động phối hợp các agent:
   - **Planner** (ví dụ: Antigravity) phân tích yêu cầu tiếng Việt và lập kế hoạch kỹ thuật.
   - **Worker** (ví dụ: Copilot / Codex / Claude) bắt tay vào viết mã nguồn.
   - **Verifier** tự động chạy test kiểm thử tại máy của bạn (`Tests: 1/1 passed`).
2. Khi hoàn tất, terminal sẽ hỏi bạn xác nhận:
   ```text
   Apply 4 changed file(s) to project now? [Y/n]: y
   ```
   _(Hoặc bạn có thể gõ `ma accept` bất kỳ lúc nào)_. Toàn bộ code đã test sạch sẽ được áp dụng ngay vào dự án của bạn!

---

### 🛠️ Các Tình Huống Thực Tế & Cách Xử Lý

- **Xem trực tiếp code khi agent đang gõ:**
  Gõ lệnh `ma open` để mở workspace tạm thời trong VS Code xem agent viết code theo thời gian thực.
- **Xem lại thay đổi (diff) trước khi nhận:**
  Gõ lệnh `ma diff` để in toàn bộ nội dung thay đổi dạng Git patch.
- **Khi terminal hiện dòng `Needs review`:**
  Khi số lượng code thay đổi lớn, hệ thống chủ động tạm dừng để tránh tốn token AI và nhường quyền kiểm tra cho bạn. Bạn chỉ cần gõ `ma diff` để xem và gõ `ma accept` để áp dụng code.
- **Khi agent hết quota hoặc lỗi kết nối tạm thời:**
  - `ma agents reset`: Xóa thời gian chờ phạt cooldown cho các agent.
  - `ma retry`: Kích hoạt workflow tiếp tục chạy ngay lập tức.
- **Kiểm tra sức khỏe hệ thống:**
  Gõ `ma doctor` để kiểm tra môi trường Python, Git và các CLI AI đã sẵn sàng.

---

### 📋 Bảng Tra Cứu Lệnh Thường Dùng

_Mọi câu lệnh đều tự động nhận diện workflow gần nhất nếu bạn không truyền `[workflow_id]`._

| Lệnh                               | Mô tả                                                                |
| ---------------------------------- | -------------------------------------------------------------------- |
| **`ma "<yêu cầu>"`**               | Giao việc mới, theo dõi trực tiếp và hỏi nghiệm thu khi xong.        |
| **`ma status`**                    | Xem trạng thái hiện tại, agent đang chạy và danh sách file thay đổi. |
| **`ma watch`**                     | Theo dõi tiến độ chạy của agent theo thời gian thực.                 |
| **`ma open [tên_file]`**           | Mở workspace tạm thời hoặc file đang chỉnh sửa trong VS Code.        |
| **`ma diff`**                      | In toàn bộ nội dung thay đổi code dạng Git diff.                     |
| **`ma accept`**                    | Áp dụng toàn bộ code đã vượt qua bài test vào dự án.                 |
| **`ma accept --file <đường_dẫn>`** | Chỉ nhận riêng một file cụ thể.                                      |
| **`ma auto-accept on / off`**      | Bật/tắt chế độ tự động nhận code ngay khi test pass.                 |
| **`ma retry`**                     | Đánh thức và tiếp tục chạy workflow đang tạm dừng hoặc chờ cooldown. |
| **`ma cancel`**                    | Hủy workflow an toàn mà không làm mất checkpoint đã làm.             |
| **`ma agents list`**               | Kiểm tra danh sách và trạng thái của các AI CLI đã cài đặt.          |
| **`ma agents reset`**              | Xóa thời gian chờ phạt cooldown cho tất cả (hoặc riêng 1 agent).     |
| **`ma doctor`**                    | Chẩn đoán môi trường Python, Git và kết nối của các agent.           |
| **`ma setup`**                     | Mở bảng điều khiển cấu hình trực quan của hệ thống.                  |

---

### 💬 Sử Dụng Trong VS Code Copilot Chat (`@hub`)

Nếu bạn bật tích hợp VS Code Chat Participant trong quá trình setup:

| Lệnh             | Tác vụ                                                                        |
| ---------------- | ----------------------------------------------------------------------------- |
| `@hub <yêu cầu>` | Giao việc ngay trong khung chat VS Code (ví dụ: `@hub Thêm trang dashboard`). |
| `@hub /status`   | Xem tiến độ, trạng thái và agent đang xử lý.                                  |
| `@hub /watch`    | Theo dõi quá trình xử lý trực tiếp trong chat.                                |
| `@hub /accept`   | Nhận code vào dự án thông qua thông báo VS Code.                              |
| `@hub /retry`    | Chạy lại tác vụ khi cần.                                                      |
| `@hub /agents`   | Xem danh sách các AI agent đã kích hoạt.                                      |

---

## Giấy phép & Đóng góp (License & Contributions)

Dự án được phát triển mã nguồn mở cục bộ. Mọi đóng góp, báo lỗi và ý kiến đóng góp vui lòng mở Issue hoặc Pull Request trên GitHub: [khang1604/multi_agents](https://github.com/khang1604/multi_agents).
