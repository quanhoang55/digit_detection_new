# Hai bản Trạm Cân QR dùng chung dữ liệu

Bản local `0.2.0-rc81` được phát hành tại `quanhoang55/digit_detection_new`.
Bản Gemini `0.2.0-rc80` tiếp tục ở `huybitvvt/tram-can-qr-render-pilot`.

| Thành phần | Gemini | Local |
|---|---|---|
| Nhận diện cân | Gemini API | CPU, `best.pt` + `crop.pt` train lần hai |
| Chương trình | `Programs\TramCanQR\TramCanQR.exe` | `Programs\TramCanQRLocal\TramCanQRLocal.exe` |
| Kênh cập nhật | repo Gemini | repo local |
| DB, ảnh, bản nháp, cấu hình | `%LOCALAPPDATA%\TramCanQR` | cùng thư mục bên trái |
| Giao diện | `http://127.0.0.1:8080` | cùng địa chỉ, mở từng bản một |

Hai bản trên cùng máy, cùng tài khoản Windows đọc trực tiếp cùng SQLite;
không có bước chép DB hay nhập lại dữ liệu. DB và các module lưu trữ, phiên
cân, đồng bộ, kho giữ tương thích rc80. Ảnh không đổi đường dẫn; config,
mã trạm, key Gemini và cấu hình cloud/kho không bị sửa.

## Cài một lần

1. Lưu xong lượt cân đang làm ở Gemini.
2. Cài [TramCanQRLocal-Setup.exe](https://github.com/quanhoang55/digit_detection_new/releases/latest/download/TramCanQRLocal-Setup.exe).
3. Giữ tùy chọn tạo biểu tượng Desktop. Bộ cài tạo chương trình riêng, không gỡ hoặc thay EXE Gemini.
4. Bấm **Chuyển sang Trạm Cân Local**. Nếu Gemini còn chạy, xác nhận đã lưu
   lượt cân để đóng Gemini và mở local. Nếu chưa lưu, chọn **No** và lưu trước.
5. Khi cần dự phòng, bấm **Chuyển sang Gemini (dự phòng)**. Local được đóng
   sau khi xác nhận; rc80 mở và đọc cùng dữ liệu vừa lưu ở local.
6. Nhấn `Ctrl+F5` sau khi chuyển nếu tab còn giữ giao diện của bản trước.

Hai shortcut chuyển bản không sửa config và chỉ đóng chương trình ở đúng
thư mục cài của tài khoản Windows hiện tại. Không chạy đồng thời hai bản
giữ camera/cổng. Bản Gemini phải còn được cài ở vị trí mặc định; nếu đã
gỡ, [cài lại rc80](https://github.com/huybitvvt/tram-can-qr-render-pilot/releases/tag/v0.2.0-rc80).

**Cập nhật Trạm Cân Local** chỉ cập nhật local, kiểm tra SHA-256 trước khi
đóng chương trình. **Cập nhật Trạm Cân QR** cũ tiếp tục cập nhật Gemini.
Cài lần đầu bản local bằng EXE ở trên; updater Gemini không chuyển kênh.

Trước lần chạy rc81 đầu tiên, sao lưu DB hiện tại (gồm dữ liệu trong WAL)
và config vào `backups\before-local2-rc81-*`, marker `backups\local2-rc81.json`.
Không phục hồi DB cũ ghi đè lượt cân phát sinh sau đó.

## Vận hành

Giữ quy trình chọn ca/máy/LSX, hai cặp lõi–SP, lưu từng cặp, danh sách,
đồng bộ theo bộ lọc và đẩy kho. Chọn đúng camera USB trong bản local;
lựa chọn camera Gemini được giữ riêng, không bị chỉ số USB của local ghi đè.

Model kèm bộ cài, chạy CPU, không cần Python/CUDA/Gemini key hoặc Internet
để đọc cân. Đồng bộ cloud/kho vẫn cần mạng và cấu hình hiện có.

Model chữ số dùng `backend/model/best.pt` từ commit
`dce040dc25c790371ca98e5a6c6ad6f79ec4ad4b`; không đóng gói checkpoint cũ
20,8 MB. `model/best.pt` cũng được cập nhật cùng checkpoint mới. Hash và xuất xứ hai model có trong
`model/MODEL-INFO.json`.

Gross được ưu tiên trên các hàng thẳng cột. Không bỏ chữ số cuối yếu để
tạo ra số cân ngắn hơn; các kết quả mâu thuẫn hoặc thiếu tin cậy bị từ chối.
Kiểm tra số thực trên cân trước khi lưu. Chất lượng nhận diện ở xưởng
chưa được nghiệm thu; ảnh mờ có thể không đọc được dù ảnh khác đọc đúng.

Dùng chung dữ liệu áp dụng cho hai bản trên cùng máy và tài khoản Windows.
Các máy khác nhau tiếp tục đồng bộ qua cloud theo quy trình hiện tại.

## Kiểm tra nhà phát triển

```powershell
.\.venv\Scripts\python.exe -m pytest
node --test tests/*.test.cjs
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\build_windows.ps1
.\.venv\Scripts\python.exe tools\verify_windows_local.py
.\.venv\Scripts\python.exe tools\smoke_windows_updater.py
.\.venv\Scripts\python.exe tools\smoke_variant_switch.py
.\.venv\Scripts\python.exe tools\smoke_frozen_local_upgrade.py
```

Một số test OCR/Colab cũ dùng fixture không được repo gốc theo dõi;
cần có các fixture kiểm thử đó để chạy toàn bộ suite. Chúng không đi vào bộ cài.
