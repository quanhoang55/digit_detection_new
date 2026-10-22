import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from roll_qr_scale import test_ui
from roll_qr_scale.storage import MeasurementStore
from roll_qr_scale.windows_app import build_local_argv
from backend.cv.types import Box, Digit


def test_both_shipped_models_match_second_training_manifest():
    info = json.loads(Path('model/MODEL-INFO.json').read_text())
    assert info['source_commit'] == 'dce040dc25c790371ca98e5a6c6ad6f79ec4ad4b'
    for name, size, digest in [('best.pt', 'bytes', 'sha256'), ('crop.pt', 'crop_bytes', 'crop_sha256')]:
        model = Path('backend/model') / name
        assert model.stat().st_size == info[size]
        assert hashlib.sha256(model.read_bytes()).hexdigest() == info[digest]
    assert Path('model/best.pt').read_bytes() == Path(info['source_digit_path']).read_bytes()


@pytest.mark.parametrize('last_confidence,expected', [(0.1, None), (0.9, 63.08)])
def test_6308_is_never_truncated_to_630(tmp_path, last_confidence, expected):
    digits = [Digit(value, last_confidence if index == 3 else 0.9,
                    Box(10 + index * 25, 20, 30 if index == 3 else 20, 40), int(value) + 2)
              for index, value in enumerate('6308')]
    run = SimpleNamespace(digits=digits, display=None, crop_scale=1,
                          preprocessing='test', inference_count=1, model_version='model_2')
    detector = SimpleNamespace(detect_with_details=lambda _: run, roi_method='crop.pt-weight-display')
    store = MeasurementStore(tmp_path / 'measurements.db', tmp_path / 'captures')
    service = test_ui.StationUIService(store, None, None, None, weight_engine='local-yolo',
        digit_detector=detector, digit_inference_confidence=0.35)
    try:
        frame = np.zeros((120, 180, 3), dtype=np.uint8)
        result = service._analyze_local_frame(frame, 'kg', '', '', None, None)
        assert result['weight'] == expected
        assert result['weight'] != 6.30
        assert '6308' in result['weight_raw']
        assert not result['gemini_used']
        assert result['requires_human_review'] == (expected is None)
    finally:
        service.close()
        store.close()


def test_local_release_ignores_old_model_paths_and_tuning_without_editing_config(tmp_path, monkeypatch):
    monkeypatch.setenv('ROLL_SCALE_CROP_DIGIT_MODEL', 'C:/missing-old-crop.pt')
    monkeypatch.setenv('ROLL_SCALE_DIGIT_MODEL', 'C:/missing-old-digits.pt')
    monkeypatch.setenv('ROLL_SCALE_DIGIT_INFERENCE_CONFIDENCE', '0.99')
    monkeypatch.setenv('ROLL_SCALE_DIGIT_IMAGE_SIZE', '640')
    monkeypatch.setenv('ROLL_SCALE_DECIMAL_PLACES', '3')
    assets = tmp_path / 'assets'
    (assets / 'model').mkdir(parents=True)
    for name in ('best.pt', 'crop.pt'):
        (assets / 'model' / name).write_bytes(b'fixture')
    args = test_ui.build_parser().parse_args(build_local_argv(tmp_path / 'TramCanQR', assets))
    assert args.digit_model == str(assets / 'model/best.pt')
    assert args.crop_digit_model == str(assets / 'model/crop.pt')
    assert args.digit_image_size == 736
    assert args.digit_inference_confidence == 0.35
    assert args.decimal_places == 2
    assert args.weight_engine == 'local-yolo'
