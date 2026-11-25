# Claude Code: nhắn tin giữa các phiên và các cách điều phối khác

Nguồn: tài liệu chính thức tại <https://code.claude.com/docs/en/cross-session-messaging>,
đọc ngày 2026-11-25. Chưa có mục nào dưới đây được chạy thử trên máy thật. Các
mục ghi "tài liệu không nói" là chỗ cần kiểm tra ở giai đoạn 0.

## Cross-session messaging

**Yêu cầu phiên bản**

| Nền tảng | Phiên bản tối thiểu |
|---|---|
| macOS, Linux, WSL 2 | v2.1.224 |
| Windows gốc | v2.1.234 |
| Bedrock, Claude Platform trên AWS, Google Cloud, Microsoft Foundry | v2.1.248 |

Tự bật khi đủ phiên bản. WSL 2 và Windows gốc không nhắn được cho nhau;
container và máy chủ cũng vậy.

**Đặt tên và địa chỉ**

- Đặt tên khi khởi chạy bằng `--name`, hoặc trong phiên bằng `/rename`.
- Claude gửi tin bằng công cụ `SendMessage` theo tên phiên. Người dùng có thể gõ
  `@tên` để chọn phiên.
- Nếu nhiều phiên trùng tên, Claude Code thêm một định danh ngắn vào từng dòng.

**Xem các phiên**

- `/list-agents` (bí danh `/peers`), hoặc công cụ `ListAgents`.
- Liệt kê subagent, teammate, các phiên cục bộ khác, phiên cloud và phiên Remote
  Control trên máy khác.
- Phiên cục bộ chỉ hiện nếu nó mở socket hộp thư. Phiên `-p` và phiên chạy nền
  có mở; phiên `--bare` thì không.
- Chỉ các phiên cùng người dùng hệ điều hành thấy nhau. Tài liệu không yêu cầu
  cùng thư mục dự án.

**Setting `crossSessionInbound`**

| Giá trị | Hành vi |
|---|---|
| `accept` | Chuyển tin cho Claude |
| `hold` | Hiện thông báo, giữ tin lại; được thả ra nếu sau đó áp dụng `accept` |
| `refuse` | Bỏ tin |

- Khi không đặt: quyết định theo chế độ quyền của hai phiên. Cùng nhóm (cùng bỏ
  qua quyền, hoặc cùng không) thì chuyển thẳng; khác nhóm thì giữ lại chờ duyệt.
- Đặt được trong user, project, local settings, `--settings` và managed
  settings. `refuse` ở project hoặc local thắng các nguồn khác.
- Tin bị giữ theo mặc định hết hạn sau `dialogExpiry` (mặc định năm phút). Tin
  bị giữ do `hold` tường minh thì không hết hạn.

**Phía nhận**

- Claude được báo rằng tin đến từ một phiên khác, không phải từ người dùng.
- Tin nhắn không phê duyệt được quyền, không đổi được cấu hình, và lệnh slash
  trong tin không được chạy.
- Nếu phiên đang chạy, Claude đọc tin giữa các lời gọi công cụ. Nếu đang rảnh,
  một lượt mới bắt đầu.
- Trả lời bằng `SendMessage`.

**Vận chuyển**

- Socket Unix riêng cho mỗi phiên (named pipe trên Windows). Tin cùng máy không
  đi qua máy chủ Anthropic.
- Đường dẫn socket có trong `/status` và biến `CLAUDE_CODE_MESSAGING_SOCKET`;
  token trong `CLAUDE_CODE_MESSAGING_TOKEN`. Dòng đầu có thể là
  `{"type":"auth","token":"<token>"}`: bắt buộc trên Windows gốc, tùy chọn ở các
  nền tảng khác.

**Giới hạn**

- Chỉ văn bản thuần, khoảng 1.000.000 ký tự mỗi tin trên cùng máy.
- Tối đa 100 tin đang giữ và 50 tin đã nhận trong hàng đợi.
- Có giới hạn tần suất theo người gửi và bỏ tin lặp y hệt; tài liệu không nêu
  con số.

**Tài liệu không nói**

- Phiên `-p` sống bao lâu khi chờ tin.
- Tên người gửi của tin do script tự gửi vào socket. Một công cụ bên thứ ba
  (cc-peer) ghi nhận là `unknown`; chưa kiểm chứng.
- Có hook nào chạy khi gửi hoặc nhận tin không, và `PreToolUse` có sửa được
  trường `to` của `SendMessage` không.
- Không có lệnh CLI kiểu `claude send` để chương trình ngoài gửi tin.

## Các cách điều phối có sẵn khác

| Tính năng | Terminal riêng | Agent nhắn trực tiếp cho nhau | Trạng thái | Cách bật |
|---|---|---|---|---|
| Cross-session messaging | Có | Có | Chính thức | Tự động |
| Agent teams | Không (một lead; teammate trong tiến trình hoặc pane tmux) | Có, kèm danh sách task chung | Thử nghiệm | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| Subagent | Không | Hạn chế; chủ yếu trả kết quả về phiên gọi | Ổn định | `.claude/agents/*.md` |
| Phiên chạy nền (`claude --bg`) | Có | Qua cross-session messaging | Research preview | `claude --bg "..."` |
| Dynamic workflows | Không (một script) | Không; kết quả đi qua script | Tùy gói | `/workflows` |

Giới hạn đáng chú ý của agent teams: không khôi phục được phiên của teammate
chạy trong tiến trình, mỗi phiên chỉ một team, không lồng team, cần phiên tương
tác (không dùng được với `-p` hay SDK).

Tài liệu: <https://code.claude.com/docs/en/agent-teams>,
<https://code.claude.com/docs/en/sub-agents>,
<https://code.claude.com/docs/en/agent-view>,
<https://code.claude.com/docs/en/workflows>.

Không tìm thấy plugin điều phối đa agent nào do Anthropic phát hành.
