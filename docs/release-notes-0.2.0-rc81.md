# Trạm Cân QR Local — v0.2.0-rc81

Bản local độc lập dùng cặp model train lần hai của đồng nghiệp, chạy trên CPU.
Giữ rc80 Gemini làm bản dự phòng, cùng đọc DB/ảnh/config tại
`%LOCALAPPDATA%\TramCanQR`; không cần chép hay chuyển đổi dữ liệu.

- Cài vào `Programs\TramCanQRLocal`, EXE/AppId/shortcut và updater riêng.
- Hai shortcut chuyển sang Local/Gemini, nhắc lưu lượt cân trước khi đóng bản đang chạy.
- Updater local lấy release từ repo này và kiểm tra SHA-256; updater Gemini vẫn dùng repo Gemini.
- Đóng gói đúng `backend/model/best.pt` (5.392.325 byte) và `crop.pt` (5.448.261 byte).
- Giữ nguyên bộ lưu trữ, phiên cân, đồng bộ cloud và kho tương thích rc80.
- Sao lưu SQLite hiện tại kể cả WAL và config trước lần mở đầu; giữ nguyên ảnh/bản nháp.
- Ưu tiên Gross trên hàng thẳng cột; từ chối đọc mâu thuẫn, giữ chữ số cuối yếu để từ chối cả kết quả.
- Lựa chọn camera local tách khỏi lựa chọn camera của Gemini.

Cài `TramCanQRLocal-Setup.exe` một lần, sau đó dùng **Cập nhật Trạm Cân Local**.
Chỉ mở một bản trên cùng máy tại `http://127.0.0.1:8080`.
Khi cần dự phòng, dùng **Chuyển sang Gemini (dự phòng)**. Gemini cần mạng/key/quota còn hiệu lực.

Nhận diện tại xưởng chưa nghiệm thu. Một số ảnh mờ vẫn không đọc được;
kiểm tra số cân thực trước khi lưu. [Hướng dẫn chi tiết](https://github.com/quanhoang55/digit_detection_new/blob/main/docs/DUAL-VARIANT-LOCAL.md).

Đã đạt 573 test Python, 149 test giao diện; EXE local và EXE rc80 thật đã lưu/đọc
chéo cùng DB, giữ config, ảnh và bản nháp. Mẫu 13,04 kg đọc đúng; hai ảnh tham
chiếu 7,02/7,84 kg vẫn bị từ chối vì chưa đọc được/thiếu tin cậy.
[Kết quả kiểm chứng và giới hạn](https://github.com/quanhoang55/digit_detection_new/blob/main/docs/verification-0.2.0-rc81.md).
