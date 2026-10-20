# Test-only security boundary

V2 không thay đổi xác nhận synthetic/cách ly đã chọn. `ma` dùng home ngoài source;
`ma init` không tạo file metadata trong repo. Không có HTTP listener hoặc port public.
Setup mặc định không sửa client config/PATH cho tới khi operator lựa chọn; có backup,
ownership và rollback. `ma config --allow-mcp-config true` là quyền riêng cho MCP sửa
enabled/model; không cho MCP sửa security, command hoặc tăng ngân sách tùy ý.
Worker không được dispatch workflow đệ quy. Cờ bypass sandbox trong extra_args bị chặn.
Context bỏ .env, credential/private-key files, appsettings và các thư mục credential;
đây không phải DLP hoàn chỉnh hoặc ACL OS. Source vẫn phải được duyệt và synthetic.

Hub mặc định chặn workflow thật trước khi tạo worktree/đọc context. Demo `--simulate`
vẫn chạy trên fixture tự tạo, không gọi model. Mọi lời gọi CLI thật nhận GLOBAL_RULES.md.

## Điều kiện trước khi bật

1. Người dùng cho phép source cụ thể và xác nhận chỉ có dữ liệu synthetic. Không mở
   secrets, .env, DB thật hoặc log người dùng. Không đưa dữ liệu thật vào Git/task/memory.
2. Cách ly OS chỉ bắt buộc khi người dùng yêu cầu. Với project demo đã xác nhận chỉ dùng
   dữ liệu giả, người dùng có thể chọn `require_isolation: false`; không cần khai báo
   giả rằng môi trường đã cách ly. Nếu chưa rõ dữ liệu, vẫn chặn workflow thật.
3. Nếu dùng API, chỉ dùng tài khoản test và endpoint/port/method được cho phép. Không dùng
   `--network` không giới hạn. Giữ sandbox và permission của CLI, không thêm cờ bypass.
4. Khối security dưới đây thuộc toàn bộ Hub home, không phải riêng một project. Chỉ đăng
   ký source đã được phép và xác nhận synthetic trong home đó; dùng `--home` riêng nếu
   cần phạm vi khác. Các giá trị là quyết định/xác nhận của người vận hành. Agent chỉ cập
   nhật khi người dùng đã chỉ dẫn rõ, không tự xác nhận dữ liệu hay cách ly để né lỗi.

Ví dụ người dùng xác nhận dữ liệu giả và không yêu cầu cách ly OS:

```json
"security": {
  "require_isolation": false,
  "isolated_test_environment": false,
  "synthetic_data_only": true,
  "isolation_description": ""
}
```

Mặc định mới: `require_isolation` là false, nhưng `synthetic_data_only` vẫn false nên
workflow thật bị chặn tới khi người dùng xác nhận dữ liệu. Config cũ không có
`require_isolation` tiếp tục yêu cầu cách ly; người vận hành cần chọn rõ true/false
để chuyển policy. Dùng boolean JSON, không dùng chuỗi `"false"` hoặc `"true"`.

Nếu người dùng yêu cầu cách ly, đặt `require_isolation: true`; workflow thật bị chặn
tới khi người dùng xác nhận `isolated_test_environment: true` cùng
`isolation_description` không rỗng. Khi đó cần VM/container hoặc tài khoản OS riêng,
chỉ đưa source đã duyệt và synthetic vào; không mount home/secrets/production. Chặn
mạng tool mặc định bằng firewall/proxy, allowlist API test chính xác và tách mạng model
provider. Các test command cũng chạy trong ranh giới được yêu cầu đó.

Hub chưa triển khai ACL đọc file, firewall allowlist hoặc redaction/DLP hoàn chỉnh.
Codex workspace-write không đảm bảo chặn đọc mọi file ngoài repo. Các CLI còn lại cũng
không có sandbox thống nhất. Do đó không thể cam kết ngăn dữ liệu thật chỉ bằng RULE.
Không khai báo đã cách ly nếu chưa có. Không dùng `--network`: Hub chặn lựa chọn đó
trong workflow thật vì không kiểm chứng được endpoint. Không đặt provider flags bỏ qua
permission/sandbox.

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
