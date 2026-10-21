# Bàn giao giữa các agent

Handoff v2 tự chạy trong workflow, không thêm bước vào `setup → init → prompt`.
Mỗi báo cáo mới gồm lý do thực hiện, tiến độ, câu hỏi chưa rõ, các cách đã thử,
lý do loại bỏ, quyết định kèm lý do và bước tiếp theo (file liên quan, điều kiện dừng).
Mục tiêu lấy từ task; phạm vi, bảo mật và verifier lấy từ cấu hình của người vận hành.

Hub lưu checkpoint có revision/generation cùng kết quả attempt trong một giao dịch
SQLite, kèm sự kiện `handoff_checkpoint`. Kết quả đến muộn từ generation cũ hoặc task
đã hủy không được ghi đè checkpoint. Khi CLI chết, Hub giữ bàn giao gần nhất, ghi rõ
phần công việc/lý do chưa được báo cáo là chưa biết rồi tiếp tục bằng generation mới.
Không tự suy ra những cách agent đã thử từ exit code hoặc bản tóm tắt.

Agent báo cáo theo schema `handoff` trong report. Các nhóm chính:

| Trường | Nội dung |
| --- | --- |
| `intent.rationale` | Vì sao cần làm việc này |
| `progress` | `completed`, `in_progress`, `unknowns` — đều là lời agent báo cáo |
| `attempts` | ID ổn định, trạng thái, lý do, tham chiếu bằng chứng, điều kiện xem xét lại; `blocked` là thiếu điều kiện, `rejected` là hướng bị bằng chứng loại bỏ |
| `decisions` | Quyết định và lý do |
| `next_action` | Hành động, vai trò nhận việc, ID cách tiếp cận, file và điều kiện dừng |

Hub bổ sung hash source trước/sau lượt chạy. Kết quả verifier có command, exit code
và fingerprint do Hub thu thập riêng. `evidence_refs` của agent chỉ là lời tham chiếu,
không chứng minh test pass. Source đổi sau bàn giao sẽ có cảnh báo phân tích có thể cũ.
Các file của bước tiếp theo được ưu tiên trong danh sách excerpt, vẫn qua bộ lọc source.

Context Pack giữ đầy đủ phạm vi, mục tiêu, tiến độ, quyết định, lý do loại hướng cũ
và bước tiếp theo trước các đoạn code tùy chọn. Bằng chứng Hub và raw error trùng lặp
không chép hai lần; có ghi rõ phần lược bỏ, checkpoint đầy đủ vẫn nằm trong SQLite.
Reviewer phải nhận toàn bộ diff trước memory/plan cũ, vì reviewer không được gọi tool
để tự bổ sung code. Không đủ chỗ cho diff thì dừng trước lượt AI, không cắt diff.
Thiếu dung lượng để chứa phần bắt buộc thì dừng trước khi tính thêm lượt CLI;
không âm thầm cắt mất lý do thất bại. Muốn tiếp tục, tăng dung lượng context phù hợp
với CLI đã chọn hoặc tách công việc sau khi xem lại checkpoint.

## Xem hoặc xử lý một hướng đã bị loại

```powershell
ma handoff TASK_ID
ma handoff TASK_ID --json
```

Lệnh thường chỉ in revision, bước tiếp theo và lý do loại các cách cũ. JSON chỉ hiện
khi yêu cầu rõ. Trạng thái workflow/MCP có checkpoint trong trường `handoff` như cũ.

Agent dùng lại ID đã bị loại cho bước tiếp theo sẽ bị chặn. Nếu người vận hành đã
xem bằng chứng mới hoặc điều kiện thay đổi và muốn thử lại:

```powershell
ma handoff TASK_ID --allow-approach APPROACH_ID --reason "Da xem bang chung moi: ..."
ma retry TASK_ID
```

Quyền này chỉ áp dụng một attempt của đúng vai trò nhận việc, revision và fingerprint đã xem; source đổi
thì phải xem lại. Lịch sử loại bỏ vẫn được giữ. Worker và MCP không có công cụ tự cấp
quyền này. Không tăng call budget, đổi security hoặc bỏ sandbox. `ma retry` vẫn cần
ngân sách còn lại; lệnh cấp quyền không tự chạy agent.
Planner chạy lại trước worker không tiêu nhầm quyền đã cấp cho worker; chỉ giữ quyền
khi action/role không đổi và fingerprint trước/sau planner vẫn khớp.

## Tương thích và giới hạn

Handoff đầu vào V1 (`summary/files/decisions/base_commit`) và report cũ vẫn được nhận.
Phần thiếu ghi UNKNOWN/chưa cung cấp, không bịa lịch sử. Không di chuyển hay sửa
worktree đang có để nâng cấp. Nội dung bàn giao là dữ liệu không đáng tin, không có
quyền ghi đè global rules hoặc xác nhận phạm vi dữ liệu.

Chặn lặp dựa trên ID agent khai báo, không phát hiện hoàn hảo hai cách giống nhau
nhưng đặt ID khác, và không giám sát được toàn bộ suy nghĩ/hành động bên trong một
lượt CLI. Hướng đã loại không bị agent sau xóa hay đổi thành thành công. Ledger tối
đa 100 ID; chạm giới hạn hoặc checkpoint vượt context sẽ dừng để người vận hành xem
lại, không tự bỏ lịch sử hoặc gọi model để nén. Nhật ký checkpoint dùng retention
hiện có của Hub. Windows đã thử workflow thật Copilot plan → Codex implement →
verifier → Copilot review trên source synthetic, có phục hồi lỗi và approve ở lượt
review cuối. Không suy ra Claude/Antigravity thật hoặc mọi chat host đều hoạt động.
