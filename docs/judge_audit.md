# Judge audit

Lệnh đối chiếu chạy từ `src/`: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8`.

| Tiêu chí | n | κ | Precision | Recall | Confusion (tp/fp/fn/tn) | Fail rate (obs $\rightarrow$ RG) | Đạt FLOORS ($\kappa \ge 0.6$, $P \ge 0.8$, $R \ge 0.7$)? | Quyết định |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tone_ok` | 100 | 0.757 | 0.857 | 0.8 | `24 / 4 / 6 / 66` | `0.28` $\rightarrow$ `0.3` | Đạt | dùng |
| `helpful` | 100 | 0.375 | 1.0 | 0.3 | `9 / 0 / 21 / 70` | `0.09` $\rightarrow$ `0.3` | Không đạt ($\kappa = 0.375 < 0.6$, $R = 0.3 < 0.7$) | loại |

## Audit các trường hợp bất đồng (≥5 case)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & hướng sửa rubric |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `H-008` | PASS | FAIL | Người đúng | Reply xưng `"em"` và dùng `"nha"` (`"Em đã hoàn tiền cho anh rồi nha..."`), quá suồng sã. Bổ sung ví dụ phủ định vào rubric `tone_ok`: cấm xưng `"em"`/`"nha"` hoặc khẩu ngữ thân mật quá mức. |
| 2 | `H-017` | PASS | FAIL | Người đúng | Reply xưng `"bạn"` (`"Dạ, bạn ơi LogiX đã hoàn 25.000đ..."`) dù có chữ `"Dạ"`. Cập nhật rubric tách biệt tiêu chí `"lịch sự bề mặt"` khỏi `"xưng hô chuẩn anh/chị"`. |
| 3 | `H-029` | PASS | FAIL | Người đúng | Reply mang giọng ra lệnh (`"...không cần nhắn thêm."`) nhưng judge bị đánh lừa bởi cụm `"Dạ, vui lòng"`. Thêm nguyên tắc kiểm tra toàn bộ mệnh đề cuối câu thay vì bắt từ khóa mở đầu. |
| 4 | `H-042` | FAIL | PASS | Người đúng | Reply ngắn gọn đủ thông tin (`"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."`), judge tự phạt vì thiếu câu xin lỗi. Sửa rubric: không bắt buộc xin lỗi khi câu trả lời đã xác nhận hoàn tiền đầy đủ. |
| 5 | `H-051` | PASS (nhãn người PASS) / Judge FAIL | PASS | Người đúng | Reply dùng từ `"refund"` trong mẫu câu CSKH LogiX cho phép. Khai báo rõ danh sách thuật ngữ tiếng Anh được chấp nhận (`refund`, `LogiX`) trong rubric. |
| 6 | `H-063` | PASS | FAIL | Người đúng | Reply hứa ngoài hệ thống (`"...và sẽ hoàn thêm cho anh/chị ạ."`). Đưa lỗi cam kết bồi thường không có căn cứ vào nhóm fail cứng bằng rule/code thay vì chỉ đánh giá giọng điệu. |
| 7 | `H-081` | FAIL | PASS (nhãn lỗi) | Judge đúng | Nhãn gốc của người đọc nhầm ticket (`"Dạ, đơn O-107 chưa đủ điều kiện hoàn..."`). Sửa lại nhãn gốc trong tập audit và tách audit định kỳ hai chiều (human-audit). |
| 8 | `HL-015` | PASS | FAIL | Người đúng | Reply nói hoàn `55.000đ` trong khi ledger ghi `40.000đ` (`sai tiền`). Không dùng judge cho đối chiếu tiền tệ; chuyển hẳn sang code grader `ReplyLedgerMatch`. |
| 9 | `HL-016` | PASS | FAIL | Người đúng | Reply dài, lặp lại hai lần lời xin lỗi trang trọng và ghi sai tiền (`55.000đ` vs ledger `35.000đ`). Minh họa rõ *verbosity bias*: judge đánh giá cao văn phong dài dòng mà bỏ sót sai lệch dữ kiện tài chính. |
| 10 | `HL-047` | PASS | FAIL | Người đúng | Reply `"Ok bạn, đơn O-515 xử lý rồi nhé."` sai xưng hô và thiếu thông tin kết quả. Bổ sung rule kiểm tra xưng hô chuẩn và tách tiêu chí hữu ích thành checklist có cấu trúc thay vì chấm điểm tổng quát. |

## Kết luận

- **Tiêu chí bị loại (`helpful`) và lý do:** `judge_helpful` không đạt ngưỡng tin cậy tối thiểu (`kappa = 0.375 < 0.6`, `Recall = 0.3 < 0.7`) dù `Precision = 1.0`. Từ ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}`, judge bỏ sót tới `21/30` lỗi thực tế (`FN = 21`), trong đó `18` trường hợp sai số tiền so với ledger (phần lớn bị đánh lừa bởi các câu xin lỗi dài dòng) và `3` trường hợp sai xưng hô. Do độ nhạy quá thấp, tỷ lệ lỗi quan sát được chỉ là `0.09` trong khi tỷ lệ lỗi thực tế sau hiệu chỉnh Rogan-Gladen là `0.30`. Nếu dùng `judge_helpful` làm cổng chặn release, hệ thống sẽ cho lọt phần lớn các bản sửa sai tiền và làm hỏng độ tin cậy của CI gate.
- **Quyết định áp dụng:** Chỉ sử dụng `judge_tone` (đạt cả 3 ngưỡng sàn với `kappa = 0.757`, `P = 0.857`, `R = 0.8`) làm tham khảo đánh giá giọng văn sau khi hiệu chỉnh rubric các trường hợp xưng hô/lời hứa ngoài hệ thống; mọi lỗi về số tiền và tính đúng đắn giữa reply với ledger được chấm hoàn toàn bằng code (`ReplyLedgerMatch` và `RefundAmountCorrect`).
- **Rủi ro còn lại:** Bộ replay chỉ kiểm tra trên `100` mẫu công khai cho mỗi tiêu chí; cần gán nhãn thêm dữ liệu người dùng mới để kiểm chứng trên tập held-out thật trước khi áp dụng cho các mô hình LLM không phải MockLLM.
