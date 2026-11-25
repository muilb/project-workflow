# Kế hoạch

## Mục tiêu

Chạy nhiều phiên Claude Code trên một máy, mỗi phiên một vai trò và một model,
phối hợp với nhau qua tin nhắn. Một bước ra quyết định bằng Jev chọn phiên nhận
tin và ước lượng độ lớn của task trước khi giao việc.

Bộ công cụ dùng chung cho nhiều dự án: cài một lần trên máy, mỗi dự án chạy
`init` để sinh cấu hình riêng.

## Kiến trúc

Ba tầng tách biệt:

| Tầng | Dùng gì | Ghi chú |
|---|---|---|
| Vận chuyển | Cross-session messaging có sẵn của Claude Code (`ListAgents`, `SendMessage`) | Không tự viết socket hay mailbox |
| Quyết định | Jev, đóng gói thành công cụ `route` | Phiên gửi gọi `route` trước khi `SendMessage` |
| Ngữ cảnh (tùy chọn) | Graphify, đọc qua MCP server cục bộ `graphify-mcp` | Chỉ bật cho dự án từ khoảng 500 file; xem [reference/graphify.md](reference/graphify.md) |

Các lựa chọn thiết kế:

- **Jev là một công cụ, không phải một trạm trung chuyển.** Claude Code không có
  hook nào được tài liệu hóa để chặn và đổi hướng tin nhắn giữa đường. Cho một
  daemon tự bơm tin vào socket thì làm được, nhưng tên người gửi khi đó không
  được đảm bảo.
- **Mỗi phiên một git worktree** để các phiên không ghi đè file của nhau.
- **Mỗi phiên đặt tên bằng `--name` và chọn model bằng `--model`.**
- **Router nằm sau một giao diện chung**, để thay Jev bằng cách khác (ví dụ một
  lời gọi Haiku) mà không sửa phần còn lại.
- **Tên phiên kèm tên dự án** (ví dụ `shop-architect`, `shop-builder`). Mọi
  phiên cùng người dùng trên máy đều thấy nhau, không phân biệt thư mục, nên
  hai dự án cùng có phiên `builder` sẽ gửi nhầm. `route` chỉ chọn trong các
  phiên cùng tiền tố.
- **Mỗi dự án một đồ thị, dựng từ nhánh chính.** Mọi phiên của dự án đọc chung
  đồ thị đó qua `graphify-mcp`; không dựng riêng trong từng worktree và không
  gộp đồ thị giữa các dự án.
- **Không cài hook của graphify.** Phiên chủ động hỏi đồ thị khi cần, để không
  chèn ngữ cảnh vào mọi lệnh đọc file.

## Dùng chung cho nhiều dự án

### Cài một lần trên máy

Repo này là bộ công cụ, gồm:

- Prompt vai trò mẫu cho architect, builder, worker, và bốn mẫu tin.
- Công cụ `route` cùng bộ câu hỏi và ngưỡng Jev mặc định.
- Lệnh `init`, `up`, `down`, `status`.
- Graphify (gói `graphifyy`) cài ở mức máy, ghim một phiên bản.
- Khóa Jev chỉ nằm trong biến môi trường `TYPESAFE_API_KEY`.

### Sinh ra trong mỗi dự án khi `init`

| File | Nội dung | Commit |
|---|---|---|
| `.workflow/team.yaml` | Tiền tố dự án, tên phiên, model, worktree, chế độ quyền, `crossSessionInbound`, phạm vi từng worker, phiên bản bộ công cụ | Có |
| `.workflow/roles/` | Chỉ phần ghi đè riêng của dự án; còn lại lấy từ mẫu chung | Có |
| `.workflow/thresholds.yaml` | Ngưỡng Jev riêng, nếu khác mặc định | Có |
| `.mcp.json` | Khai báo `route` và `graphify-mcp` trỏ vào đồ thị của dự án | Có |
| `graphify-out/` | Đồ thị của dự án | Không; dựng lại được |
| `.workflow/log/` | Log quyết định của router | Không |

### `init` làm gì

1. Kiểm tra dự án: có git không, ngôn ngữ gì, bao nhiêu file.
2. Dựng đồ thị chỉ từ code với `GRAPHIFY_BACKEND=none`, nên không tốn token.
   Dự án dưới khoảng 500 file thì bỏ qua bước này và bước 3.
3. Đọc các cụm trong đồ thị, đề xuất danh sách worker và phạm vi, ghi vào
   `team.yaml` để người dùng sửa trước khi chạy `up`.
4. Ghi `.mcp.json` và bổ sung `.gitignore`.
5. Không cài hook nào.

Chạy lại `init` trên dự án đã có thì chỉ cập nhật đồ thị, không ghi đè những
file người dùng đã sửa.

### Giữ đồ thị không bị cũ

- Chạy `graphify update .` trên nhánh chính sau mỗi lần gộp việc của worker.
- Phiên phải đọc file thật trước khi sửa; đồ thị chỉ dùng để tìm chỗ.
- Tin giao việc cho worker kèm sẵn phần trích đồ thị liên quan tới task, để
  worker không phải tự tra cả đồ thị.

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

Khi dự án có đồ thị, số cụm mà task chạm tới là một tín hiệu để kiểm tra chéo
`task_size`: một cụm ứng với mức 0 hoặc 1, nhiều cụm ứng với mức 2 trở lên. Đây
là giả thuyết, chưa đo.

## Các giai đoạn

### Giai đoạn 0: xác minh trên máy thật

Xem checklist trong [HANDOFF.md](HANDOFF.md). Kết quả quyết định ba việc: chạy
worker ở dạng tương tác, chạy nền hay headless; có dùng được hook để ép quy tắc
gửi tin hay chỉ dựa vào prompt vai trò; và graphify có đáng bật trên dự án đích
không.

### Giai đoạn 1: khung đội hình và `init`, chưa có Jev

- Mẫu `team.yaml` và `roles/` dùng chung.
- Lệnh `init` như mô tả ở trên, thử trên một dự án thật.
- Script `up`, `down`, `status` đọc `team.yaml` của dự án hiện tại.
- Bắt đầu với ba phiên: architect, builder, một worker.

### Giai đoạn 2: quy ước phối hợp

- Bốn mẫu tin cố định: giao việc, kết quả, bị chặn, ký duyệt.
- Luồng chuẩn: builder giao việc → worker báo kết quả → architect kiểm tra diff
  và ký duyệt.
- Architect và builder dùng đồ thị khi chia việc và khi xem diff lan tới đâu.

### Giai đoạn 3: router Jev

- Công cụ `route` nhận nội dung tin, trả về người nhận, độ lớn task và quyết
  định cho gửi hay chặn.
- Câu hỏi và ngưỡng mặc định nằm trong một file duy nhất của bộ công cụ; mỗi dự
  án ghi đè qua `.workflow/thresholds.yaml`.
- Ghim phiên bản model (ví dụ `jev-1.14.0`) sau khi đã chỉnh ngưỡng.
- Ghi mọi quyết định vào log của dự án (nội dung rút gọn, câu trả lời, xác
  suất, phiên bản model) để chỉnh ngưỡng theo số liệu thật.
- Khi Jev lỗi hoặc vượt hạn mức: chuyển tin về architect.

### Giai đoạn 4: rào chắn

- Architect để `crossSessionInbound` là `hold`, worker để `accept`.
- Không phiên nào chạy ở chế độ bỏ qua quyền.
- Giới hạn số lần chuyển tiếp của một tin để tránh hai phiên nhắn qua lại vô
  hạn.
- Khóa API Jev chỉ nằm trong biến môi trường `TYPESAFE_API_KEY`.
- Đặt `GRAPHIFY_QUERY_LOG_DISABLE=1`; không dùng MCP hosted của graphify.

### Giai đoạn 5: mở rộng

- Tăng lên ba worker.
- Áp dụng cho dự án thứ hai, chạy song song với dự án đầu để kiểm tra tin không
  đi nhầm dự án.
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
- Phiên của hai dự án trên cùng máy thấy nhau. Tiền tố tên chỉ là quy ước; nếu
  một phiên gửi sai tên thì không có gì chặn.
- Đồ thị cũ có thể khiến phiên tin vào quan hệ không còn đúng.
- Số liệu tiết kiệm token của graphify do chính dự án đó tự đo; mức lợi thật
  trên dự án đích chưa biết.
- Graphify đổi gần như hàng ngày; bản mới có thể đổi tên công cụ MCP hoặc định
  dạng `graph.json`.
