# Multi Agents V2 — terminal-first

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1

cd C:\Projects\MyApp
ma init
ma
```

V2 mở rộng engine hiện có, không có GUI/web server. `ma` dùng dữ liệu local ngoài
repository, mặc định `%LOCALAPPDATA%\MultiAgents` trên Windows. `ma init` đăng ký source
được phép và tạo context có hash/version; không tạo AGENTS.md, .gitignore, MCP config
hoặc metadata trong repo. `ma` không có tham số mở menu; `ma --help` xem toàn bộ lệnh.

Setup kiểm tra Python >=3.11/Git, phát hiện executable, cho chọn agent bằng Space/Enter
trong Windows Terminal (terminal đơn giản có nhập tên thay thế), model policy và vai trò.
Cài PATH và cấu hình client chỉ thực hiện sau lựa chọn rõ ràng, có backup/ownership và
rollback. Không tự cài/login provider, đổi security flags hay bật chạy cùng Windows.

`ma agents list` chỉ phát hiện executable. `ma agents list --check` dùng lệnh version,
help và auth-status chính thức khi có; không gọi model. `READY` nghĩa là probe auth và
giao thức adapter đạt, **không** chứng minh quota hay live execution. Copilot/Antigravity
auth chưa có probe noninteractive được triển khai thì báo `UNKNOWN`. IDE đã cài không
đồng nghĩa CLI đã cài/đăng nhập. Mỗi provider giữ đăng nhập của chính nó.

```powershell
ma agents configure
ma agents models
ma agents disable copilot
ma agents model codex INHERIT
ma doctor
ma run "Thêm tính năng lọc với kiểm thử" --max-calls 6
ma status --watch
ma logs
ma diff
```

`INHERIT` không truyền model; model IDE có thể khác CLI. `AUTO` chỉ dùng khi adapter có
hỗ trợ đã khai báo; hiện Copilot hỗ trợ `auto`, provider khác cần cho phép fallback
INHERIT. `MANUAL` chỉ nhận model từ catalog provider được probe trả về, không hardcode
danh sách model; catalog chưa xác định thì dùng INHERIT hoặc fallback được chọn rõ.
Model thực dùng chỉ ghi khi CLI trả metadata. [Hướng dẫn V2](docs/V2_GUIDE.md) giải thích
setup, scope project, MCP, migration, monitoring và các giới hạn chưa live-verify.

MCP dùng cùng một Hub/SQLite cho Antigravity, VS Code Copilot, Codex, Claude hoặc CLI
Copilot khi client thực tế hỗ trợ. `ma integrations install CLIENT` preview;
thêm `--apply` để cập nhật cấu hình user ngoài repo có backup. Refresh client, gọi
`projects_list` rồi `recover_context`; client hỗ trợ MCP không đồng nghĩa provider
có thể chạy coding. [Bảo mật](docs/SECURITY.md) và xác nhận dữ liệu vẫn bắt buộc;
cách ly OS theo lựa chọn của người dùng, không tự khai báo đã cách ly.

Chưa chạy provider live hoặc test tương tác IDE cho V2. Không tuyên bố kết nối client
hoạt động chỉ vì đã sinh cấu hình. [Audit/kế hoạch](docs/V2_IMPLEMENTATION_PLAN.md),
[kiến trúc](docs/ARCHITECTURE.md) và [kiểm chứng](VERIFICATION.md).

## Tương thích V1: `hub` và dữ liệu cũ

`hub.py`, `hub.cmd`, `Start-Hub.cmd` và menu cũ được giữ. `hub.py init` vẫn khởi tạo
home cũ; **khác với `ma init`** đăng ký project hiện tại. Không tự chuyển `data/` cũ.
Muốn dùng V2 với state cũ, đặt `--home` tới home bên ngoài source repo hoặc dùng
`ma --home EXTERNAL_PATH migrate --from OLD_HOME` vào thư mục trống, sau khi dừng daemon
và xử lý worktree còn tồn tại. Migration sao chép, giữ nguyên dữ liệu cũ làm backup.
Phần dưới mô tả các lệnh và đường dẫn của giao diện V1.

# Agent Hub Private (V1 interface)

Bộ điều phối agent cá nhân, chạy cục bộ trên máy bạn. Dành cho quy trình:
**Antigravity suy nghĩ/lập kế hoạch → Codex triển khai → test bằng chương trình → Claude/Copilot review**.
Leader được thay thế khi CLI lỗi, timeout hoặc hết quota; công việc và bộ nhớ nằm trên đĩa.
Không cần tài khoản Hub, dịch vụ cloud của Hub hay API key mới. Từng CLI dùng đăng nhập của chính nó.

Bản 0.1 tập trung vào CLI, menu terminal và MCP. Chưa có giao diện desktop đồ họa.
Windows 10/11 + Python 3.11+ + Git; Linux dùng Python 3.11+ + Git.

## Cài đặt và dùng thử nhanh trên Windows

Mở PowerShell (đã cài Git và Python 3.11+):

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
python hub.py init
python hub.py demo --simulate
```

Demo tự tạo repo synthetic, mô phỏng lỗi quota của leader, chuyển leader, sửa code,
chạy test và xuất ZIP. **Không gọi AI, không tốn quota**. Không cần `pip install`.
Xem kết quả JSON: workflow `completed`, test pass và đường dẫn deliverable.
Nếu máy chỉ nhận `py -3`, dùng `py -3` thay cho `python`.

Trước khi chạy AI thật, đọc [GLOBAL_RULES.md](GLOBAL_RULES.md) và
[docs/SECURITY.md](docs/SECURITY.md). Mặc định Hub **chặn workflow thật** cho đến khi
người vận hành xác nhận chỉ chứa dữ liệu synthetic. Cách ly OS chỉ bắt buộc khi
người dùng yêu cầu (`security.require_isolation: true`). Không tự khai báo dữ liệu
giả hoặc đã cách ly để bỏ qua lỗi; xem docs/SECURITY.md về config cũ.

```powershell
# Xem các đường dẫn global rules, chưa sửa file:
python scripts/install_global_rules.py
# Cài rules vào 4 CLI, có backup file cũ:
python scripts/install_global_rules.py --apply
```

## Prompt cài đặt và chạy thử trên Windows

Dán toàn bộ prompt dưới đây vào agent có quyền dùng terminal trên máy Windows.
Bạn có thể thay thư mục `D:\Tools\multi_agents` trước khi gửi. Prompt này cho phép
cài Hub, cài global rules có backup và chạy mô phỏng; chưa cho phép gọi AI có phí.

```text
Hãy trực tiếp cài đặt và chạy thử dự án cá nhân này trên Windows 10/11:
https://github.com/khang1604/multi_agents.git

Thư mục đích: D:\Tools\multi_agents. Nếu không có ổ D:, dùng
%USERPROFILE%\Documents\multi_agents và báo lại đường dẫn thực tế.

Thực hiện lần lượt:
1. Kiểm tra Windows, PowerShell, Git và Python >= 3.11 bằng lệnh version.
   Ưu tiên python; nếu không dùng được, thử py -3 và dùng cùng một interpreter
   cho các bước tiếp theo. Chưa có Git/Python thì hướng dẫn hoặc cài từ nguồn
   chính thức nếu quyền hiện tại cho phép; không tự nâng quyền admin hay tắt
   chính sách bảo mật. Không cần cài package pip cho Hub.
2. Clone repo vào thư mục đích nếu chưa tồn tại. Nếu đã có, kiểm tra đúng remote
   và git status; giữ mọi thay đổi có sẵn, không reset/clean/ghi đè. Chỉ cập nhật
   bằng fast-forward khi working tree sạch; có xung đột thì báo rõ và dừng cập nhật.
3. Đọc AGENTS.md, GLOBAL_RULES.md và docs/SECURITY.md. Chỉ thao tác source của Hub
   và fixture giả lập do demo tạo. Không mở .env, secrets, token, dữ liệu người dùng,
   backup/DB thật hoặc quét các thư mục cá nhân. Không in biến môi trường hàng loạt.
4. Tại root repo, chạy lần lượt, kiểm tra exit code sau từng lệnh:
   python hub.py init
   python -m unittest discover -s tests -v
   python hub.py demo --simulate
   Thay python bằng py -3 nếu đã chọn interpreter đó. Nếu lỗi, chẩn đoán trong
   phạm vi repo và sửa tối thiểu; không tắt sandbox hoặc bật --network để né lỗi.
5. Cài global rules bằng script có sẵn; tôi cho phép cập nhật các file rule được
   script liệt kê và tạo backup, giữ nguyên nội dung khác:
   python scripts/install_global_rules.py
   python scripts/install_global_rules.py --apply
   Chỉ truy cập đúng các file instruction cần thiết, không đọc cấu hình đăng nhập.
6. Sinh cấu hình MCP bằng python hub.py mcp-config. Hiển thị khối JSON để tôi ghép
   server agent-hub-private vào Antigravity, giữ nguyên server khác. Không tự mở
   hoặc in cấu hình toàn cục có thể chứa secrets. Cho tôi biết cần refresh MCP
   và khởi động chat agent mới để nạp global rules.
7. Chưa cài hoặc đăng nhập CLI AI cũng phải chạy được demo --simulate. Không tự
   đăng nhập, đọc credential, gọi model thật, bật autostart hoặc giao task có phí.
   Giữ security.isolated_test_environment và synthetic_data_only ở false trong bước
   cài đặt. Khi tôi muốn thử AI thật, cần tôi xác nhận dữ liệu synthetic; chỉ yêu cầu
   cách ly OS nếu tôi yêu cầu. Không tự khai báo đã cách ly; xem docs/SECURITY.md.
8. Cài lệnh dùng từ folder dự án bằng scripts/install-command.ps1; tôi cho phép
   thêm đúng thư mục Hub vào PATH của user hiện tại, không sửa PATH hệ thống.
   Nếu policy chặn script thì không bypass: hướng dẫn gọi hub.cmd bằng đường dẫn
   tuyệt đối. Không chạy hub here trong folder cá nhân tùy ý; chỉ chạy khi tôi
   chỉ định source project được phép. Lệnh này không khởi chạy AI.
9. Báo kết quả ngắn: đường dẫn cài, interpreter/version, số test pass/fail,
   workflow demo có completed không, vị trí ZIP deliverable, backup rules và bước
   tiếp theo. Chỉ báo thành công dựa trên output thực tế; phần chưa chạy phải ghi rõ.

Nếu terminal không có quyền hoặc thiếu công cụ, chỉ rõ bước bị chặn và đưa lệnh
PowerShell cụ thể để tôi tự chạy. Không khẳng định đã cài khi chưa thực hiện.
```

## Tự nhận diện dự án từ CMD/PowerShell: `hub here`

Cài Hub một lần tại thư mục cố định. Thêm lệnh `hub` vào PATH người dùng bằng
PowerShell (không cần admin):

```powershell
& "D:\Tools\multi_agents\scripts\install-command.ps1"
```

Mở terminal mới, vào folder dự án rồi chạy:

```bat
cd /d D:\Projects\my-app
hub here
```

Trong PowerShell, dùng `cd D:\Projects\my-app` thay cho `cd /d`.
Không muốn chỉnh PATH hoặc máy chặn script PowerShell? Gọi trực tiếp từ folder dự án:

```bat
D:\Tools\multi_agents\hub.cmd here
```

Nếu đường dẫn Hub có khoảng trắng, CMD dùng `"D:\My Tools\multi_agents\hub.cmd" here`;
PowerShell dùng `& "D:\My Tools\multi_agents\hub.cmd" here`.

`here` tìm Git root kể cả khi đang ở thư mục con. Lần đầu đăng ký tên dạng
`my-app-<hash đường dẫn>`; lần sau nhận lại đúng project và trả memory/tiến độ gần đây.
Không ghi file vào repo, không tự git init, không chạy test hoặc gọi AI.
Repo chưa commit/sạch vẫn nhận diện được; muốn chạy workflow sau đó phải có baseline sạch.
Không tự đổi project khi trùng tên hoặc ghi đè cấu hình đã đăng ký.

Hub chỉ dùng Git root và **tên file được Git theo dõi**, không đọc nội dung source,
.env hay package scripts để nhận diện. Có gợi ý pytest/unittest, Go, Rust và .NET.
Đây là gợi ý, chưa phải lệnh test đã xác minh; Python dùng pytest nhưng không có marker
pytest có thể bị gợi ý unittest, hãy khai báo `--verify` ngay lần đăng ký đầu.
Node, monorepo nhiều hệ test hoặc dự án không rõ cần chỉ định lệnh test:

```bat
hub here --name my-app --verify "[[\"node\",\"--test\"]]"
```

Ví dụ trên dành cho CMD. Với PowerShell 7 dùng:

```powershell
hub here --name my-app --verify '[["node","--test"]]'
```

Nếu PowerShell trên máy làm mất quote khi gọi file `.cmd`, gọi Python trực tiếp:

```powershell
python D:\Tools\multi_agents\hub.py here --name my-app --verify '[["node","--test"]]'
```

Nếu vẫn lỗi JSON trên PowerShell cũ, dùng cách đăng ký bằng Python trong
[docs/WINDOWS.md](docs/WINDOWS.md). Không đoán lệnh test hoặc dùng lệnh luôn trả thành công.
`here` giữ nguyên cờ security. Chỉ dùng trong source được phép; tự nhận diện không có nghĩa
đã cách ly hay được phép gọi API thật.

Sau khi đã xác nhận dữ liệu synthetic và các điều kiện bảo mật được yêu cầu, giao việc bằng tên
project mà `hub here` trả về, hoặc dùng MCP trong Antigravity:

```bat
hub run my-app "Them tinh nang loc cong viec" --request-key filter-1
hub recover my-app
```

`hub run` ở đây dùng tên đã đặt bằng `--name my-app`. Mặc định `hub here` chỉ đăng ký/
khôi phục trạng thái; không tự tiếp tục workflow hoặc khởi chạy daemon. Với workflow bị chặn,
xử lý nguyên nhân rồi dùng `hub retry WORKFLOW_ID`; không tạo task trùng.

## Menu và chạy AI sau khi chuẩn bị môi trường test

1. Giải nén dự án vào thư mục cố định, ví dụ `D:\Tools\AgentHubPrivate`.
2. Cài Python 3.11+ và Git nếu chưa có. Cài/đăng nhập ít nhất Codex CLI.
   Claude Code, Copilot CLI và Antigravity CLI là tùy chọn. Cài IDE Antigravity
   không tự có nghĩa là lệnh `agy` đã nằm trong PATH.
3. Hoàn tất ranh giới bảo mật theo docs/SECURITY.md. Mở `Start-Hub.cmd`. Chọn **1** để kiểm tra, **8** để xem demo không gọi model,
   **2** để tạo dự án mẫu. Các mục menu chỉ gọi AI khi bạn giao một công việc thật.
4. Chọn **7** lấy cấu hình MCP riêng cho máy này; ghép server `agent-hub-private`
   vào MCP config của Antigravity. Giữ nguyên các server khác, rồi refresh MCP.
5. Dán nội dung [ANTIGRAVITY_PROMPT.md](ANTIGRAVITY_PROMPT.md) vào chat Antigravity.

Có thể dùng PowerShell trực tiếp:

```powershell
python hub.py init
python hub.py doctor
python hub.py demo --simulate
python hub.py demo
python hub.py mcp-config
# Chỉ chạy sau khi xác nhận synthetic và cách ly nếu người dùng yêu cầu:
python hub.py run demo --task-file examples/todo/TASK.md --request-key todo-filter-1
python hub.py status --watch
```

Nếu lệnh trên máy bạn là `py -3`, thay `python` bằng `py -3`.
Chỉ sửa tiêu đề README trong smoke test đã được thực hiện sẵn trên máy phát triển;
không có token hoặc tài khoản nào được đóng gói trong bản ZIP.

## Auto: dùng nhiều hay ít tùy việc

| Mức Auto | Luồng | Trần lượt chạy CLI | Sửa tự động |
|---|---|---:|---:|
| Nhỏ: chính tả/tài liệu ngắn | Worker → test; bỏ AI planner/reviewer | 2 | 0 vòng |
| Thường | Leader lập kế hoạch → worker → test → 1 reviewer | 6 | 1 vòng |
| Phức tạp: auth, payment, DB… | Kế hoạch → worker → test → 2 reviewer khác provider | 9 | 1 vòng |

Quy tắc local chọn mức ban đầu. Planner có thể nâng lên mức phức tạp; không tự tăng
trần gọi CLI đã cấp. Thiếu reviewer thứ hai thì dừng ở `needs_review`, không giả vờ đủ agent.
Nếu chỉ cài Codex, các vai trò có thể dùng Codex ở các phiên riêng; đó không phải review từ
hai model family độc lập. Có thể ép `--mode standard` hoặc `--max-calls 4`.

Một lượt CLI có thể tự gọi model nhiều lần bên trong. Trần ở đây là **lượt chạy CLI**, không phải
cam kết token/USD cứng. Usage được lưu khi CLI báo; không bịa số liệu khi provider không cung cấp.

Tiết kiệm quota bằng cách:
- Hàng đợi, health, retry, đổi leader và status hoàn toàn bằng code.
- Tái sử dụng `prepared_plan` do Antigravity gửi, không trả phí lập kế hoạch lần hai.
- Chỉ gửi file liên quan, diff, kế hoạch và checkpoint ngắn; không gửi toàn bộ lịch sử chat.
- Test fail thì sửa trước khi trả phí review; lượt review chỉ thấy code đã được kiểm thử.
- Tất cả leader hết quota thì chờ reset/cooldown, không ping model liên tục.
- Không tự đổi model, nâng gói, mua credit hoặc chuyển tài khoản. Dùng model cấu hình sẵn trong CLI.

## Đổi leader và phục hồi

Thứ tự mặc định: `Antigravity → Claude → Codex → Copilot`, chỉ dùng CLI khả dụng và đúng vai trò.
Worker mặc định `Codex → Claude`. Review ưu tiên provider khác worker khi có thể.
Khi provider lỗi, Hub lưu checkpoint, xác nhận tiến trình cũ đã dừng rồi chọn provider khác.
Mỗi lượt có generation; kết quả cũ trả về sau hủy/chuyển giao không được ghi đè state mới.

- Quota: dùng timestamp reset/Retry-After rõ ràng nếu có, nếu không chờ 30 phút.
- Lỗi mạng/timeout: cooldown 2 phút; có agent thay thế thì giao ngay bước đang dở cho agent đó.
- Lỗi quyền, đăng nhập, kết quả sai schema: tránh gọi lại provider lỗi; chuyển sang provider khác
  nếu khả dụng, nếu không `blocked` để bạn xử lý.
- Không đổi leader chỉ vì một agent đang bận. Chỉ failover khi bước quyết định thực sự thất bại/timeout.
- Nếu không thể dừng tiến trình cũ hoặc sau crash còn PID sống, không mở writer trùng; chờ ở
  `recovering` hoặc `blocked` và lưu lý do. Không giết PID cũ bằng phỏng đoán.
- Tác vụ có giới hạn 24 giờ. Dữ liệu không mất khi hết ngân sách; bạn chủ động cho thêm lượt.

Daemon độc lập với menu/MCP/chat. Đóng Antigravity hoặc menu không dừng daemon.
Sau reboot, state vẫn còn; bật daemon để nó khôi phục. Có script autostart tùy chọn:

```powershell
# Chỉ thực hiện nếu bạn muốn tự chạy sau khi đăng nhập Windows:
.\scripts\install-autostart.ps1
# Gỡ:
.\scripts\remove-autostart.ps1
```

Script chưa được chạy/kiểm chứng trên Windows trong phiên phát triển Linux này.
Không cần mở quyền admin hoặc tắt sandbox. Nếu chính sách máy chặn PowerShell,
hãy dùng `python hub.py start` thủ công, không cần đổi ExecutionPolicy toàn hệ thống.
Linux: có `sh scripts/install-linux-user-service.sh` tùy chọn cho systemd user.
Máy tắt/sleep không chạy công việc. Hub không đánh thức chat Antigravity đã đóng;
luồng workflow bên trong daemon vẫn độc lập và tiếp tục trong khả năng CLI còn hoạt động.

## Dùng cho repository thật

Repository phải có commit và working tree sạch. Hub tạo Git worktree tách biệt;
không tự sửa working copy gốc, commit, merge hoặc push kết quả.

```powershell
python hub.py project-add my-app D:\Code\my-app --verify '[["{python}","-m","unittest","discover","-s","tests","-v"]]'
python hub.py run my-app "Thêm tính năng lọc công việc và test" --request-key filter-1
python hub.py status WORKFLOW_ID
python hub.py diff WORKFLOW_ID
python hub.py logs WORKFLOW_ID
python hub.py recover my-app
python hub.py cancel WORKFLOW_ID
python hub.py retry WORKFLOW_ID --extra-calls 2
```

Với PowerShell cũ gặp lỗi dấu nháy JSON, dùng file/script Python gọi Store.add_project;
hoặc xem [WINDOWS.md](docs/WINDOWS.md) để dùng PowerShell 7 và native argument passing.
`--verify` là lệnh bạn tin cậy, chạy bằng quyền người dùng để test độc lập. Hub không tự cài thư viện;
project cần có môi trường/dependency sẵn. `{python}` là Python đang chạy Hub; dùng đường dẫn Python
venv cụ thể khi dự án cần venv. Node dùng ví dụ `[["node","--test"]]`.

`retry` giữ nguyên trần hiện tại; `--extra-calls` là cấp thêm ngân sách có chủ đích.
Lỗi auth/config đã sửa xong: `python hub.py health-reset claude` rồi retry workflow.
Sửa file thủ công trong worktree có thể làm bằng chứng test cũ mất hiệu lực; Hub kiểm tra
fingerprint và chạy test lại trước khi review. Kết quả nằm trong `delivery` ZIP sau tự dọn, hoặc worktree nếu retention được tắt/không đủ điều kiện dọn.
Hub không tự merge; xem manifest trong ZIP trước khi đưa thay đổi vào repo gốc.

## Dữ liệu, config và công cụ

Mặc định `data/` cạnh hub.py; có thể đặt `--home PATH` hoặc biến `AGENT_HUB_HOME`.
- `config.json`: command của CLI, vai trò, ưu tiên leader, budget Auto, timeout.
- `hub.sqlite3`: queue, memory, health, generation, evidence, usage và event log; SQLite WAL.
- `runs/<id>/`: prompt, stdout/stderr, schema và report của từng lượt; verification logs.
- `deliverables/<id>.zip`: code thay đổi, manifest, patch và báo cáo bàn giao; được giữ lại.
- `workspaces/<id>/`: worktree tạm chứa thay đổi; sau completed được đóng gói rồi dọn theo retention.

Mỗi project chỉ có một workflow active, mỗi daemon chạy một bước tại một thời điểm.
V0.1 ưu tiên ổn định và quota; chưa chạy nhiều writer song song.
Không sao chép `data/` hoặc `workspaces/` giữa Windows/Linux để di chuyển state: worktree
và đường dẫn phụ thuộc máy. Dùng ZIP nguồn, tạo data mới; xuất code và tài liệu qua Git.

CLI cục bộ:
`init`, `doctor`, `demo`, `project-add`, `projects`, `run`, `status`, `logs`, `diff`,
`recover`, `memory-note`, `cancel`, `retry`, `health-reset`, `start`, `stop`, `mcp-config`, `mcp`.
MCP chỉ dùng project đã đăng ký, không cho agent tự chọn đường dẫn bất kỳ.

## Kiểm tra

```powershell
python -m unittest discover -s tests -v
python hub.py demo --simulate
```

Demo `--simulate` không dùng model/quota, nhưng thật sự dùng SQLite, Git worktree và Python test.
Kết quả kiểm chứng, khoảng trống coverage: [VERIFICATION.md](VERIFICATION.md).
Kiến trúc: [ARCHITECTURE.md](docs/ARCHITECTURE.md). Nguồn tham khảo: [SOURCES.md](docs/SOURCES.md).

## Giới hạn quyền

Không có HTTP server, telemetry, chia sẻ log hay gửi tin ra ngoài do Hub thực hiện.
Các CLI vẫn liên hệ provider theo đăng nhập của bạn. Logs/checkpoint có thể chứa code và nội dung
bạn giao việc; đây là dữ liệu cục bộ, không phải kho bí mật được mã hóa.
Worktree là cách tránh xung đột code, không phải OS sandbox. Codex giữ sandbox của CLI;
Claude/Copilot/Antigravity có giới hạn công cụ riêng, không được coi là sandbox hệ điều hành tương đương.
Antigravity/Copilot chỉ được cấu hình làm planner/reviewer ở v0.1; thay đổi file ở vai trò này bị phát hiện và dừng.
Bản hiện tại chặn workflow thật có `--network`. Demo mới mặc định không bật mạng công cụ. Nếu gặp lỗi bwrap, sửa môi trường sandbox trong VM test thay vì tự mở mạng.
Không có cờ bypass sandbox tự động trong Hub.

## Không đọc lại toàn bộ code giữa các agent

Mỗi lượt nhận Context Pack thay vì toàn bộ repository. Antigravity truyền thêm handoff gồm
bản phân tích, quyết định và file/range cụ thể. Planner trả context_files để worker nhận đúng
phần liên quan. Reviewer chỉ nhận diff và evidence. Gói có SHA256; file thay đổi làm mất hiệu lực
ghi chú gắn hash cũ. Cache theo file, chỉ text của file thực sự gửi cho model mới được lưu.

Mỗi attempt có context-pack.json (file/hash/range, cache hit và số ký tự); usage có context_chars
để bạn theo dõi. Agent được yêu cầu không scan lại repository, chỉ đọc thêm phạm vi thiếu.
Không thể truyền nguyên suy nghĩ giữa model hoặc đảm bảo model không đọc lại file mục tiêu;
đây là cơ chế tái sử dụng phân tích và giới hạn lượng code gửi vào model.

## Tự dọn sau khi hoàn tất

Mặc định Hub xuất ZIP bàn giao, kiểm tra CRC + SHA256, rồi mới xóa worktree, raw prompt/log và
cache của workflow completed. Không xóa code bàn giao hoặc repo gốc. Code bị sửa sau review,
ignored file lạ, symlink hoặc lỗi xuất ZIP đều làm Hub giữ worktree và báo lý do.
Logs lỗi giữ 7 ngày; cache giới hạn 64 MiB/20.000 entries; lịch sử verbose đã có ZIP compact sau
90 ngày. Xem docs/RETENTION.md. Dọn thủ công: `python hub.py cleanup`.
Tính năng không xóa lịch sử toàn cục của các ứng dụng agent khác.

## Kết quả kiểm chứng

Xem [VERIFICATION.md](VERIFICATION.md) để biết phần đã chạy thật và giới hạn kiểm thử Windows/provider.

CI mẫu ở `docs/github-actions-test.yml.example`. Chưa bật GitHub Actions vì token push thiếu scope workflow. Muốn bật, chép mẫu vào `.github/workflows/test.yml` và push bằng tài khoản/token có quyền workflow.
