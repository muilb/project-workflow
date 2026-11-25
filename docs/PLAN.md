# Kế hoạch

## Mục tiêu

Chạy nhiều phiên Claude Code trên một máy, mỗi phiên một vai trò và một model,
phối hợp với nhau qua tin nhắn. Một bước ra quyết định bằng Jev chọn phiên nhận
tin và ước lượng độ lớn của task trước khi giao việc.

## Kiến trúc

Hai tầng tách biệt:

| Tầng | Dùng gì | Ghi chú |
|---|---|---|
| Vận chuyển | Cross-session messaging có sẵn của Claude Code (`ListAgents`, `SendMessage`) | Không tự viết socket hay mailbox |
| Quyết định | Jev, đóng gói thành công cụ `route` | Phiên gửi gọi `route` trước khi `SendMessage` |

Các lựa chọn thiết kế:

- **Jev là một công cụ, không phải một trạm trung chuyển.** Claude Code không có
  hook nào được tài liệu hóa để chặn và đổi hướng tin nhắn giữa đường. Cho một
  daemon tự bơm tin vào socket thì làm được, nhưng tên người gửi khi đó không
  được đảm bảo.
- **Mỗi phiên một git worktree** để các phiên không ghi đè file của nhau.
- **Mỗi phiên đặt tên bằng `--name` và chọn model bằng `--model`.**
- **Router nằm sau một giao diện chung**, để thay Jev bằng cách khác (ví dụ một
  lời gọi Haiku) mà không sửa phần còn lại.

## Câu hỏi gửi cho Jev

Một request cho mỗi tin nhắn hoặc task, `state` là nội dung tin, kèm các câu hỏi
sau. Đây là đề xuất ban đầu; cần đối chiếu với dự án "bvn aidd" đang dùng Jev.

| Mã câu hỏi | Kiểu | Hỏi gì | Cách dùng kết quả |
|---|---|---|---|
| `recipient` | `choice` | Phiên nào nên nhận tin này | So ngưỡng trên `probabilities[choice]` |
| `fits_any` | `noul` | Tin có thuộc phạm vi của một phiên nào không | Dưới 0,3: bỏ qua `recipient`, chuyển cho architect |
| `task_size` | `score` | Task lớn cỡ nào (thang có thứ tự) | Kiểm tra `confidence` trước, rồi ánh xạ điểm sang model |
| `leaks` | `noul` | Tin có chứa bí mật hoặc đổ nguyên ngữ cảnh không | Trên 0,7: chặn, không gửi |

Quy tắc đọc kết quả, theo tài liệu Jev:

- `choice`: đặt ngưỡng trên xác suất của lựa chọn được chọn. `confidence` của
  `choice` được tính từ chính xác suất đó nên không thêm thông tin.
- `score`: kiểm tra `confidence` trước; nếu thấp, câu trả lời đang bị chia giữa
  các mức xa nhau và nên chuyển cho architect.
- `noul`: trên 0,7 là có, dưới 0,3 là không, khoảng giữa có nhánh xử lý riêng.
- Ngưỡng tăng theo rủi ro: việc dễ hoàn tác dùng ngưỡng thấp, việc khó hoàn tác
  (ví dụ migration cơ sở dữ liệu) dùng ngưỡng cao hơn.

Ánh xạ độ lớn task sang model (đề xuất, chưa đo):

| Mức | Mô tả | Giao cho |
|---|---|---|
| 0 | Sửa nhỏ trong một file | Worker Haiku |
| 1 | Thay đổi trong một module | Worker Haiku hoặc builder Sonnet |
| 2 | Thay đổi liên module | Builder Sonnet |
| 3 | Cần thiết kế hoặc phải chia nhỏ | Architect Opus tách việc |

## Các giai đoạn

### Giai đoạn 0: xác minh trên máy thật

Xem checklist trong [HANDOFF.md](HANDOFF.md). Kết quả quyết định hai việc: chạy
worker ở dạng tương tác, chạy nền hay headless; và có dùng được hook để ép quy
tắc gửi tin hay chỉ dựa vào prompt vai trò.

### Giai đoạn 1: khung đội hình, chưa có Jev

- `team.yaml`: tên phiên, model, worktree, chế độ quyền, giá trị
  `crossSessionInbound`, danh sách phiên được phép gửi tới.
- `roles/`: prompt vai trò cho architect, builder và từng worker.
- Script bật, tắt và xem trạng thái cả cụm.
- Bắt đầu với ba phiên: architect, builder, một worker.

### Giai đoạn 2: quy ước phối hợp

- Bốn mẫu tin cố định: giao việc, kết quả, bị chặn, ký duyệt.
- Luồng chuẩn: builder giao việc → worker báo kết quả → architect kiểm tra diff
  và ký duyệt.

### Giai đoạn 3: router Jev

- Công cụ `route` nhận nội dung tin, trả về người nhận, độ lớn task và quyết
  định cho gửi hay chặn.
- Câu hỏi và ngưỡng nằm trong một file duy nhất để dễ xem lại.
- Ghim phiên bản model (ví dụ `jev-1.14.0`) sau khi đã chỉnh ngưỡng.
- Ghi mọi quyết định vào log (nội dung rút gọn, câu trả lời, xác suất, phiên
  bản model) để chỉnh ngưỡng theo số liệu thật.
- Khi Jev lỗi hoặc vượt hạn mức: chuyển tin về architect.

### Giai đoạn 4: rào chắn

- Architect để `crossSessionInbound` là `hold`, worker để `accept`.
- Không phiên nào chạy ở chế độ bỏ qua quyền.
- Giới hạn số lần chuyển tiếp của một tin để tránh hai phiên nhắn qua lại vô
  hạn.
- Khóa API Jev chỉ nằm trong biến môi trường `TYPESAFE_API_KEY`.

### Giai đoạn 5: mở rộng

- Tăng lên ba worker.
- Bảng trạng thái cho cả cụm.
- Đánh giá độ chính xác của router từ log quyết định.

## Rủi ro đã biết

- Tin nhắn từ phiên khác đi vào ngữ cảnh của phiên nhận. Claude Code đánh dấu
  nó là tin từ phiên khác và không cho nó phê duyệt quyền, nhưng một phiên bị
  nhiễu vẫn có thể kéo các phiên khác đi sai hướng.
- Các phiên nhắn qua lại lâu vẫn tính vào mức sử dụng.
- Alias `jev-latest` có thể đổi model, làm lệch các ngưỡng đã chỉnh.
- Ba điểm tài liệu Claude Code chưa nói rõ (xem giai đoạn 0) có thể buộc đổi
  cách chạy worker.
