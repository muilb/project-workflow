# Khảo sát mã nguồn mở

Số sao, giấy phép và ngày commit lấy từ trang repo ngày 2026-11-25. Chưa cài
hay chạy thử dự án nào.

## Kết luận

Không chọn dự án nào làm nền. Phần lớn ra đời để lấp chỗ trống mà cross-session
messaging có sẵn của Claude Code nay đã lấp. Tự viết tầng nhắn tin chỉ hợp lý
khi cần đảm bảo tin không mất hoặc xác thực chặt giữa các phiên; chưa dự án nào
dưới đây làm trọn hai việc đó.

## Nhắn tin ngang hàng giữa các terminal thật

| Dự án | Cách liên lạc | Tình trạng | Lưu ý |
|---|---|---|---|
| [claude-peers-mcp](https://github.com/louislva/claude-peers-mcp) | MCP server + broker cục bộ (SQLite), đẩy tin vào terminal đang chạy | MIT, 2.2k sao, 7 commit, dừng từ 2026-04 | Cần cờ `--dangerously-load-development-channels`; có lỗi mất tin; không hỗ trợ Windows |
| [hcom](https://github.com/aannoo/hcom) | Hook + SQLite, gọi theo `@tên` và nhóm `@tag` | MIT, 673 sao, commit 2026-10 | Hỗ trợ cả Codex và Gemini |
| [repowire](https://github.com/prassanna-ravishankar/repowire) | Daemon Go định tuyến tin, hook + MCP | MIT, 279 sao, commit 2026-11-24 | Có xác thực bearer; cấu hình mẫu dùng `--dangerously-skip-permissions` |
| [mcp_agent_mail_rust](https://github.com/Dicklesworthstone/mcp_agent_mail_rust) | Hộp thư qua HTTP MCP; agent tự kiểm tra thư | 283 sao, commit 2026-11-24; bản Python đã ngừng | Giấy phép MIT kèm điều khoản loại trừ riêng; có đặt chỗ file để tránh ghi đè |
| [cc2cc](https://github.com/paulrobello/cc2cc) | Hub + Redis + WebSocket, định tuyến theo vai trò | MIT, 4 sao | Chỉ dùng trong mạng LAN tin cậy |

## Bộ điều phối

| Dự án | Cách liên lạc | Tình trạng | Lưu ý |
|---|---|---|---|
| [CLI Agent Orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | Supervisor + worker trong tmux; dán tin vào pane khi rảnh | Apache-2.0, 1.7k sao, commit 2026-11-25 | Profile theo vai trò có model riêng; mặc định dùng Kiro CLI |
| [Gas Town](https://github.com/gastownhall/gastown) | Mayor + worker trong tmux, hộp thư, sổ cái Beads | MIT, 18.9k sao, commit 2026-11-12 | Nặng (Go, Dolt, Beads); thiết kế cho 20–30 agent |
| [Ruflo](https://github.com/ruvnet/ruflo) | MCP server với bộ nhớ chung | MIT, 82.4k sao | Không phải nhắn tin ngang hàng; số liệu hiệu năng tự công bố |
| [Overstory](https://github.com/jayminwest/overstory) | Thư SQLite, model theo vai trò | Đã lưu trữ 2026-05 | Không dùng |

## Chỉ quản lý phiên, không có nhắn tin giữa agent

- [claude-squad](https://github.com/smtg-ai/claude-squad): AGPL-3.0, 8.9k sao;
  tmux + worktree.
- [agent-deck](https://github.com/asheshgoplani/agent-deck): MIT, 1.3k sao.

## Giao thức

- ACP nối editor với agent, không dùng để nhắn giữa các phiên.
- A2A: có cầu nối cộng đồng ([a2abridge](https://github.com/vbcherepanov/a2abridge),
  17 sao, một người phát triển); tin chỉ đến ở lượt prompt kế tiếp của phiên
  nhận.

## Rủi ro chung

Tin từ một phiên đi vào ngữ cảnh của phiên nhận, nên một phiên bị nhiễu có thể
kéo các phiên khác đi sai. Không dự án nào mô tả biện pháp kỹ thuật chống lại
điều này. Kết hợp với `--dangerously-skip-permissions` làm rủi ro nặng hơn.
