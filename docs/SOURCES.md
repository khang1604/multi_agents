# Nguồn và ý tưởng áp dụng

Đây là triển khai mới cho nhu cầu cá nhân, không fork hoặc sao chép mã các dự án bên dưới.
Không khẳng định tối ưu tuyệt đối; ưu tiên ít thành phần, kiểm chứng được và tiết kiệm quota.

- Maestro — https://github.com/RunMaestro/Maestro
  Áp dụng ý tưởng task runner theo tài liệu, worktree, retry có phân loại, review có điều phối.
  https://docs.runmaestro.ai/agent-resilience
- agent-intern — https://github.com/SinanTufekci/agent-intern
  Áp dụng mô hình MCP bọc CLI chính thức, dùng login riêng của CLI và phân biệt sandbox thực
  với giới hạn công cụ. Không sao chép adapter hoặc tự bypass lỗi sandbox Windows.
- Agent Deck — https://github.com/asheshgoplani/agent-deck
  Áp dụng quản lý trạng thái phiên, conductor thay thế được và event log.
- AI Maestro — https://github.com/23blocks-OS/ai-maestro
  Áp dụng bộ nhớ dự án và bàn giao giữa agent. V0.1 không xây vector DB/code graph hoặc multi-machine.

Giao thức chính thức:
- Codex structured repair — https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex
- Claude Code programmatic — https://code.claude.com/docs/en/headless
- Copilot CLI — https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference
- Antigravity MCP — https://antigravity.google/docs/mcp

Các điểm bổ sung theo yêu cầu riêng:
- Bộ điều phối độc lập model để leader chết không làm mất queue.
- Auto chọn mức công việc dưới budget cố định, không dùng LLM để ping/giám sát.
- Context Pack mang lại kết quả phân tích, file/range/hash và cache incremental.
- Idempotency, generation fencing, test evidence và không chấp nhận exit 0 là thành công.
- Archive code trước cleanup; không dọn lịch sử agent toàn cục.

Global instructions chính thức:
- Codex: https://developers.openai.com/codex/guides/agents-md
- Claude Code: https://code.claude.com/docs/en/memory
- Copilot CLI: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions
- Antigravity: https://www.antigravity.google/docs/rules/
