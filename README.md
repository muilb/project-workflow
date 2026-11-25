# project-workflow

Hệ thống phối hợp nhiều phiên Claude Code trên cùng một máy: một phiên kiến trúc
(architect), một phiên xây dựng (builder) và các phiên worker, nhắn tin cho nhau
bằng tính năng cross-session messaging có sẵn của Claude Code. Jev (mô hình ra
quyết định của TypeSafe AI) chọn phiên nhận tin và ước lượng độ lớn của task.

Repo hiện mới có tài liệu, chưa có mã.

## Đọc theo thứ tự

1. [docs/HANDOFF.md](docs/HANDOFF.md): bối cảnh và việc cần làm tiếp trên PC.
2. [docs/PLAN.md](docs/PLAN.md): kiến trúc và các giai đoạn.
3. Tài liệu tham khảo đã kiểm chứng:
   - [docs/reference/claude-code-cross-session.md](docs/reference/claude-code-cross-session.md)
   - [docs/reference/jev-api.md](docs/reference/jev-api.md)
   - [docs/reference/open-source-survey.md](docs/reference/open-source-survey.md)
