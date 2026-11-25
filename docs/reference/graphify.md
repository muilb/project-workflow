# Graphify

Nguồn: README và `BENCHMARKS.md` của repo, trang PyPI, đọc ngày 2026-11-25. Các
bài đánh giá bên ngoài mới chỉ đọc qua phần trích trong kết quả tìm kiếm. Chưa
cài hay chạy thử.

## Kết luận

Dùng làm lớp ngữ cảnh bổ sung cho từng phiên, không thay tầng vận chuyển hay
tầng quyết định. Chỉ bật cho dự án từ khoảng 500 file trở lên, và phải đo trên
dự án thật trước khi coi là mặc định (xem "Cách đo").

## Thông tin cơ bản

| Mục | Giá trị |
|---|---|
| Repo | <https://github.com/Graphify-Labs/graphify> (trước là `safishamsi/graphify`) |
| Giấy phép | Apache-2.0 và MIT |
| Gói PyPI | `graphifyy` (hai chữ y); lệnh vẫn là `graphify` |
| Phiên bản | 0.9.119, ra ngày 2026-11-24 |
| Python | 3.11.5 đến 3.14 |
| Windows gốc | Có hỗ trợ |
| Tình trạng | Khoảng 153k sao, 800 issue và 942 PR đang mở; đổi gần như hàng ngày |

Có nhiều repo fork cùng tên. Chỉ cài từ gói `graphifyy` và ghim phiên bản.

## Cách hoạt động

- Code: phân tích bằng tree-sitter (khoảng 40 ngôn ngữ) ngay trên máy, không
  gọi LLM. Bắt được lời gọi, import, kế thừa, mixin.
- Tài liệu, PDF, ảnh, video: gửi cho LLM để trích ý. `GRAPHIFY_BACKEND=none`
  tắt hẳn phần này.
- Gom cụm thành các "community" bằng Leiden; thiếu gói phụ thì âm thầm dùng
  Louvain.
- Mỗi cạnh được gắn nhãn `EXTRACTED` (có sẵn trong mã) hoặc `INFERRED` (do
  graphify suy ra).
- Đầu ra trong `graphify-out/`: `GRAPH_REPORT.md`, `graph.json`, `graph.html`.

## Cách phiên Claude dùng đồ thị

| Cách | Ghi chú |
|---|---|
| MCP server cục bộ `graphify-mcp` | Công cụ: `query_graph`, `shortest_path`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `get_pr_impact`. Đây là cách workflow này dùng |
| Skill `/graphify` | `query`, `path`, `explain`; có `--budget N` (mặc định 2000) và `--depth N` (mặc định 2) |
| Hook (`graphify claude install`) | Chạy trước Read, Glob và các lệnh Bash đọc file; chèn nhắc nhở vào mọi lần đọc. Không dùng |
| MCP hosted `api.graphify.com` | Gửi dữ liệu ra ngoài. Không dùng |

Cập nhật: `graphify update .` hoặc `--update` chỉ trích lại file đã đổi.
`graphify hook install` gắn git hook dựng lại khi commit và đổi nhánh.

## Số liệu về token và độ chính xác

Toàn bộ do dự án tự đo; chưa thấy phép đo độc lập nào đủ chặt.

| Nguồn | Kết quả | Lưu ý |
|---|---|---|
| `BENCHMARKS.md`, repo ERPNext khoảng 1 triệu dòng | Độ phủ ý chính 82,0% so với 70,8% của cách grep và đọc file | Chỉ 6 câu hỏi |
| Cùng benchmark | Khoảng 140K token mỗi câu hỏi khi dùng graphify | Không phải vài nghìn token |
| Con số "71 lần" | Khoảng 1.700 token so với 123.000 cho một câu hỏi | Một phép đo đơn lẻ |
| Issue 985 trên repo | Người dùng báo Claude Code tự làm cho kết quả tương đương với token bằng hoặc thấp hơn ở nhiều câu hỏi thường gặp | Một người dùng |
| Kiểm tra cạnh `INFERRED` | 12/12 đúng trên FastAPI | Kiểm tra tay một lần, ngày 2026-10-05 |

Các bài đánh giá bên ngoài cho rằng dưới khoảng 100 file thì gần như không lợi,
và phải từ khoảng 500 file công dựng đồ thị mới được bù lại.

## Giới hạn

- Đồ thị cũ đi khi code đổi. Nhiều worktree cùng sửa thì cũ nhanh hơn.
- README không nói gì về gọi động, reflection, dependency injection hay quan hệ
  giữa các ngôn ngữ (ví dụ frontend gọi backend qua HTTP). Coi như đồ thị thiếu
  các cạnh này cho đến khi kiểm tra được.
- README không nói về worktree hay việc commit `graphify-out/`.
- Mọi câu hỏi được ghi vào `~/.cache/graphify-queries.log`; tắt bằng
  `GRAPHIFY_QUERY_LOG_DISABLE=1`.
- Đồ thị giúp tìm đúng chỗ, không thay việc đọc file thật trước khi sửa.

## Cách đo

1. Chọn 8 đến 10 task thật đã làm xong, trộn câu hỏi cấu trúc với sửa nhỏ.
2. Chạy mỗi task hai lần bằng cùng model: một lần không có đồ thị, một lần có
   `graphify-mcp`, không bật hook.
3. Ghi token đầu vào, số lượt gọi công cụ, và kết quả đúng hay sai.

Nếu token không giảm rõ ở nhóm câu hỏi cấu trúc thì tắt graphify cho dự án đó.

## Nguồn

- <https://github.com/Graphify-Labs/graphify>
- <https://github.com/Graphify-Labs/graphify/blob/HEAD/BENCHMARKS.md>
- <https://github.com/Graphify-Labs/graphify/issues/985>
- <https://pypi.org/project/graphifyy/>
- <https://www.roborhythms.com/graphify-review/>
- <https://codeconductor.ai/blog/graphify-review/>
- <https://www.mindstudio.ai/blog/graphify-claude-code-knowledge-graph-large-codebase-70x>
