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
| Quyết định | Jev, gọi từ hook `PreToolUse` của `SendMessage` | Hook đổi người nhận hoặc chặn tin; có thêm công cụ `route` để hỏi trước |
| Ngữ cảnh (tùy chọn) | Graphify, đọc qua MCP server cục bộ `graphify-mcp` | Chỉ bật cho dự án từ khoảng 500 file; xem [reference/graphify.md](reference/graphify.md) |

Các lựa chọn thiết kế:

- **Jev chạy trong hook `PreToolUse` của `SendMessage`.** Giai đoạn 0 cho thấy
  hook này chặn được lời gọi và đổi được trường `to`
  ([phase0-results.md](phase0-results.md)). Router vì vậy không phụ thuộc vào
  việc Claude nhớ gọi một công cụ trước khi gửi. Công cụ `route` vẫn có, để
  phiên hỏi trước khi soạn tin.
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
| `graphify-out/` | Đồ thị của dự án | Không; dựng lại được |
| `.workflow/log/` | Log quyết định của router | Không |
| `.workflow/run/` | Prompt, settings và cấu hình MCP sinh ra cho từng phiên mỗi lần `up` | Không |

### `init` làm gì

1. Kiểm tra dự án: có git không, ngôn ngữ gì, bao nhiêu file.
2. Dựng đồ thị chỉ từ code với `GRAPHIFY_BACKEND=none`, nên không tốn token.
   Dự án dưới khoảng 500 file thì bỏ qua bước này và bước 3.
3. Đề xuất danh sách worker và phạm vi theo thư mục, ghi vào `team.yaml` để
   người dùng sửa trước khi chạy `up`. Cụm của graphify quá mịn để dùng thẳng
   (246 file cho 381 cụm).
4. Bổ sung `.gitignore`. `graphify-mcp` được nối vào từng phiên lúc `up` bằng
   `--mcp-config` với đường dẫn tuyệt đối, vì worktree không có `graphify-out/`
   nên một `.mcp.json` dùng đường dẫn tương đối sẽ không chạy ở đó.
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

Đã có mã trong gói `pwf`; đã chạy thử trên Linux, chưa chạy trên Windows.

- Mẫu `team.yaml` và `roles/` dùng chung.
- Lệnh `init` như mô tả ở trên, thử trên một dự án thật.
- Script `up`, `down`, `status` đọc `team.yaml` của dự án hiện tại.
- Bắt đầu với ba phiên: architect, builder, một worker.
- `pwf guard`: hook chặn `SendMessage` tới phiên ngoài `can_send_to`.

### Giai đoạn 2: quy ước phối hợp

Đã có mã trong `pwf/messages.py`. Đã chạy thử trên Linux với hai phiên Haiku:
builder giao việc, worker commit và báo kết quả, không tin nào bị chặn. Chưa
chạy thử đoạn architect ký duyệt với phiên thật.

- Mẫu tin: dòng đầu `[pwf:<loại>] <mã-task>`, sau đó là các trường bắt buộc.
  Hook `pwf guard` chặn tin sai mẫu hoặc sai chiều và trả mẫu đúng cho phiên
  gửi. Không có tin tự do; cần hỏi lại thì dùng `blocked`.
- Chiều gửi: architect → builder (`assign`, `signoff`); builder → worker
  (`assign`); builder → architect và worker → builder (`result`, `blocked`).
- Tin được cho qua ghi vào `.workflow/log/messages.jsonl`; `pwf tasks` cho biết
  trạng thái mới nhất của từng task.

- Bốn mẫu tin cố định: giao việc, kết quả, bị chặn, ký duyệt.
- Luồng chuẩn: builder giao việc → worker báo kết quả → architect kiểm tra diff
  và ký duyệt.
- Architect và builder dùng đồ thị khi chia việc và khi xem diff lan tới đâu.

### Giai đoạn 3: router Jev

Phần khung đã có mã (`pwf/router.py`, `pwf/templates/router.yaml`), tắt theo mặc
định; bật bằng `router: jev` trong `team.yaml`. Đã test bằng response giả và đã
chạy với phiên Claude thật gọi một máy chủ Jev giả trên máy. **Chưa gọi Jev thật
lần nào**: dạng request và response lấy từ tài liệu, ngưỡng chưa chỉnh theo số
liệu, và chưa đối chiếu với dự án "bvn aidd".

Cách router xử lý một tin đã đúng mẫu:

| Tin | Hỏi Jev | Kết quả |
|---|---|---|
| Mọi tin | `leaks` | Trên 0,7: chặn |
| `assign` từ builder cho worker | thêm `fits_any`, `task_size`, và `recipient` nếu có từ hai worker | Xem dưới |

- `fits_any` dưới 0,3: chặn, bảo builder tự làm hoặc hỏi architect.
- `task_size` có `confidence` dưới 0,5, hoặc điểm trên 2,5: chặn, bảo builder
  gửi architect tin `blocked` để xin chia việc. Điểm trên 1,5: chặn, bảo
  builder tự làm hoặc tách nhỏ.
- `recipient` khác người builder chọn và xác suất từ 0,7: đổi người nhận. Thấp
  hơn thì giữ lựa chọn của builder.
- Jev lỗi, vượt hạn mức hoặc thiếu khóa: tin giao việc cho worker bị chặn kèm
  hướng dẫn hỏi architect; các tin khác đi tiếp mà không kiểm tra `leaks`. Đổi
  bằng `on_error: allow`. Vì luồng tin cố định không cho builder gửi `assign`
  lên architect, "chuyển về architect" được làm bằng cách chặn và hướng dẫn,
  không phải đổi người nhận.
- Mọi quyết định ghi vào `.workflow/log/router.jsonl`.
- `pwf route --from <phiên> --to <phiên> "<tin>"` cho xem quyết định mà không
  gửi. Công cụ `route` dạng MCP chưa làm.

- Mở rộng hook `pwf guard`: gọi Jev với nội dung tin, rồi cho gửi, đổi người
  nhận hoặc chặn. Công cụ `route` trả cùng kết quả cho phiên muốn hỏi trước.
- Câu hỏi và ngưỡng mặc định nằm trong một file duy nhất của bộ công cụ; mỗi dự
  án ghi đè qua `.workflow/thresholds.yaml`.
- Ghim phiên bản model (ví dụ `jev-1.14.0`) sau khi đã chỉnh ngưỡng.
- Ghi mọi quyết định vào log của dự án (nội dung rút gọn, câu trả lời, xác
  suất, phiên bản model) để chỉnh ngưỡng theo số liệu thật.
- Khi Jev lỗi hoặc vượt hạn mức: chuyển tin về architect.

### Giai đoạn 4: rào chắn

Đã có mã. Đã chạy thử trên Linux với một phiên thật chạm giới hạn tin: phiên bị
chặn và dừng lại báo người dùng.

- `pwf check` rà cấu hình, và chạy trước mỗi `pwf up`. Lỗi (dừng `up`): Claude
  Code thiếu hoặc quá cũ; file trong `.workflow/` trông như chứa khóa. Cảnh báo:
  architect không để `hold`, worker không để `accept` hoặc thiếu `scope`, phiên
  chạy lệnh không hỏi, `.gitignore` thiếu dòng, bật router mà chưa đặt khóa.
- Giới hạn chuyển tiếp tính theo task: mặc định 12 tin (`limits.messages_per_task`
  trong `team.yaml`). Chạm giới hạn thì mọi tin về task đó bị chặn, trừ
  `signoff`; người dùng mở lại bằng `pwf reopen <mã-task>`.
- Settings của mỗi phiên có `permissions.disableBypassPermissionsMode`. Tài
  liệu Claude Code không thống nhất về việc khóa này có hiệu lực ngoài managed
  settings hay không, và chưa chạy thử; rào chắn chắc chắn là `team.yaml` từ
  chối `bypassPermissions`.

Các mục gốc của giai đoạn này:

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
- Hook và backend Windows Terminal chưa chạy trên Windows gốc lần nào.
- Hook chặn cả `SendMessage` tới subagent của chính phiên đó, vì không phân
  biệt được với tên phiên.
- Phiên của hai dự án trên cùng máy thấy nhau. Hook `pwf guard` chặn phiên của
  bộ công cụ gửi ra ngoài `can_send_to`, nhưng không chặn được phiên lạ gửi
  vào.
- Đồ thị cũ có thể khiến phiên tin vào quan hệ không còn đúng.
- Số liệu tiết kiệm token của graphify do chính dự án đó tự đo; mức lợi thật
  trên dự án đích chưa biết.
- Graphify đổi gần như hàng ngày; bản mới có thể đổi tên công cụ MCP hoặc định
  dạng `graph.json`.
