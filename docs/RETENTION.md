# Dọn dữ liệu

Chính sách mặc định tự áp dụng sau completed và khi daemon rảnh theo chu kỳ 1 giờ:

1. Chỉ xử lý đúng data/workspaces/<workflow-id> của Hub.
2. So hash worktree với bằng chứng verification. Nếu code đã bị sửa sau test/review thì giữ nguyên.
3. Đóng gói file thay đổi (cả file mới), danh sách file xóa, Git binary patch, base commit,
   workflow checkpoint và report vào data/deliverables/<id>.zip.
4. Kiểm tra CRC và SHA256 từng file trong ZIP, xác nhận worktree chưa đổi trong lúc xuất.
5. Sau đó mới git worktree remove --force đúng worktree đó, dọn runs/<id> và cache tương ứng.
6. Giữ CLEANED.json chỉ tới ZIP bàn giao. hub.py diff vẫn đọc được patch/manifest từ ZIP.

Không tự xóa ZIP code bàn giao hoặc repo gốc. ZIP là overlay của file thay đổi trên base_commit,
không phải toàn bộ repository. Giải nén files/ lên checkout base_commit và xóa deleted_files
trong manifest. Không áp dụng patch lẫn copy overlay hai lần. Các file reports/ và workflow.json
là bằng chứng đã đóng gói, không chứa đăng nhập do Hub quản lý.

Tác vụ active/đang chờ quota không bị dọn. Failed/blocked/cancelled giữ raw logs 7 ngày;
sau đó dọn logs nhưng objective, plan, handoff và checkpoint SQLite vẫn còn để retry.
Cache có hạn mức 64 MiB text và 20.000 entries, bỏ mục ít dùng trước; có thể tái tạo hoàn toàn.
Thành công đã có ZIP sau 90 ngày được compact lịch sử chi tiết trong DB; bản đầy đủ nằm trong ZIP.
SQLite VACUUM chỉ chạy sau compact khi không có workflow active.

Mỗi stdout/stderr của agent có watchdog khoảng 4 MiB; vượt hạn mức thì dừng lượt đó.
Giới hạn file không phải chặn byte tuyệt đối: tiến trình có thể ghi vượt trong một chu kỳ quan sát.
Deliverable tự động tối đa 256 MiB file thay đổi; nếu lớn hơn thì giữ worktree để bạn xử lý,
không xóa hoặc cắt bỏ code. Không xóa worktree nếu có ignored file lạ hoặc changed symlink.

Dọn thủ công: python hub.py cleanup. Tắt tự dọn bằng retention.enabled=false trong config.json
rồi khởi động lại daemon. Có thể retention.archive_completed_worktrees=false để giữ worktree,
vẫn dọn cache/log cũ. Danh sách giữ lại và lý do nằm trong data/cleanup-last.json.

Hub không xóa ~/.claude, ~/.copilot, ~/.codex hoặc bộ nhớ Antigravity toàn cục. Codex được gọi
với --ephemeral để giảm session artifacts của CLI. Những lịch sử bên ngoài Hub có thể cần
chính sách riêng trong từng ứng dụng; không được xem là đã dọn bởi tính năng này.
