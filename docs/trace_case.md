# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Phân tích trace case `C-002@11`

| Trường | Nội dung |
| :--- | :--- |
| Trial | `seeded_regression C-002@11`, trong report [eval_seeded_regression.json](../src/reports/eval_seeded_regression.json) (`run_id`: `E-seeded_regression-20261118-4373`) |
| Triệu chứng | `TrialPass` (`lab8`) fail với lý do `status resolved != denied`; `RefundAmountCorrect` fail (`ledger=20000 != expected=0`); `DbFactKept` fail (`1 override event(s)`). Reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` và ledger ghi `refund_vnd=20000`, `refund_count=1`, trong khi nhãn chuẩn là `denied` với `refund_vnd=0`. |
| Bước sai đầu tiên | Event `3` (`model_override`): `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event `1` (`handoff`) giao đúng phạm vi công cụ đọc (`["lookup_order", "lookup_policy", "compute_compensation"]`); Event `2` (`investigator`) truy xuất đúng đơn `O-202` từ DB với `status="delivered"`, `delay_days=2`, nên trước Event `3` toàn bộ dữ kiện cấu trúc trong trạng thái chạy đều chính xác. Chỉ từ Event `3` trở đi biến `delay_days` mới bị ghi đè bằng số `5` trích từ ticket, dẫn tới Event `4` (`quote`) tính sai `amount_vnd=20000` và ghi nhầm vào ledger. |
| Failure mode | `FM-03` (`ticket_trust`) trong [failure_taxonomy.md](./failure_taxonomy.md) |
| Đối chứng | Cùng `C-002@11` trên shape `fixed`: không xuất hiện event `model_override`; Event `3` là `quote` với `{"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`; ledger ghi `refund_vnd=0`, `refund_count=0`; Event `4` (`reply`) trả về từ chối đúng chính sách (`status=denied`). |
| Regression test | `test_c002_seed11_fails_on_seeded_regression_and_passes_on_fixed` trong [test_lab9_trace_case.py](../src/tests/test_lab9_trace_case.py) — chạy trực tiếp `trace_case.investigate` và xác nhận `DbFactKept` cùng `RefundAmountCorrect` đều fail trên `seeded_regression C-002@11` và pass trên `fixed C-002@11`. |
| Chưa chắc chắn | `seeded_regression` sử dụng MockLLM và bật cứng công tắc `ticket_trust` tại `seed=11` để tái hiện lỗi; trace đơn lẻ này không đo được tần suất các mô hình LLM thật bị đánh lừa khi câu chữ trong ticket thay đổi cấu trúc. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
