# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có (PASS) | dùng (với kiểm soát định kỳ) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (FAIL: κ<0.6, R<0.7) | loại (không dùng làm gate) |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | `H-008` (tone): *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* | PASS | FAIL | Người đúng | Xưng hô thân mật ("nha", "check giúp em") không đúng chuẩn CSKH chuyên nghiệp của LogiX ("Dạ", "anh/chị"). Cần bổ sung vào rubric danh sách từ ngữ suồng sã bị cấm. |
| 2 | `H-029` (tone): *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* | PASS | FAIL | Người đúng | Câu có "Dạ" ở đầu nhưng giọng điệu cộc lốc, ra lệnh ("không cần nhắn thêm"). Cần sửa rubric để không chỉ chấm theo từ khóa lịch sự đầu câu. |
| 3 | `H-042` (tone): *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* | FAIL | PASS | Người đúng | Câu trả lời lịch sự, rõ ràng và cung cấp thông tin thời gian nhận tiền hữu ích; judge phạt nhầm (FP). Cần thêm ví dụ mẫu PASS có thông tin bổ sung vào prompt judge. |
| 4 | `H-070` (tone): *"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"* | PASS | FAIL | Người đúng | Dùng emoji cười cợt không phù hợp trong giao tiếp CSKH chính thức. Cần thêm quy tắc cấm emoji không phù hợp vào rubric. |
| 5 | `HL-016` (helpful): *"Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của..."* | PASS | FAIL | Người đúng | Trả lời dài dòng, xin lỗi suông nhưng không nêu hành động/kết quả xử lý cụ thể (verbosity bias của judge). Cần sửa rubric yêu cầu kiểm tra có thông tin hành động hoặc trạng thái đơn cụ thể. |
| 6 | `HL-047` (helpful): *"Ok bạn, đơn O-515 xử lý rồi nhé."* | PASS | FAIL | Người đúng | Thiếu chi tiết xử lý gì, số tiền/trạng thái cụ thể là gì. Judge bỏ sót vì quá khoan dung (FN). Cần làm rõ tiêu chí "helpful" phải có bước tiếp theo hoặc số liệu xác nhận. |

## Kết luận
- **Tiêu chí bị loại và lý do:** `helpful` bị loại khỏi CI gate vì `κ = 0.375` (< 0.6) và `Recall = 0.300` (< 0.7). Theo ma trận nhầm lẫn (`tp=9, fp=0, fn=21, tn=70`), judge bỏ sót tới **21/30** ca không hữu ích (FN cao, thiên vị câu dài dòng/lịch sự), khiến tỉ lệ lỗi quan sát chỉ là `0.09` dù tỉ lệ lỗi thực tế sau hiệu chỉnh Rogan-Gladen lên tới `0.30`. Nếu dùng làm gate sẽ cho lọt regression về chất lượng trả lời.
- **Tiêu chí được giữ:** `tone_ok` đạt cả 3 sàn (`κ = 0.757`, `P = 0.857`, `R = 0.800`, `observed 0.28 -> corrected 0.30`), đủ tin cậy để theo dõi, nhưng vẫn cần cập nhật rubric cho các edge case (từ suồng sã, emoji, giọng điệu cộc lốc).
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
