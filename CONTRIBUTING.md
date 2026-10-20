# Đóng góp

Ưu tiên [các lỗi mở](docs/KNOWN_ISSUES.md) và luồng **setup global một lần → init
một lệnh → prompt trong chat**. Ghi kết quả Windows/Ubuntu, chat còn/hết quota;
chưa kiểm thử thì ghi chưa kiểm thử.

Đọc AGENTS.md, GLOBAL_RULES.md, docs/SECURITY.md, VERIFICATION.md trước khi làm.
Dùng source được phép và dữ liệu synthetic, giữ sandbox, checkpoint và call cap.
Không đọc credential, tự xác nhận scope hoặc đè thay đổi người dùng.

Sau sửa code: `python -m unittest discover -s tests -v` (Ubuntu dùng `python3`).
Test tự động dùng fake CLI, không gọi model. Smoke AI thật cần quyền rõ và budget
hữu hạn. Dọn fixture/worktree test đã dùng xong sau khi kiểm gói bàn giao cần giữ.
PR gồm ID lỗi, hành vi trước/sau, test và phần chưa xác minh.

## Prompt đầu tiên cho agent

Thay đường dẫn và ID lỗi trước khi gửi. Prompt này không tự cấp quyền gọi AI có phí.

```text
Tôi cho phép bạn làm việc trên source Multi Agents tại <HUB_REPO>.
Repo demo được phép tại <DEMO_REPO>, chỉ dữ liệu synthetic, không gọi API ứng dụng.
Mục cần xử lý: <ID trong docs/KNOWN_ISSUES.md>.

Đọc AGENTS.md, GLOBAL_RULES.md, docs/SECURITY.md, VERIFICATION.md, README.md và
docs/KNOWN_ISSUES.md. Kiểm git status, giữ thay đổi hiện có và checkpoint/budget.
Tự kiểm OS, Python >=3.11, Git và CLI bằng probe chính thức không gọi model.
Tái hiện lỗi trong worktree riêng, sửa đúng phạm vi bằng Python stdlib + Git.
Chạy unittest với fake CLI rồi kiểm setup-init-prompt tới mức công cụ cho phép.
Không đọc .env/token/dữ liệu thật, bypass/hạ sandbox hoặc tự tăng calls.
Không tự gọi AI có phí, commit/push/merge hay thay đổi hệ thống bên ngoài.
Nếu cần đăng nhập/UAC hoặc smoke AI thật, chuẩn bị bước cụ thể, giải thích vì sao
cần tôi thao tác/xác nhận; không yêu cầu tôi gửi credential.
Dọn test tạm sau khi kiểm gói bàn giao. Cập nhật ID lỗi, test và giới hạn còn lại;
không báo hoàn thành khi thiếu bằng chứng UI/OS/quota.
```
