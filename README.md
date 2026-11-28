# project-workflow

Hệ thống phối hợp nhiều phiên Claude Code trên cùng một máy: một phiên kiến trúc
(architect), một phiên xây dựng (builder) và các phiên worker, nhắn tin cho nhau
bằng tính năng cross-session messaging có sẵn của Claude Code. Jev (mô hình ra
quyết định của TypeSafe AI) chọn phiên nhận tin và ước lượng độ lớn của task.

## Dùng thử

Cần Python 3.9 trở lên, git, Claude Code từ v2.1.224, và tmux (Linux, macOS, WSL)
hoặc Windows Terminal.

```bash
pip install -e .
```

Trong thư mục dự án đích:

```bash
pwf init
```

Lệnh này sinh `.workflow/team.yaml` với ba phiên (architect, builder, một
worker). Xem lại file rồi bật cả cụm:

```bash
pwf up
```

`pwf status` xem trạng thái, `pwf down` tắt. Mỗi phiên trừ architect chạy trong
một git worktree riêng ở `../<tên-dự-án>.worktrees/`. Một hook chặn mọi tin gửi
tới phiên ngoài danh sách `can_send_to` của phiên gửi.

Các phiên trao đổi bằng bốn mẫu tin cố định: `assign` (giao việc), `result`
(kết quả), `blocked` (bị chặn), `signoff` (ký duyệt). Tin sai mẫu bị chặn.
`pwf tasks` cho biết mỗi task đang ở bước nào.

Router Jev đã có khung nhưng tắt theo mặc định và chưa gọi Jev thật lần nào.
Bật bằng `router: jev` trong `.workflow/team.yaml`, với khóa trong biến môi
trường `TYPESAFE_API_KEY`. Xem trước quyết định cho một tin bằng `pwf route`.

Đã xong giai đoạn 1 và 2, và phần khung của giai đoạn 3.

## Đọc theo thứ tự

1. [docs/HANDOFF.md](docs/HANDOFF.md): bối cảnh và việc cần làm tiếp trên PC.
2. [docs/phase0-results.md](docs/phase0-results.md): những gì đã chạy thử thật.
3. [docs/PLAN.md](docs/PLAN.md): kiến trúc và các giai đoạn.
4. Tài liệu tham khảo đã kiểm chứng:
   - [docs/reference/claude-code-cross-session.md](docs/reference/claude-code-cross-session.md)
   - [docs/reference/jev-api.md](docs/reference/jev-api.md)
   - [docs/reference/open-source-survey.md](docs/reference/open-source-survey.md)
   - [docs/reference/graphify.md](docs/reference/graphify.md)
