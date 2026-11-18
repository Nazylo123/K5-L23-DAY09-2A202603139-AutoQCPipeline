# Báo cáo Day 09 — Nguyễn Văn Hoa, 2A202603139

## 1. Kết luận trước
**Hold (mã thoát 10).** Pipeline nhận 202/224 ảnh và xuất nhãn cho 202 ảnh trong `clean_v1`. Sau lượt duyệt mô phỏng, không còn lỗi bắt buộc nhưng 38/202 ảnh (18,81%) vẫn còn cảnh báo chưa duyệt, cao hơn ngưỡng 10%. Bản xuất chỉ dùng để thử nghiệm.

## 2. Lỗi và phân việc
Số liệu lấy từ `02_error_list_v1.csv`. Một dòng nhãn có thể có nhiều mã lỗi.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT`, `DUP_IMAGE_NEAR`, `LEAK_TEST`, `BAD_SIZE`, `CORRUPT_IMAGE` | Lần lượt 8, 4, 5, 3, 2 ảnh | Máy | Loại theo quy tắc ở đầu vào. |
| `BOX_OUT_OF_IMAGE`, `DUP_BOX`, `BAD_CLASS_ID`, `BOX_ZERO`, `BAD_FORMAT` | Lần lượt 8, 7, 6, 4, 3 dòng báo lỗi | Máy | Cắt box tràn hoặc bỏ dòng không hợp lệ. |
| `BAD_CLASS_NAME` | 2 lỗi trong `data.yaml` | Máy | Ghi lại tên lớp theo cấu hình. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người | Không tạo file nhãn rỗng thay cho nhãn chưa gán. |
| `POSSIBLE_MISSING`, `POSSIBLE_FALSE_POS`, `POSSIBLE_LOOSE_BOX`, `POSSIBLE_WRONG_CLASS` | Lần lượt 53, 29, 28, 18 cảnh báo | Người | Dự đoán của model chỉ là gợi ý, không dùng để tự sửa nhãn. |
| `EMPTY_LABEL`, `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` | 12 ảnh, 6 box, 3 box, 4 cảnh báo cấp tập | Người | Xem ảnh hoặc đối chiếu thống kê trước khi quyết định. |

`img_0020` đứng đầu hàng (11.524 điểm) vì vừa có dòng bị xóa tự động, vừa có cảnh báo thiếu box và nhầm lớp. Sáu ảnh chưa có nhãn đứng tiếp theo (10 điểm/ảnh). Lượt duyệt mô phỏng xử lý 80/125 ảnh trong hàng; các ảnh này chứa 94/123 cảnh báo ngữ nghĩa sau sửa tự động, trên 74/103 ảnh có cảnh báo loại này (`04_error_list_v2.csv`, `06_review_log.csv`). Đây là số cảnh báo được đưa ra xem, không phải số lỗi thật đã xác nhận.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 14 | Gần trùng: 1.00 / 0.50 → 1.00 / 0.67. Trùng byte: 1.00 / 1.00 ở cả hai ngưỡng. | Bắt 4/6 thay vì 3/6 ca gần trùng trên `calib`. Chọn 14 thay vì 16 để giảm nguy cơ tự động loại nhầm ảnh. |
| `second_opinion.conf` | 0.25 | 0.60 | Thiếu box: 0.50 / 1.00 → 0.57 / 1.00. Nhầm lớp: 0.56 / 0.83 → 0.62 / 0.83. Box lỏng: 0.29 / 0.40 → 0.20 / 0.20. | Bớt cảnh báo sai về thiếu box và nhầm lớp, nhưng bắt ít hơn một ca box lỏng. |

Precision 1.00 cho ảnh gần trùng chỉ đo trên tập `calib` có sáu ca chèn. Trên `raw`, số ảnh bị loại ở bước nhận dữ liệu tăng từ 19 lên 31; trong 12 ảnh bị loại thêm, 5 ảnh được báo gần trùng trong `raw` và 7 ảnh bị báo trùng kho tham chiếu (`LEAK_TEST`). Khi xem 5 cặp gần trùng mới trong `raw`, cặp 01 (`img_0008`–`img_0011`) và cặp 03 (`img_0113`–`img_0177`) có vẻ là hai ảnh khác nhau; cặp 02, 04 và 05 trông như cùng một ảnh. Hai cặp nghi báo nhầm đều có khoảng cách pHash 16. Ở ngưỡng 14, số ảnh bị loại giảm từ 31 xuống 22. Hai ảnh từng bị báo gần trùng ở cặp 01 và 03 (`img_0011`, `img_0177`) được giữ lại; `img_0113` vẫn bị loại vì kích thước. Cặp 04 và 05 vẫn được phát hiện, còn cặp 02 không bị đánh dấu nữa. Đây là phần đánh đổi khi ưu tiên giữ ảnh khác nhau.

## 4. Cửa chặn và điều pipeline không bắt được

Chạy riêng với `--budget 0`: còn 6 lỗi `MISSING_LABEL_FILE`, kết quả **Rework** (mã thoát 20) và không xuất dataset. Kết quả thử nằm ở `work/report_budget0/reports/08_summary.json`.

Đối chiếu quan sát trên ảnh gốc với `02_error_list_v1.csv`:

| Ảnh | Quan sát |
|---|---|
| `img_0001` | Thiếu box cho một người. Pipeline có cảnh báo `POSSIBLE_MISSING` ở ảnh này. |
| `img_0060` | Box `truck` không bao hết chiếc xe tải, nhưng không có cảnh báo cho ảnh này. |
| `img_0062` | Bóng người dưới nước bị gán `person`. Pipeline báo box lỏng, không báo box thừa. |
| `img_0063` | Có một box `person` thừa, nhưng không có cảnh báo cho ảnh này. |

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy phần train tùy chọn; báo cáo này chỉ làm phần lõi.

## 6. Quyết định và ghi chú AI

Giữ **Hold**. Cần duyệt thêm các ảnh còn cảnh báo thay vì tăng ngưỡng để giảm số cờ. Với 202 ảnh, phải còn tối đa 20 ảnh chưa xử lý cảnh báo và không còn lỗi bắt buộc thì mới đạt Release.

- Dùng AI hỗ trợ triển khai bốn module CP2 và tổng hợp báo cáo.
- Kiểm bằng `pytest` (79 test đạt) và bộ `calib` (bắt đúng 14/14 lỗi định dạng dòng nhãn đã chèn).
- Đề xuất ban đầu của AI là pHash 16. Sau khi xem cặp ảnh thật, hạ xuống 14 vì có hai cặp nghi bị báo nhầm.
