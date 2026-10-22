"""Verify source/model/update assets in the primary in-place Windows package."""
import hashlib
import json
import marshal
import re
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader
from verify_ai_auto import normalized


def main():
    root = Path(__file__).resolve().parents[1]
    version = re.search(r'^APP_VERSION = "([^"]+)"', (root / "backend/src/roll_qr_scale/windows_app.py").read_text(), re.M)[1]
    package = root / "dist/TramCanQRLocal"
    executable = CArchiveReader(str(package / "TramCanQRLocal.exe"))
    archive = executable.open_embedded_archive("PYZ.pyz")
    modules = {
        **{f"roll_qr_scale.{name}": root / f"backend/src/roll_qr_scale/{name}.py"
           for name in ("test_ui", "crop_digit_detector", "digit_postprocess", "live_camera", "live_capture_cache", "camera_process", "camera_worker", "station_session", "sync", "storage")},
        **{f"backend.cv.{name}": root / f"new_system/Digit_QRCode_Detection/backend/src/backend/cv/{name}.py"
           for name in ("digit_detector", "qr_decoder")},
    }
    for module, source in modules.items():
        assert normalized(archive.extract(module)) == normalized(compile(source.read_bytes(), str(source), "exec", dont_inherit=True)), module
    entry = root / "backend/src/roll_qr_scale/windows_app.py"
    assert normalized(marshal.loads(executable.extract("windows_app"))) == normalized(compile(entry.read_bytes(), str(entry), "exec", dont_inherit=True))
    assets = package / "_internal/assets"
    assert (assets / "frontend/index.html").read_bytes() == (root / "frontend/index.html").read_bytes()
    info = json.loads((root / "model/MODEL-INFO.json").read_text())
    assert hashlib.sha256((assets / "model/best.pt").read_bytes()).hexdigest() == info["sha256"]
    assert hashlib.sha256((assets / "model/crop.pt").read_bytes()).hexdigest() == info["crop_sha256"]
    assert (assets / "model/best.pt").stat().st_size == info["bytes"]
    assert (assets / "model/crop.pt").stat().st_size == info["crop_bytes"]
    for name in ("storage", "station_session", "sync", "warehouse"):
        gemini_source = root.parent / "train_thigiacAI/backend/src/roll_qr_scale" / f"{name}.py"
        if gemini_source.is_file():
            assert gemini_source.read_bytes().replace(b"\r\n", b"\n") == (
                root / f"backend/src/roll_qr_scale/{name}.py").read_bytes().replace(b"\r\n", b"\n"), name
    forbidden = {".env", "config.env", "measurements.db", ".active-bindings.json"}
    assert not [path for path in package.rglob("*") if path.name in forbidden]
    assert (package / "CAP-NHAT-BAN-MOI.cmd").read_bytes() == (root / "packaging/CAP-NHAT-BAN-MOI.cmd").read_bytes()
    assert (package / "CHUYEN-BAN.ps1").read_bytes() == (root / "packaging/CHUYEN-BAN.ps1").read_bytes()
    handoff = root / f"dist/handoff-{version}"
    for line in (handoff / "SHA256SUMS.txt").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((handoff / name).read_bytes()).hexdigest().lower() == expected.lower()
    assert (handoff / "TramCanQRLocal-Setup.exe").read_bytes() == (handoff / f"TramCanQRLocal-Setup-{version}.exe").read_bytes()
    assert (handoff / "CAP-NHAT-BAN-MOI.cmd").read_bytes() == (root / "packaging/CAP-NHAT-BAN-MOI.cmd").read_bytes()
    print(f"PASS {version}: frozen backend/entry/frontend match source; model SHA-256; no private config/DB; updater and installer hashes match")


if __name__ == "__main__":
    main()
