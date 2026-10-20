# Lỗi và công việc cần đóng góp

Dự án chưa đạt tiêu chí setup → init → prompt trên Windows/Ubuntu và mọi khung chat
mục tiêu khi còn/hết quota. Không đánh dấu hoàn thành chỉ vì unittest pass hay đã
sinh cấu hình MCP. Xem bằng chứng trong [VERIFICATION](../VERIFICATION.md).

## Lỗi đã sửa

| Lỗi từng gặp | Bản sửa |
|---|---|
| Setup hỏi model nhiều lần; role sai làm hỏng setup | Chọn policy chung một lần, sửa input tại chỗ, rollback/backup |
| JSON dài, không rõ agent vì sao chưa hoạt động | Một dòng/agent và lý do ngắn; JSON tùy chọn |
| Cài agy nhưng PATH cũ không thấy | Tìm thư mục installer; discovery/execution thống nhất, giữ custom command |
| Auth probe chưa hỗ trợ dù đã gọi AI thành công | Xác nhận operator có fingerprint, không giả live_verified/auth |
| Gradle wrapper lồng thư mục/đường dẫn có khoảng trắng | Detect wrapper, --project-dir, kiểm path, backup verifier |
| MCP config rỗng/BOM làm installer lỗi | Hỗ trợ file rỗng/BOM; backup, không đè JSON sai |
| Context thiếu scope/verifier khiến agent từ chối | Scope đã xác nhận và verifier lên đầu pack; manifest lồng thư mục |
| Task blocked nhắc 429 lịch sử bị coi là quota thật | Tách task_blocked, không thay health/cooldown provider |
| Individual quota reached/reset 124h1m3s bị retry sau 2 phút | Phân loại quota và đọc duration nhiều giờ/ngày |
| Monitor lặp; launcher cũ chọn Python/home khác | Chỉ in trạng thái đổi; backup PATH, ưu tiên launcher cố định |
| Mất lượt AI rồi mới thấy sandbox không chạy | Probe executor không gọi model trong init và trước lượt worker |
| Codex CLI 0.161.0 lỗi Windows error 32 khi desktop mở | Cập nhật CLI chính thức lên 0.163.0 đã vượt probe đọc/ghi khi desktop mở; giữ sandbox và managed policy, không xóa runtime/auth |
| Hub hướng dẫn slash /setup-default-sandbox không có trong CLI | Bỏ slash sai; chỉ dẫn doctor và cập nhật CLI, không in raw diagnostics |
| Chat chỉ hiện tiến độ, không trả báo cáo khi hết budget | @hub /status và /watch hiện báo cáo checkpoint, finding, review còn mở và file trong worktree; không gọi thêm AI |
| Copilot Chat bị nhầm với Copilot CLI chưa cài | Nhãn AGENT CLI và lý do riêng; Chat hoạt động độc lập với CLI |
| Phải ra ngoài setup đăng nhập từng provider | Menu số chỉ cho CLI được chọn, dùng login chính thức tại terminal, probe lại; không suy diễn auth từ exit code |
| Prompt tiếng Việt bị sai mã khi stdio Windows | Bridge ghim Python UTF-8 cho stdin/stdout |
| Trạng thái CLI phải ghi nhận thủ công dù agent đã trả lời | Lưu bằng chứng adapter thành công, so fingerprint binary/model; auth âm tính và cooldown được ưu tiên |
| Chờ quota nhiều ngày bị chặn bởi tuổi task | Lưu lịch chờ, tách thời gian chờ khỏi cửa sổ thực thi; khôi phục khi daemon chạy lại, giữ call cap |
| Retry lịch bị gửi lại có thể cấp trùng lượt | Request key khử trùng lịch và khoản cấp lượt; xung đột tham số bị chặn |
| Review báo cáo lặp vì yêu cầu fingerprint bao gồm chính báo cáo | Giữ hash trong bằng chứng Hub; báo cáo chỉ ghi nguồn/kết quả và giới hạn cache một cách trung thực |
| Cleanup Windows lỗi Filename too long ở build Gradle | Bật core.longpaths riêng mỗi lệnh Git; có regression tạo/xóa worktree đường dẫn dài |

## Việc còn mở

| ID | Vấn đề | Bằng chứng nghiệm thu cần bổ sung |
|---|---|---|
| WIN-01 | CLI 0.163.0 đã vượt sandbox probe; workflow AI còn cần tiếp tục kiểm chứng | Task thật sửa file + verifier pass khi desktop mở; giữ sandbox và call cap |
| CHAT-01 | @hub chưa kiểm chứng UI Copilot khi chat còn/hết quota | Gửi task, xem tiến độ, cancel/retry từ đúng chat, không gọi host model |
| CHAT-02 | Khung chat riêng Antigravity và các client khác | Bridge qua API chính thức, xác minh cả hai trạng thái quota |
| LINUX-01 | Bản mới chưa test Ubuntu; launcher global chưa hoàn thiện | Setup một lần, init một lệnh, prompt IDE; suite và smoke thật pass |
| INIT-01 | Chưa có Git/commit sạch, verifier mơ hồ hoặc thiếu dependency | Xử lý rõ trong init với lựa chọn được phép; không báo ready giả |
| PROVIDER-01 | Claude/Copilot và một số auth/model probe chưa live-test đầy đủ | Smoke synthetic, version, quyền và metadata khi provider có trả |
| CTX-01 | Bộ lọc data loại cả source package như data/DataRepository.kt | Phân biệt source đã duyệt với thư mục dữ liệu; không nới quyền đọc dữ liệu thật/secrets |
| CI-01 | CI mới có file mẫu, chưa bật | Ma trận Windows/Ubuntu; test không gọi model, không cần secrets |

Chat host hết quota có thể chặn request trước khi extension/tool được chạy. MCP
không tự giải quyết điều này; từng client cần đường tích hợp chính thức được test.
Không đổi sandbox, vượt quota hoặc tăng budget để phép thử trông như thành công.

WIN-01: [hướng dẫn Windows sandbox của OpenAI](https://learn.chatgpt.com/docs/windows/windows-sandbox).
Người dùng tự hoàn tất setup/UAC khi cần; không tự hạ sandbox để né lỗi.

Khi góp bản sửa, ghi ID, OS/CLI version, tái hiện bằng source synthetic và kết quả
trước/sau. Không gửi token, .env hoặc log có dữ liệu thật.
