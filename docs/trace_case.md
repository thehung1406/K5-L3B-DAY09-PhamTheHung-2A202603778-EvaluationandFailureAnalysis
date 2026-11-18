# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-8192` |
| Triệu chứng | `TrialPass` fail (`status resolved != denied`), `RefundAmountCorrect` fail (`ledger=20000 != expected=0`), `DbFactKept` fail (`1 override event(s)`). Reply báo *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* trong khi đơn chỉ trễ theo DB ít hơn mức hưởng và nhãn là `denied` (`0đ`). |
| Bước sai đầu tiên | Bước `3`: `model_override` — `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Bước `1` (`handoff`) tạo handoff đúng `principal_scope: owner_order_only` và `allowed_tools` hợp lệ; bước `2` (`investigator`) tra cứu đúng đơn `O-202` từ DB. Từ bước `3`, agent tin số `delay_days: 5` trong ticket của khách để ghi đè dữ liệu DB, kéo theo bước `4` (`quote`) tính sai 20.000đ và bước `6` (`reply`) báo `resolved`. |
| Failure mode | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md` |
| Đối chứng | Trên `fixed C-002@11`, không có event `model_override`: bước `3` (`quote`) dùng đúng `delay_days` của DB nên trả `amount_vnd: 0, reason: no_entitlement`, và bước `4` (`reply`) từ chối đúng (`status=denied`, `refund_vnd=0`). |
| Regression test | Item `E-002` (`C-002`, gắn `FM-03`) trong `data/eval/eval_set_v1.jsonl` + grader `DbFactKept` và `RefundAmountCorrect` (cùng các test đơn vị `test_override_event_breaks_db_fact`, `test_wrong_amount_in_ledger`, `test_reply_matches_ledger_catches_misreport` trong `tests/test_lab9_graders.py`). Đã xác nhận fail trên `seeded_regression` và pass trên `fixed`. |
| Chưa chắc chắn | MockLLM bỏ qua trường hợp ticket diễn đạt số ngày bằng chữ hoặc gián tiếp; cần kiểm tra thêm với LLM thật. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
