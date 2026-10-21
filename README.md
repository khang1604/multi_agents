# Multi Agents

Dùng nhiều công cụ AI để cùng làm một dự án, đỡ phải tự chuyển việc qua lại.
Bạn cài một lần, mở dự án cần làm rồi nhập yêu cầu. Multi Agents giúp giao việc,
nhớ tiến độ, kiểm tra kết quả và đổi sang công cụ khác khi có thể.

Hỗ trợ **Codex, Claude Code, Copilot CLI và Antigravity CLI**. Không cần cài đủ cả bốn.
Codex và Claude có thể sửa code; cả bốn đều có thể lập kế hoạch hoặc xem lại thay đổi.
CLI là bản chạy bằng dòng lệnh; có ứng dụng hay extension chưa chắc đã có CLI.

**Dự án vẫn đang hoàn thiện.** Một số luồng đã chạy bằng AI thật, nhưng chưa kiểm
đầy đủ trên mọi máy và mọi ứng dụng chat. Đặc biệt, chưa thể hứa rằng chat hết quota
thì vẫn gửi được yêu cầu mới. [Xem phần đã thử và còn thiếu](VERIFICATION.md).

## Dự án giúp được gì?

| Bạn muốn… | Multi Agents giúp thế nào? |
|---|---|
| Dùng những AI mình đang có | Tìm CLI đã cài và cho bạn chọn công cụ muốn dùng. Không bắt cài đủ bốn. |
| Bớt tự chuyển việc giữa các AI | Giao phần lập kế hoạch, viết code và xem lại kết quả cho công cụ phù hợp. |
| AI lỗi thì có công cụ khác làm tiếp | Lưu tiến độ rồi thử công cụ khác còn dùng được. Nếu không còn công cụ phù hợp, sẽ chờ hoặc báo cần bạn xử lý. |
| Đóng chat rồi quay lại không phải giải thích từ đầu | Lưu việc đang làm, quyết định đã có và lỗi còn lại trên máy. |
| Đỡ tốn quota cho việc nhỏ | Việc đơn giản dùng ít bước hơn; việc khó có thêm bước kiểm tra. Không tự tăng số lượt đã cho phép. |
| Không để AI nào cũng đọc lại cả dự án | Bàn giao mục tiêu, cách đã thử/lý do thất bại và bước tiếp theo; giữ hash và kết quả test riêng. [Chi tiết](docs/HANDOFF.md). |
| Biết code làm ra có chạy không | Chạy lệnh kiểm tra của dự án, lưu kết quả rồi cho AI xem lại khi cần. Test pass vẫn chưa chứng minh mọi tính năng đều đúng. |
| Chấp nhận code theo cách mình muốn | Agent viết vào file trong bản làm việc riêng. Khi xong, bạn xem rồi Accept để áp dụng vào file dự án đang mở; có thể bật Auto accept riêng cho dự án. |
| Không để file tạm phình mãi | Kiểm gói kết quả trước khi dọn bản làm việc tạm; việc đang chạy hoặc đang chờ được giữ lại. |
| Hết quota thì làm tiếp sau | Lưu chỗ đang dở và giờ thử lại. Máy và Hub cần hoạt động để tiếp tục; không tự mua thêm lượt. |

Giới hạn lượt hiện tính theo **số lần chạy CLI**, chưa phải số token hoặc tiền chính xác.
Một lượt CLI có thể gọi model nhiều lần bên trong.

## Cần chuẩn bị gì?

- Git và **Python 3.11 trở lên**.
- Ít nhất Codex CLI hoặc Claude Code CLI nếu muốn AI sửa code.
- Tự đăng nhập những CLI muốn dùng bằng cách chính thức của từng công cụ.
- Dự án có Git, đã commit phần muốn dùng và có lệnh kiểm tra chạy được.
- Chỉ dùng code được phép, dữ liệu giả và API test đã được cho phép.

Multi Agents dùng thư viện có sẵn của Python, không cần `pip install` cho phần chính.
Các CLI AI và thư viện của dự án bạn làm vẫn cần cài riêng.

## Bắt đầu theo 3 bước

### 1. Cài một lần tại thư mục Multi Agents

**Ubuntu:**

```bash
mkdir -p ~/Project
cd ~/Project
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

**Windows — PowerShell:**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

Nếu đã có folder cùng tên, dùng folder trống khác; đừng xóa thay đổi đang có để cài lại.
Có thể chạy `python3 ma.py setup` trên Ubuntu hoặc `py -3 ma.py setup` trên Windows
nếu máy không chạy được file setup. Không cần tắt chính sách bảo mật của máy.

Làm theo hướng dẫn để chọn AI, cài lệnh `ma` và kết nối ứng dụng chat muốn dùng.
Bạn có thể giữ lựa chọn model mặc định của từng AI bằng **INHERIT**.
Setup có chỗ mở đăng nhập chính thức; công cụ chưa xác minh được sẽ ghi **UNKNOWN**,
không tự nhận là đã đăng nhập hay còn quota.

Trên Ubuntu, nếu chọn cài `ma`, chạy lệnh `export PATH=...` mà setup in ra.
Nó giúp terminal tìm thấy lệnh vừa cài. Dự án không tự sửa `.bashrc` hoặc `.profile`;
terminal mới cần PATH đã được bạn cấu hình, hoặc dùng đường dẫn đầy đủ của lệnh `ma`.
Trên Windows, mở terminal mới sau khi cài. Nếu có yêu cầu, mở lại ứng dụng chat.

### 2. Mở thư mục dự án cần làm rồi chạy init

```bash
cd /duong/dan/du-an-cua-ban
ma init
```

Không cần chép Multi Agents vào từng dự án. Cài ở một nơi rồi dùng cho nhiều dự án.

### 3. Nhập yêu cầu trong chat như bình thường

Ví dụ:

```text
Thêm chức năng lọc công việc theo trạng thái và từ khóa. Giữ cách gọi cũ và bổ sung test.
```

Ứng dụng chat cần được kết nối với Multi Agents ở bước setup. Trong Copilot Chat,
chọn `@hub` một lần rồi tiếp tục nhập nội dung trong cuộc chat đó.
Với chat dùng MCP, ứng dụng cần nhận đúng công cụ của Hub sau khi refresh.

**Chỉ khi có mã công việc của Hub mới biết yêu cầu đã được giao.**
Nếu AI trong chat tự viết code mà không gọi Hub, đó chưa phải luồng Multi Agents.
Bạn không cần tự chạy `ma run` cho từng việc; lệnh này vẫn có nếu muốn dùng terminal.

## Khi chat hoặc AI hết quota thì sao?

- **Việc đã giao cho Hub:** có thể tiếp tục bằng CLI khác còn dùng được.
- **CLI đang làm hết quota:** Hub lưu tiến độ, tìm công cụ thay thế hoặc chờ thử lại.
- **Chat chặn yêu cầu mới:** MCP không tự đọc được câu bạn nhập, nên yêu cầu có thể
  chưa tới Hub. Hiện chưa bảo đảm khắc phục được việc này trên mọi giao diện.

`@hub` được viết để không gọi model của chat trong phần xử lý, nhưng vẫn phải kiểm
tra xem ứng dụng có cho phần đó chạy khi hết quota hay không. Chưa thử được thì
không coi là đã hoạt động.

## Muốn xem thử trước khi dùng AI thật?

Tại thư mục Multi Agents, chạy:

```bash
python3 ma.py demo --simulate
```

Windows dùng `py -3` thay cho `python3`.
Demo này giả lập câu trả lời của AI, nhưng vẫn dùng Git, lưu tiến độ và chạy test thật.
**Không gọi model, không tốn quota.** Nó không chứng minh tài khoản AI đã dùng được.

## Những lệnh hay dùng

| Lệnh | Dùng khi nào? |
|---|---|
| `ma setup` | Muốn đổi lựa chọn AI hoặc kết nối lại ứng dụng chat. |
| `ma init` | Bắt đầu với một dự án, hoặc kiểm tra lại sau khi sửa môi trường. |
| `ma agents list --check` | Xem CLI nào có trên máy và thông tin đăng nhập kiểm tra được. |
| `ma status --watch` | Xem công việc đang đến đâu mà không hỏi AI liên tục. |
| `ma logs` | Xem lượt nào đã chạy hoặc gặp lỗi. |
| `ma handoff ID` | Xem bước tiếp theo và lý do loại các hướng đã thử; `--json` để xem đầy đủ. |
| `ma diff` | Xem phần code thay đổi trước khi Accept. |
| `ma accept ID` | Chấp nhận và áp dụng code đã hoàn tất vào file dự án; lệnh này chính là xác nhận của bạn. |
| `ma auto-accept on` / `off` / `status` | Bật, tắt hoặc xem chế độ tự áp dụng cho dự án trong thư mục hiện tại. |
| `ma retry ID` | Tiếp tục công việc sau khi xử lý lỗi; không tự cấp thêm lượt. |
| `ma doctor` | Tìm nguyên nhân khi setup hoặc init báo lỗi. |
| `ma --help` | Xem các lệnh còn lại. |

### Lệnh `@hub` trong Copilot Chat

| Lệnh | Dùng khi nào? |
|---|---|
| `@hub <yêu cầu>` | Trong Copilot Chat đã cài Hub, nhập ví dụ `@hub Thêm bộ lọc công việc`. Hub nhận việc cho dự án đang mở và trả mã công việc để theo dõi. Nếu đã có việc đang chạy, yêu cầu mới chưa được gửi; bạn cần theo dõi hoặc dừng việc cũ trước. Chat khác có thể kết nối qua MCP. |
| `@hub /agents` | Liệt kê CLI mà Hub nhận diện và thông tin trạng thái đã biết. Lệnh này không gọi model; trạng thái có thể chưa đủ để khẳng định tài khoản còn quota. |
| `@hub /status` | Hiện trạng thái, bước đang làm, AI phụ trách, số lượt đã dùng và lỗi nếu có. Chỉ xem một lần, không tạo việc mới. |
| `@hub /watch` | Cập nhật tiến độ của việc đã giao trong tối đa khoảng 10 phút mỗi lần xem. Đóng hoặc dừng phần theo dõi không hủy việc đang chạy. |
| `@hub /retry` | Yêu cầu tiếp tục việc sau khi bạn xử lý nguyên nhân bị chặn. Giữ nguyên giới hạn lượt AI; không cấp thêm quota và không bảo đảm lỗi đã hết. |
| `@hub /cancel` | Gửi yêu cầu dừng, giữ lại code và tiến độ đã lưu để xem hoặc tiếp tục sau. Không xóa thay đổi đã có. |
| `@hub /accept [ID]` | Sau khi xem code và kết quả kiểm tra, chọn Accept trong hộp xác nhận để ghi thay đổi vào file dự án. Không tự commit hoặc push. |
| `@hub /autoaccept on` | Bật tự áp dụng kết quả cho dự án đang mở sau khi xác nhận. Nếu file gốc đã thay đổi, Hub dừng áp dụng để tránh ghi đè. |
| `@hub /autoaccept off` | Tắt tự áp dụng; các kết quả tiếp theo chờ bạn Accept. |
| `@hub /autoaccept status` | Xem dự án đang bật hay tắt Auto accept. Mặc định tắt. |

Với `/status`, `/watch`,
`/retry`, `/cancel` và `/accept`, nếu không nhập mã thì Hub chọn công việc gần nhất của dự án
đang mở. Muốn chọn việc cụ thể, thêm mã phía sau, ví dụ `@hub /status abc123`.
Mã phải thuộc dự án đang mở. Accept áp dụng kết quả của cả công việc.
Auto accept của Hub không thay đổi quyền sửa file hay sandbox riêng của từng CLI.
Các lệnh này không gọi model để hỏi tiến độ;
`/retry` có thể khiến Hub tiếp tục gọi CLI AI trong giới hạn lượt còn lại.

## Dữ liệu và quyền truy cập

Không dùng dữ liệu khách hàng thật, database thật, `.env`, token hoặc khóa bí mật
làm đầu vào cho agent. Tên folder có chữ `test` không có nghĩa dữ liệu bên trong là giả.

Quy tắc bằng chữ không thay thế quyền truy cập của hệ điều hành. Nếu cần ngăn truy
cập ngoài dự án, phải chuẩn bị môi trường cách ly phù hợp. Agent không được tự xác
nhận điều kiện này hoặc nới quyền để chạy cho xong.

Đọc [GLOBAL_RULES.md](GLOBAL_RULES.md) và [hướng dẫn bảo mật](docs/SECURITY.md) trước
khi giao việc thật. Đăng nhập nằm ở CLI chính thức; không chia sẻ token với Hub hay chat.

## Đọc thêm

- [Hướng dẫn Ubuntu và cách quay demo](docs/UBUNTU_DEMO.md).
- [Cấu hình mẫu cho đủ bốn CLI](examples/config/providers.example.json) — không có tài khoản hay đường dẫn máy cá nhân.
- [Những gì đã chạy thử](VERIFICATION.md) và [phần còn cần làm](docs/KNOWN_ISSUES.md).
- [Hướng dẫn chi tiết hơn](docs/V2_GUIDE.md), gồm lệnh test riêng và hẹn làm tiếp.
- [Góp phần phát triển](CONTRIBUTING.md).

Ý tưởng tham khảo từ [Maestro](https://github.com/RunMaestro/Maestro),
[agent-intern](https://github.com/SinanTufekci/agent-intern),
[Agent Deck](https://github.com/asheshgoplani/agent-deck) và
[AI Maestro](https://github.com/23blocks-OS/ai-maestro).
