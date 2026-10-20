# Ubuntu: những gì đã thử và phần còn thiếu

Đã thử phần terminal: cài đặt, nhận diện dự án, kiểm tra code và chạy công việc bằng
Codex/Copilot thật. Code xuất ra được kiểm lại trong một bản sao riêng; dự án gốc
không bị tự ghi đè. Các kết quả này không thay cho việc thử giao diện chat.

| Phần | Đã kiểm tra đến đâu? |
|---|---|
| Cách dùng | Giữ setup ở root Hub → init ở dự án → nhập yêu cầu trong chat. Bước UI cuối chưa được xác minh đầy đủ. |
| Mã và file cài | Kiểm cú pháp Python/shell, đường dẫn dùng chung và quyền chạy launcher Ubuntu. |
| Kiểm thử tự động | Có các ca về launcher, đường dẫn, giữ tiến độ, quota và dọn dữ liệu; dùng AI giả lập. Xem VERIFICATION.md. |
| Các phần nối với nhau | Git, SQLite, lệnh test và MCP được chạy thật. |
| Công việc AI thật | Codex đã viết code, Copilot đã review; có gói kết quả kiểm lại được. Chưa chứng minh cả bốn AI đều chạy thật cùng lúc. |
| Dùng trên máy khác | Dùng tên CLI và đường dẫn theo máy đích. Chưa thử mọi bản Ubuntu, Python hay ứng dụng chat. |
| Giới hạn và phục hồi | Có kiểm sandbox, file bàn giao và giữ source gốc. Chưa phải kiểm toán bảo mật hoặc kiểm tải toàn diện. |

## Trước khi nói đã sẵn sàng quay toàn bộ

- Clone sạch bản có sửa Ubuntu; dùng project và home demo mới, không lẫn rehearsal.
- Chọn ứng dụng chat trong setup và refresh kết nối.
- Thấy prompt trên UI thật tạo đúng mã công việc của Hub cho đúng dự án.
- Nếu giới thiệu việc chat hết quota vẫn nhận lệnh, phải thử đúng tình huống đó;
  test code của handler hoặc MCP handshake chưa đủ.
- Có ngân sách rõ cho lần chạy AI mới; không tự gọi thêm để quay lại.

Chi tiết riêng của từng máy, đăng nhập, quota và log buổi thử không thuộc tài liệu
public. Hãy giữ trong file `.local.md` hoặc thư mục dữ liệu cục bộ đã được Git bỏ qua.
