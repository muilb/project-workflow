# Bàn giao sang phiên chạy trên PC

Tài liệu này dành cho phiên Claude Code chạy trực tiếp trên PC (thư mục làm việc
`D:\Work\Projects\000.BRC-AI`). Phiên đó không có nội dung cuộc trò chuyện gốc,
nên mọi thứ cần biết nằm ở đây và trong các file được liên kết.

## Bối cảnh

- Ý tưởng xuất phát từ một video minh họa "Claude Code cross-session messaging":
  Opus làm kiến trúc, Sonnet là phiên chính, các phiên Haiku làm worker, có một
  khối "JEV message router" đứng giữa.
- Phần nghiên cứu được làm trong một phiên cloud ngày 2026-11-25. Phiên cloud
  không nối được vào PC: trang Settings → Code → Remote Control của ứng dụng
  desktop trên PC chỉ có công tắc "Connect new sessions to Remote Control",
  không có danh sách thư mục để chia sẻ.
- Vì vậy các bước cần máy thật (chạy thử Claude Code, gọi Jev bằng khóa thật,
  đọc dự án đang dùng Jev) chuyển sang phiên trên PC.

## Đã xác lập

- Tầng nhắn tin giữa các phiên đã có sẵn trong Claude Code, không cần tự viết.
  Chi tiết: [reference/claude-code-cross-session.md](reference/claude-code-cross-session.md).
- Jev là mô hình ra quyết định qua API đóng, trả về lựa chọn kèm xác suất.
  Chi tiết: [reference/jev-api.md](reference/jev-api.md).
- Các dự án mã nguồn mở tương tự và lý do không chọn làm nền:
  [reference/open-source-survey.md](reference/open-source-survey.md).
- Kiến trúc và lộ trình: [PLAN.md](PLAN.md).

## Chưa biết, cần phiên trên PC trả lời

1. **Dự án "bvn aidd".** Người dùng cho biết có một dự án tên gần như vậy đang
   dùng Jev để định tuyến và quyết định độ lớn task. Phiên cloud không tìm thấy
   repo nào tên chứa "aidd". Hãy tìm nó trong `D:\Work\Projects\000.BRC-AI`,
   đọc các câu hỏi Jev, ngưỡng và cách ánh xạ độ lớn task sang model, để tái sử
   dụng thay vì viết lại.
2. **Hệ điều hành chạy Claude Code:** Windows gốc hay WSL 2. Hai môi trường này
   không nhắn được cho nhau, nên toàn bộ các phiên phải ở cùng một bên.
3. **Phiên bản Claude Code** (`claude --version`): cần từ v2.1.224, hoặc từ
   v2.1.234 nếu chạy Windows gốc.
4. **Dự án đích gồm những phần nào** (frontend, backend, database…), để đặt tên
   và phạm vi cho các worker.
5. **Gọi Jev qua đâu:** trực tiếp TypeSafe hay qua một gateway.

## Việc cần làm trước (giai đoạn 0)

Làm theo thứ tự; ghi kết quả vào `docs/phase0-results.md`.

1. Ghi lại hệ điều hành và `claude --version`.
2. Thử nhắn tin giữa hai phiên có tên:
   - Terminal A: `claude --name architect --model opus`
   - Terminal B: `claude --name builder --model sonnet`
   - Trong A, gõ `/peers` để xem B có hiện không, rồi yêu cầu Claude gửi một
     tin cho `@builder` và kiểm tra B nhận được.
3. Kiểm tra ba điểm tài liệu chưa nói rõ:
   - Phiên headless `claude -p` với `crossSessionInbound` là `accept` sống bao
     lâu khi chờ tin.
   - Hook `PreToolUse` có khớp được công cụ `SendMessage` không, và có chặn
     được lời gọi không.
   - Tin do một script tự gửi vào socket (`CLAUDE_CODE_MESSAGING_SOCKET`) mang
     tên người gửi là gì.
4. Gọi thử Jev bằng khóa trong biến môi trường `TYPESAFE_API_KEY` với request
   mẫu ở [reference/jev-api.md](reference/jev-api.md). Không ghi khóa vào file
   nào trong repo.
5. Tìm và đọc dự án "bvn aidd" (mục 1 ở trên).

## Sau giai đoạn 0

Tiếp tục giai đoạn 1 trong [PLAN.md](PLAN.md). Nhánh làm việc của repo này là
`ccr-9b77bcc0-r6lcgd`.
