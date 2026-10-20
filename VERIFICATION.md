# Kiểm chứng bản demo

## Ubuntu — 2026-10-20

Portable setup/launcher update: **175 cases, 168 passed, 7 Windows-only skipped**.
Actual Ubuntu setup/init, MCP/18 tools, two completed model-backed workflows, delivery
integrity and exported behavior were checked separately from the suite. Five Hub CLI
calls used Codex/Copilot; one Antigravity frontend attempt hit real quota (6 total).
UI prompt dispatch and exhausted-host chat operation are **not accepted** from this
result. See [Ubuntu readiness evidence](docs/UBUNTU_READINESS.md) for seven-layer
coverage, exact limits and filming gates. Default provider commands are machine-neutral
and configure all four supported CLIs; enabled/installed/authenticated/working are
separate states. No global security attestation was invented.

## V2 — Windows, 2026-10-20

Chat results/setup login/wake update: **167 unittest pass in 77.684s**, including 11
Node handler/transport cases. Tests use fake providers and mock login processes.
Blocked/completed chat responses show bounded structured reports from SQLite,
review findings and verifier evidence without additional AI or artifact-file reads.
UTF-8 is pinned for Windows stdio. The owned chat extension upgrades to 0.1.1;
unowned or externally changed installs are preserved. Setup provides numbered
official login for checked providers; exit 0 never implies authentication, and
unsupported auth probes remain UNKNOWN. A fake three-agent pipeline completed
Antigravity plan, Codex implementation and Copilot review in three calls.
Official Copilot CLI 1.0.100 was installed; after the human completed browser
login, one actual Hub adapter smoke returned HUB_COPILOT_OK with tool access and
built-in MCPs disabled. No application source/API was used in that one model call.
Antigravity remains quota-cooling until 2026-10-25 13:20:16 +07:00; simultaneous
three-provider live execution has not been claimed or forced.
Automatic readiness uses actual completed adapter responses with executable/model
fingerprints; negative auth and persisted cooldown take precedence. Tests cover
model changes, negative auth, scheduled retry idempotency, no early call, recovery
after five days waiting and three additional offline days, and unchanged call caps.
The generic queue watchdog starts only due/recoverable work through the existing
daemon lock. Windows installation uses an owned limited user Scheduled Task,
pythonw.exe (no terminal window), five-minute checks and StartWhenAvailable.
It does not wake powered-off hardware or run while the user is logged out. Ubuntu
user-service installation remains open; the stdlib queue wake function is shared.

Codex runtime conflict: CLI 0.161.0 reproduced a sharing violation (Windows error
32) while refreshing read/execute permissions on the running desktop node_repl.exe.
The official stable CLI 0.163.0 was installed separately and passed the workspace
sandbox probe while the desktop chat remained open, then replaced only the npm
CLI package after its previous package/launchers were archived and hash-verified.
Hub resolved 0.163.0 and passed its own no-model probe. A Python read/write/delete
check of one owned synthetic file also passed inside the sandbox with managed
configuration included. No sandbox override, auth/config deletion, ACL reset or
model call was used. Existing workflow ec51b8abc1b4 remained blocked at 2/6 calls;
this proves executor startup, not completion of that AI task or all desktop tools.
The probe now includes managed requirements and no longer suggests the unsupported
/setup-default-sandbox slash command or echoes raw provider diagnostics.
Windows regression suite after this change: **156 unittest pass in 78.936s**.
Project preparation rerun with desktop open: worker probe OK, configured offline
Gradle verifier exit 0, MCP handshake OK with 18 tools, ready=true and AI calls=0.

Chat/init/failover update: **155 unittest pass**; Node handler/transport regression
also runs inside that suite (9 Node cases, including a real local stdio handshake).
Tests use synthetic repositories/fake providers, not live model calls. Covers compact
quota reset durations, task_blocked without provider cooldown, operator scope and
configured verifier in planner context, nested manifests, changed-only monitoring,
matching discovery/execution fallback without replacing custom commands, per-project
scope preserving isolation policy, baseline verification in an owned worktree,
SDK environment allowlist and verified VSIX packaging/ownership. Handler never
accesses the host chat model and restricts dispatch/cancel to registered workspace
projects; retry preserves the call budget. Chat Stop does not cancel the daemon.
Actual Copilot UI rendering/account-quota behavior and Antigravity's own chat remain
unverified; unit/stdIO evidence does not prove those UI paths.
Launcher normalization backs up the user PATH, retires only this checkout's old
PATH entry and keeps the owned interpreter/home launcher first. It never deletes
legacy source files or another tool's PATH entry.

Live MCP smoke from Codex chat: one CLI call, workflow e8272b9b820b, correctly stopped
as task_blocked when the Codex 0.161.0 Windows executor returned
`helper_unknown_error: setup refresh had errors`. No document created, no verifier
run for that task, original E-Learning source unchanged, no provider quota health
penalty. A separate `codex sandbox -P :workspace` literal-print probe reproduced the
same failure without a model. Interactive init and real Codex implementation now
probe that executor before consuming a worker call; failure does not loosen sandbox,
grant calls or report ready. Baseline Android verifier itself passed offline before
this executor failure. Installed VS Code extension @hub 0.1.0 verified by CLI listing;
Copilot UI/quota behavior remains unverified.
Windows cleanup also hit Git's default long-path limit on nested Gradle artifacts.
Hub now supplies core.longpaths=true per Git invocation, without changing global
Git config. Regression creates, archives and removes a real worktree with paths
over 400 characters; temporary fixtures are removed after the test.

Bản installer MCP: **136 unittest pass** trong 64.875 giây. Cấu hình rỗng,
chỉ whitespace hoặc có BOM được xử lý và giữ backup nguyên byte. JSON sai cấu trúc
bị từ chối, không ghi đè. Kiểm tra stdio server thật: initialize, 18 tools và
list_agents trả bốn agent; 0 lượt gọi AI. Việc IDE refresh/chat nhận server vẫn
cần kiểm chứng trên giao diện; không suy ra từ phép thử stdio này.

Bản Gradle/nâng cấp verifier: **134 unittest pass** trong 64.148 giây.
V2 nhận diện wrapper trong thư mục con và file chưa tracked, cần một candidate có
marker Gradle và source unit test. Dùng đường dẫn tương đối, --project-dir và
--offline; fixture Windows thực thi wrapper giả có khoảng trắng. Lệnh Gradle chỉ
được ghi nhận khi init, không tự chạy. --replace-verify giữ bản cũ, chặn workflow
đang active và cập nhật context cache theo verifier mới. Wrapper/project path sai
bị chặn. CLI ghi Tests run: no và hiện lệnh đã lưu; không nhận lỗi thiếu dependency
cache là test pass. Không chạy Gradle thật, tải dependencies hoặc gọi model.

Bản nhập lệnh kiểm tra trực tiếp: **126 unittest pass** trong 59.454 giây.
`ma init --verify-command EXECUTABLE ARGS...` lưu một command mà không cần JSON,
không chạy command lúc init. Giữ tương thích --verify, cấm dùng đồng thời hai cách,
báo lỗi rõ khi thiếu executable và giữ nguyên các flags như --offline. Regression
chạy trên Git fixture; chưa chạy Gradle hoặc workflow AI trên project E-Learning.

Bản READY từ xác nhận người dùng: **124 unittest pass** trong 61.261 giây.
Xác nhận mới không hết hạn theo ngày, hiện READY và giữ nguồn operator; authentication
và live_verified không tự đổi. CLI/model thay đổi, probe lỗi, thiếu protocol hoặc auth
âm tính vẫn vô hiệu xác nhận. Record cũ có hạn giữ hạn cũ tới khi người dùng xác nhận
lại. Regression gồm record mới sau 30 ngày, hạn cũ, thu hồi và terminal/MCP.

Bản ghi nhận operator: **124 unittest pass** trong 59.136 giây. Lệnh
`ma agents confirm AGENT --worked` kiểm tra CLI/protocol, lưu xác nhận của người
dùng trong 24 giờ và hiện USER_CONFIRMED ở terminal/MCP. Authentication vẫn UNKNOWN
nếu chưa có probe chính thức; live_verified không tự bật. Có regression cho hết hạn,
thời gian sai, binary/model/command đổi, lỗi probe/auth, thu hồi và tách home.
Không lưu phản hồi/token, không gọi model và không thay security attestations.

Bản nhận diện Antigravity Windows: **117 unittest pass** trong 60.655 giây.
Hub tìm `%LOCALAPPDATA%\agy\bin\agy.exe` khi terminal chưa cập nhật PATH.
Regression dùng executable giả và không chạy provider. Kiểm tra riêng binary thật
agy 1.4.2 bằng --version/--help: adapter protocol được nhận diện, authentication
giữ UNKNOWN vì chưa có probe đăng nhập được xác minh; không gọi model.

Bản hiển thị CLI ngắn và lý do agent: **116 unittest pass** trong 57.789 giây.
Các lệnh ma mặc định dùng văn bản, hỗ trợ --json cho script/chẩn đoán đầy đủ;
setup giữ tương tác văn bản, MCP giữ JSON-RPC và mcp-config giữ JSON nhập vào IDE.
Monitor giới hạn lịch sử, logs hiện tóm tắt, diff giữ patch cần xem. Cột lý do phân
biệt đã tắt, thiếu CLI/PATH, thiếu đăng nhập, chưa xác minh, lỗi probe và adapter.
Regression dùng repo synthetic và probe giả; không gọi model, không sửa cấu hình thật.

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
