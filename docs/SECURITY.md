# Test-only security boundary

Hub mặc định chặn workflow thật trước khi tạo worktree/đọc context. Demo `--simulate`
vẫn chạy trên fixture tự tạo, không gọi model. Mọi lời gọi CLI thật nhận GLOBAL_RULES.md.

## Điều kiện trước khi bật

1. Tạo VM hoặc tài khoản OS/container dành riêng cho development. Chỉ đưa source đã
   duyệt và fixture synthetic vào đó. Không mount home chính, .env, cloud credentials,
   DB dump, volume production hoặc log người dùng. Không đưa dữ liệu thật vào Git.
2. Chặn mạng của công cụ mặc định bằng firewall/proxy bên ngoài Hub. Nếu cần API test,
   khai báo chính xác hostname/port/method và thực thi allowlist ở proxy/firewall.
   Mạng của model provider cần cấu hình riêng; một cờ mạng chung không tạo allowlist.
3. Dùng tài khoản API test riêng, không có quyền production. Không dùng dữ liệu thật
   dù đã đặt trong môi trường test. Không chuyển credential/payload vào task hoặc memory.
4. Người vận hành kiểm tra ranh giới trên, rồi sửa `data/config.json` **bên trong môi
   trường đã cách ly**. Không để agent tự sửa policy hoặc xem đây là bước bỏ qua lỗi:

```json
"security": {
  "isolated_test_environment": true,
  "synthetic_data_only": true,
  "isolation_description": "Mô tả ranh giới OS, source/fixture được phép và firewall test thực tế"
}
```

Hai giá trị true là xác nhận của người vận hành, không phải kết quả Hub tự kiểm chứng.
Hub chưa triển khai ACL đọc file, firewall allowlist hoặc redaction/DLP hoàn chỉnh.
Codex workspace-write không đảm bảo chặn đọc mọi file ngoài repo. Các CLI còn lại cũng
không có sandbox thống nhất. Do đó không thể cam kết ngăn dữ liệu thật chỉ bằng RULE.
Giữ mặc định false nếu chưa có cách ly. Không dùng `--network`: Hub chặn lựa chọn đó
trong workflow thật vì không kiểm chứng được endpoint. Không đặt provider flags bỏ qua
permission/sandbox. Các test command của dự án cũng cần chạy trong cùng ranh giới.

## Cài global rules trên Windows

```powershell
python scripts/install_global_rules.py
# Xem bốn đường dẫn ở PREVIEW, rồi cài khi muốn:
python scripts/install_global_rules.py --apply
```

Script giữ nội dung cũ, cập nhật riêng khối marker của Hub và tạo `.backup-TIMESTAMP`.
Khởi động phiên agent mới. Muốn gỡ, xóa khối giữa hai marker hoặc khôi phục backup.
Codex: `$CODEX_HOME/AGENTS.md` hoặc `~/.codex/AGENTS.md`.
Claude Code: `~/.claude/CLAUDE.md`. Copilot CLI: `~/.copilot/copilot-instructions.md`.
Antigravity: `~/.gemini/GEMINI.md`. File Copilot CLI không đảm bảo mọi extension IDE đều đọc.
Quy tắc global có thể bị ảnh hưởng bởi precedence của từng sản phẩm; gate và sandbox
vẫn cần độc lập. Installer không tự cài firewall và không chỉnh credentials.

Mặc định dữ liệu Hub chỉ ở máy. Model provider vẫn nhận context bạn cho phép và có
chính sách dữ liệu riêng. Không đưa secrets/dữ liệu thật vào source, task, log hay pack.
