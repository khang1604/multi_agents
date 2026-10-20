# Multi Agents

Hub mã nguồn mở điều phối Antigravity, Claude, Codex và Copilot qua CLI đã đăng nhập.
Bạn giao việc trong chat; Hub chọn agent, giữ tiến độ, kiểm tra thay đổi và đổi leader
khi lỗi/quota. Core dùng Python standard library + Git; không cần cài đủ provider.

Lấy cảm hứng từ [Maestro](https://github.com/RunMaestro/Maestro),
[agent-intern](https://github.com/SinanTufekci/agent-intern),
[agent-deck](https://github.com/asheshgoplani/agent-deck) và
[AI Maestro](https://github.com/23blocks-OS/ai-maestro), kết hợp ý tưởng cá nhân:
setup một lần, init một lệnh, giao việc trong chat; tự đổi leader, giữ checkpoint
và giới hạn lượt CLI để giảm thao tác và lãng phí quota.

**Đang phát triển — chưa hoàn thành.** Chỉ nghiệm thu khi **setup → init → prompt**
chạy trơn tru trên Windows/Ubuntu và mọi khung chat mục tiêu khi chat còn hoặc hết
quota. Hiện chưa có bằng chứng đạt toàn bộ tiêu chí này.

## Dùng theo 3 bước

Cần Git, Python ≥ 3.11 và một coding CLI Codex/Claude đã đăng nhập. Chỉ dùng source
được phép, dữ liệu giả và API test đã khai báo; đọc [quy tắc](GLOBAL_RULES.md).

**1. Setup global một lần — Windows:**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

Chọn agent, model policy chung, cài lệnh `ma` và bridge `@hub` cho VS Code Copilot
Chat. Setup kiểm tra CLI đã chọn; bấm số để đăng nhập chính thức ngay tại setup,
bấm 0 để tiếp tục. CLI chưa hỗ trợ probe auth giữ UNKNOWN; không tự nhận đã đăng nhập.
Setup có backup. Mở lại IDE/terminal sau khi cài.

**2. Vào project được phép, chạy một lệnh:**

```powershell
cd 'C:\Projects\MyApp'
ma init
```

Xác nhận scope một lần cho project. Init nhận diện verifier/SDK, probe sandbox Codex
Windows không gọi model, chạy baseline trong worktree riêng và kiểm tra MCP. Cần
commit sạch và dependency sẵn sàng; thiếu thì báo nguyên nhân trước khi gọi AI.
Không tự commit source hoặc tắt sandbox để chạy tiếp.

**3. Nhập trong Copilot Chat:**

```text
@hub Thêm tài liệu hướng dẫn chạy dự án. Kiểm tra thay đổi bằng verifier đã cấu hình.
```

`@hub` gửi trực tiếp tới Hub, không gọi model chat trung gian. Bridge đã cài/test
stdio; UI thật và tình huống chat hết quota vẫn cần kiểm chứng. Chưa bảo đảm khung
chat riêng Antigravity khi hết quota. Ubuntu còn cần hoàn thiện launcher global và
kiểm thử lại bản hiện tại.

## Tính năng hiện có

| Tính năng | Hiện trạng |
|---|---|
| Planner, worker, reviewer | Antigravity/Claude/Codex/Copilot plan/review; Codex/Claude sửa code |
| Tự đổi leader và chờ quota | Cooldown, reset time, checkpoint; không retry vô hạn |
| Auto mức công việc và budget | Small/standard/complex; giới hạn lượt CLI, không tự tăng |
| SQLite, memory, handoff | Giữ tiến độ và context có hash, giảm đọc lặp |
| Worktree, verifier, review, ZIP | Source gốc tách biệt; kiểm tra và bàn giao trước cleanup |
| Init project | Scope riêng, Gradle lồng thư mục, verifier/SDK, baseline và MCP |
| CLI gọn | Trạng thái/lý do ngắn; `--json` tùy chọn |
| Đăng nhập trong setup | Menu số cho CLI đã chọn; quay lại kiểm tra sau login, không đọc token |
| Kết quả trong chat | Hiện báo cáo đã lưu, finding, verifier và phần review còn mở khi hết budget |
| Trạng thái tự động | Probe chính thức + phản hồi CLI đã lưu, khớp binary/model; quota hiển thị riêng |
| Chờ quota và đánh thức | Lịch bền vững, khôi phục khi Hub chạy lại; không gọi sớm hoặc tự tăng lượt |
| Chat `@hub` | Bridge VS Code Copilot; chưa nghiệm thu UI/quota và mọi IDE |
| Windows/Ubuntu | Windows: Codex CLI 0.163.0 đã chạy sandbox khi desktop mở. Ubuntu: bản mới chưa test |

## Lệnh và cách dùng

| Lệnh | Công dụng |
|---|---|
| `ma setup` | Chạy lại setup global khi cần thay cấu hình/cài đặt |
| `ma init` | Chuẩn bị project hiện tại; lần đầu hoặc sau khi sửa môi trường |
| `@hub <prompt>` | Giao việc trong Copilot Chat với budget Auto |
| `@hub /agents` | Xem agent, không gọi model |
| `@hub /status` | Xem workflow gần nhất của project |
| `@hub /watch` | Theo dõi; dừng chat chỉ đóng theo dõi |
| `@hub /retry` | Tiếp tục sau sửa lỗi, giữ nguyên call cap |
| `@hub /cancel` | Dừng workflow, giữ checkpoint/code |
| `ma agents list --check` | Probe CLI chính thức; READY không bảo đảm còn quota |
| `ma retry ID --at "2026-10-25T13:21:00+07:00" --request-key wake-ID` | Hẹn tiếp tục checkpoint, giữ trần lượt; `--extra-calls N` chỉ khi người dùng cấp thêm |
| `ma wake` / `ma wake --install --apply` | Kiểm tra hàng đợi không gọi AI / cài đánh thức nền Windows mỗi 5 phút, cần máy bật và user đăng nhập |
| `ma doctor` | Chẩn đoán khi setup/init báo lỗi |
| `ma integrations chat --apply` | Cài thêm @hub nếu đã setup bản cũ |
| `ma integrations install CLIENT --apply` | Cấu hình MCP client có backup |
| `ma init --verify-command EXECUTABLE ARGS` | Chọn verifier; đặt option này cuối |
| `ma init --replace-verify --verify-command EXECUTABLE ARGS` | Sửa verifier cũ có backup |
| `ma init --register-only` | Chỉ đăng ký/refresh; không test baseline, không báo ready |
| `ma status --watch` / `ma logs` / `ma diff` | Xem tiến độ, lỗi, thay đổi ngoài chat |
| `ma --help` | Toàn bộ lệnh; thêm `--json` cho script |

Lệnh chat có thể thêm ID, ví dụ `@hub /status abc123`. Project đang có workflow thì
không tạo task trùng. Provider vẫn cần quota riêng để chạy AI.

## Đóng góp

Xem [lỗi đã sửa và phần cần đóng góp](docs/KNOWN_ISSUES.md),
[hướng dẫn + prompt đầu tiên cho agent](CONTRIBUTING.md) và
[bằng chứng kiểm thử](VERIFICATION.md). Ưu tiên hoàn thiện 3 bước trước khi thêm tính năng.
