# Kết quả giai đoạn 0

Chạy ngày 2026-11-28 trong container Linux của một phiên cloud, **không phải
trên PC**. Claude Code v2.1.332, các phiên thử dùng model Haiku. Những mục cần
PC vẫn để ngỏ ở cuối file.

## Đã kiểm chứng

| Câu hỏi | Kết quả |
|---|---|
| Hai phiên có tên thấy nhau không | Có. `ListAgents` liệt kê phiên kia theo tên, kèm định danh ngắn (`pw-builder [46ed9e]`), trạng thái `idle`/`busy` |
| Gửi và nhận tin | Có. `SendMessage` trả về `success: true` và `msg_id`; phiên nhận thấy đúng tên người gửi và trả lời lại được |
| Hook `PreToolUse` có khớp `SendMessage` không | Có, với `matcher: "SendMessage"`. Hook nhận `tool_input` gồm `to`, `message`, `summary` |
| Hook có chặn được không | Có. Thoát mã 2 thì tin không được gửi, stderr trả về cho Claude |
| Hook có đổi được người nhận không | Có. Trả `hookSpecificOutput.updatedInput` với `to` khác thì tin đi tới phiên mới; phiên gửi thấy người nhận thật trong kết quả |
| Phiên `claude -p` sống bao lâu khi chờ tin | Không chờ. Phiên một lượt thoát ngay khi xong (khoảng 6 giây). Tin trả lời đến trong lúc nó còn chạy thì vẫn được xử lý |
| Giữ phiên headless sống để nhận tin | Được, bằng `--input-format stream-json` và giữ stdin mở. Tin đến lúc rảnh mở một lượt mới |
| `--append-system-prompt-file` | Dùng được, dù `claude --help` không liệt kê riêng |
| Graphify dựng đồ thị chỉ từ code | Được: `GRAPHIFY_BACKEND=none graphify update .` (bản 0.9.119), không gọi LLM. `graphify-mcp <graph.json>` chạy qua stdio |

## Ghi nhận thêm

- `claude --bg` từ chối chạy trong thư mục chưa được tin cậy ("Workspace not
  trusted"); phải mở `claude` tương tác một lần ở thư mục đó trước. Mỗi
  worktree mới là một thư mục mới nên sẽ gặp hộp thoại này lần đầu.
- `SendMessage` là công cụ nạp trễ: phiên gọi `ToolSearch` trước lần gửi đầu.
- Mọi phiên cùng người dùng đều hiện trong `ListAgents`, kể cả phiên của dự án
  khác. Tiền tố tên là cần thiết.
- Graphify chia rất mịn: 246 file cho ra 381 cụm. Cụm không ánh xạ thẳng thành
  worker được, nên `pwf init` đề xuất worker theo thư mục.

## Chưa kiểm chứng được

- **Tin do script tự gửi vào socket.** Socket nằm ở `/tmp/cc-socks/<pid>.sock`.
  Hai dạng JSON đoán thử đều không được chuyển cho phiên nhận; định dạng dòng
  tin không có trong tài liệu. Không còn cần cho thiết kế, vì hook đã làm được
  việc chặn và đổi hướng.
- Phiên tương tác trong tmux: container này dừng ở màn hình chọn giao diện lần
  đầu nên không thử tiếp. `pwf up` tạo đúng cửa sổ tmux; phần còn lại cần máy
  đã đăng nhập.

## Hệ quả cho thiết kế

1. Quy tắc gửi tin ép được bằng hook, không chỉ dựa vào prompt vai trò. Giai
   đoạn 1 đã dùng: `pwf guard` chặn mọi `SendMessage` tới phiên ngoài
   `can_send_to`.
2. Jev đứng giữa đường được. Router ở giai đoạn 3 có thể là một hook
   `PreToolUse` tự gọi Jev rồi đổi `to` hoặc chặn, thay vì trông vào việc
   Claude nhớ gọi công cụ `route` trước khi gửi.
3. Worker nên là phiên tương tác (tmux hoặc tab terminal). Phiên `-p` một lượt
   không ở lại nhận việc; cách giữ stdin mở chạy được nhưng không ai xem được
   phiên đó.

## Còn lại cho phiên trên PC

1. Hệ điều hành (Windows gốc hay WSL 2) và `claude --version`.
2. Lặp lại phép thử hai phiên và hook trên máy đó, nhất là nếu là Windows gốc:
   lệnh hook và backend `wt` của `pwf` chưa chạy trên Windows lần nào.
3. Gọi thử Jev bằng `TYPESAFE_API_KEY`.
4. Tìm dự án "bvn aidd" và đọc cách nó dùng Jev.
5. Đo graphify trên dự án đích theo [reference/graphify.md](reference/graphify.md).
