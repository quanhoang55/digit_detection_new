# Kiểm chứng Local rc81 — 23/10/2026

- Python: **573 passed**, một warning thư viện; có fixture OCR/Colab cũ tại máy kiểm thử, không đưa vào bộ cài.
- Node: **149 passed**; gồm giữ riêng lựa chọn camera local/Gemini.
- Script chuyển bản: **8/8** tình huống hai chiều, hủy, thiếu bản đích,
  bản kia không chạy. Chỉ dừng đúng đường dẫn ứng dụng, không mở song song,
  không sửa DB/config/ảnh. Các thao tác process/dialog trong phép thử này được mô phỏng.
- Updater PowerShell: đúng repo local, chọn rc81, SHA-256 đúng thì dừng/cài/mở;
  checksum sai bị chặn trước khi dừng. Process/installer/network được mô phỏng;
  file bảo vệ không đổi. Không gọi updater Gemini.
- EXE local thật: mở config Gemini cũ và model path cũ không còn tồn tại;
  nhận đúng trạm 04, giữ cloud/kho và chế độ đồng bộ, dùng model CPU trong gói.
- Giữ hai phiếu cũ pending/failed, ảnh lõi/SP, ảnh staging và một bản nháp
  thật trong SQLite. Snapshot DB gồm WAL và config kiểm tra được.
- API nhận diện của EXE local đọc ảnh chuẩn **13,04 kg + QR** mà không dùng Gemini.
- EXE local lưu thêm phiếu; EXE Gemini rc80 cũ mở cùng DB, thấy phiếu local,
  lưu thêm phiếu; mở lại EXE local thấy cả phiếu Gemini. Config, ảnh cũ và bản nháp không đổi.
  Mỗi bước chỉ có một EXE đang chạy. Các EXE dùng thư mục/port thử riêng;
  không cài đè hay chạy trên dữ liệu vận hành.
- Mã trong EXE (entry/backend/CV) và HTML đối chiếu khớp source. Hai checkpoint
  trong gói khớp manifest SHA-256. Không chứa `.env`, `config.env`, DB vận hành
  hoặc staging của khách. Hai installer generic/có version có cùng bytes/hash.
- Repo Gemini và Latest `v0.2.0-rc80` giữ nguyên.

## Giới hạn nhận diện đã đo

| Ảnh chuẩn | Kết quả model mới |
|---|---|
| 13,04 kg | đúng 13,04; confidence nhỏ nhất khoảng 0,531 |
| 7,02 kg toàn cảnh | chưa đọc được, từ chối kết quả |
| 7,84 kg ảnh mờ trạm 01 | chưa đủ tin cậy, từ chối kết quả |

Đây không phải nghiệm thu camera USB tại xưởng hoặc kiểm tra key/quota Gemini thật.
Không kết luận độ chính xác tổng thể từ một ảnh đạt. Dùng shortcut chuyển sang
Gemini khi local không đọc được và đối chiếu số thực trên cân trước khi lưu.

Installer (363.809.195 byte):

```text
eac2d12d5d26705fea4eecad2146c0f1139252e6f18ea2b48c06946509003a88  TramCanQRLocal-Setup-0.2.0-rc81.exe
eac2d12d5d26705fea4eecad2146c0f1139252e6f18ea2b48c06946509003a88  TramCanQRLocal-Setup.exe
```
