# Jev (TypeSafe AI): ghi chú API

Nguồn: tài liệu chính thức tại <https://docs.typesafe.ai>, đọc ngày 2026-11-25.
Mục lục đầy đủ cho máy đọc: <https://docs.typesafe.ai/llms.txt>. Chưa có lời
gọi API nào được chạy thử.

## Jev là gì

Mô hình ra quyết định, không sinh văn bản. Nhận một `state` và một bộ câu hỏi có
kiểu, trả về câu trả lời có cấu trúc kèm xác suất. Tài liệu nói rõ Jev không
thay được model của coding agent; nó dùng trong mã mình viết để định tuyến, phân
loại, chấm điểm.

## Gọi API

- Endpoint: `POST https://api.typesafe.ai/v1/systemone`
- Xác thực: `Authorization: Bearer $TYPESAFE_API_KEY`
- Ba trường bắt buộc: `model`, `state`, `questions`
- `questions` là một map từ mã câu hỏi tự đặt sang đối tượng câu hỏi. Mã câu hỏi
  không được gửi cho model; câu trả lời trả về dưới cùng mã đó.
- Model đọc `state` một lần và đánh giá mọi câu hỏi song song, nên gộp nhiều câu
  hỏi vào một request.
- SDK: `typesafe_sdk` (Python), `@typesafe-ai/sdk` (JavaScript). SDK tự thử lại
  khi gặp `429` và `529`.
- Đặc tả OpenAPI: <https://api.typesafe.ai/openapi.json>

## Model

| | Jev 1.14 | Jev 1.13 |
|---|---|---|
| Model ID | `jev-1.14.0` | `jev-1.13.0` |
| Giá đầu vào | 0,042 USD / 1 triệu token | 0,042 USD / 1 triệu token |
| Giá đầu ra | Miễn phí | Miễn phí |
| Ngữ cảnh | 64k mỗi request, 32k mỗi câu hỏi | như bên trái |

- Alias `jev-latest` hiện trỏ tới `jev-1.14.0`. Alias đổi khi có bản mới, nên
  sau khi chỉnh ngưỡng hãy gửi đúng model ID.
- Trường `model` trong response cho biết phiên bản đã trả lời; nên ghi vào log.
- Hạn mức đặt theo tổ chức, xem tại console của TypeSafe.

## Các kiểu câu hỏi

| Kiểu | `criteria` | Trả về |
|---|---|---|
| `choice` | Map: tên lựa chọn → mô tả | `choice`, `probabilities` (tổng bằng 1), `confidence` |
| `score` | Mảng có thứ tự các mức, từ thấp đến cao, tối đa 10 mức | `score` (vị trí trên thang, có thể nằm giữa hai mức), `probabilities` theo mức, `legend`, `confidence` |
| `noul` | Không cần | `noul`: xác suất câu trả lời là "có", từ 0 đến 1 |

Tên kiểu viết thường. `instructions` là câu hỏi mà model trả lời.

## Ví dụ request cho router

Tự soạn theo cấu trúc trong tài liệu, chưa chạy thử. Tên phiên và mô tả là giả
định.

```bash
curl https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-latest",
    "state": "Thêm cột last_login vào bảng users và trả nó về trong API /me.",
    "questions": {
      "recipient": {
        "type": "choice",
        "instructions": "Phiên nào nên nhận task này?",
        "criteria": {
          "frontend-client": "Giao diện, component, kiểu dữ liệu phía client",
          "backend-api": "Endpoint, logic nghiệp vụ, hợp đồng API",
          "db-migration": "Schema, migration, chỉ mục cơ sở dữ liệu"
        }
      },
      "fits_any": {
        "type": "noul",
        "instructions": "Task này có thuộc phạm vi của ít nhất một phiên trong danh sách không?"
      },
      "task_size": {
        "type": "score",
        "instructions": "Task này lớn cỡ nào?",
        "criteria": [
          "Sửa nhỏ trong một file",
          "Thay đổi trong một module",
          "Thay đổi liên module",
          "Cần thiết kế hoặc phải chia nhỏ"
        ]
      }
    }
  }'
```

Dạng response, theo các ví dụ trong tài liệu:

```json
{
  "model": "jev-1.14.0",
  "answers": {
    "recipient": {
      "type": "choice",
      "choice": "db-migration",
      "confidence": 0.5,
      "probabilities": { "frontend-client": 0.0, "backend-api": 0.33, "db-migration": 0.67 }
    },
    "fits_any": { "type": "noul", "noul": 0.98 },
    "task_size": {
      "type": "score",
      "score": 1.8,
      "confidence": 0.6,
      "legend": { "0": "...", "1": "...", "2": "...", "3": "..." },
      "probabilities": { "0": 0.0, "1": 0.3, "2": 0.6, "3": 0.1 }
    }
  },
  "usage": { "input_tokens": 0, "output_tokens": 0 }
}
```

Các con số trong response trên là minh họa, không phải kết quả thật.

## Cách đọc kết quả

- **`choice`:** dùng `probabilities[choice]`, tức xác suất lựa chọn đó đúng.
  `confidence` của `choice` được tính từ chính số này. Ví dụ ngưỡng trong tài
  liệu: dưới 0,7 thì không hành động; việc rủi ro cao cần trên 0,9.
- **`noul`:** trên 0,7 là có, dưới 0,3 là không; khoảng giữa cần nhánh xử lý
  riêng, không làm tròn về một phía.
- **`score`:** kiểm tra `confidence` trước (ví dụ trong tài liệu dùng 0,5); nếu
  đạt mới định tuyến theo `score`. Khi quyết định phụ thuộc vào một mức cụ thể,
  cộng xác suất của các mức ở phía cần quan tâm.
- **`choice` luôn chọn một lựa chọn**, kể cả khi không lựa chọn nào phù hợp. Tài
  liệu khuyên thêm một câu `noul` hỏi "có lựa chọn nào phù hợp không" trong cùng
  request, thay vì thêm lựa chọn "khác".
- Ngưỡng đúng phụ thuộc vào dữ liệu của mình: bắt đầu thận trọng, đo, rồi chỉnh.

Tài liệu liên quan:
<https://docs.typesafe.ai/confidence.md>,
<https://docs.typesafe.ai/patterns/probability-routing.md>,
<https://docs.typesafe.ai/patterns/confidence-routing.md>,
<https://docs.typesafe.ai/patterns/companion-noul.md>.

## Giới hạn và lỗi

| Mã | Ý nghĩa |
|---|---|
| `400` | Vi phạm quy tắc request, hoặc vượt ngữ cảnh (`max_tokens_exceeded`) |
| `401` | Thiếu hoặc sai khóa API |
| `422` | Request sai cấu trúc; thân lỗi nêu trường sai |
| `429` | Vượt hạn mức; thử lại với thời gian chờ tăng dần |
| `529` | Dịch vụ quá tải tạm thời |

Thân request tối đa 32 MiB, JSON UTF-8.

## Plugin cho Claude Code

Plugin chính thức giúp Claude viết mã gọi Jev đúng cấu trúc (nó không biến Jev
thành router):

```bash
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
```

Gọi trong phiên bằng `/typesafe:typesafe-ai`. Tài liệu khuyên đặt mọi câu hỏi và
ngưỡng vào một file duy nhất để dễ xem lại.

## Dữ liệu

Tài liệu nói Jev không được huấn luyện trên request hay response của khách hàng.
Chế độ không lưu dữ liệu chỉ có cho khách hàng doanh nghiệp. Chưa đọc thỏa thuận
xử lý dữ liệu.

## Công cụ bên thứ ba dùng Jev với Claude Code

Chỉ thấy qua kết quả tìm kiếm, chưa mở để kiểm chứng: `jev-router` (proxy chọn
model Claude cho từng tin), plugin `jev-route`, và `jev-model-router` (chọn
model cho subagent). Tất cả định tuyến giữa các model; không thấy công cụ nào
dùng Jev để chọn phiên nhận tin.
