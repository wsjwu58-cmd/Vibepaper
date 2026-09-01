from __future__ import annotations

import wave
from pathlib import Path

import pytest

from generation.providers.providers import GenerationRequest, WindowsSapiTtsProvider


def request(tmp_path: Path, **params: object) -> GenerationRequest:
    return GenerationRequest(
        task_id=101,
        model_type="audio",
        model_name="local-sapi-tts",
        params={"text": "你好，VibePaper", **params},
        output_dir=str(tmp_path),
    )


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows SAPI only")
def test_sapi_generates_non_empty_wave(tmp_path: Path) -> None:
    job = WindowsSapiTtsProvider().generate(request(tmp_path, voice="female", speed=0.95, tone="calm"))

    assert job.status == "succeeded", job.error_message
    output = job.result["outputs"][0]
    with wave.open(output["file_path"], "rb") as wav:
        assert wav.getnframes() > 0
        assert wav.getframerate() >= 16000
    assert output["meta"]["textHash"]
    assert output["meta"]["toneApplied"] is True


@pytest.mark.parametrize("speed", [0.5, 0.95, 1.0, 1.5, 2.0])
def test_sapi_speed_boundaries_are_mapped_deterministically(tmp_path: Path, speed: float) -> None:
    provider = WindowsSapiTtsProvider()
    first = provider.normalized_params(request(tmp_path, speed=speed).params)
    second = provider.normalized_params(request(tmp_path, speed=speed).params)

    assert first == second
    assert -10 <= first["rate"] <= 10


def test_sapi_empty_text_is_rejected(tmp_path: Path) -> None:
    job = WindowsSapiTtsProvider().generate(request(tmp_path, text=""))

    assert job.status == "failed"
    assert job.error_code == "INVALID_INPUT"


def test_sapi_unknown_tone_is_visible_in_metadata(tmp_path: Path) -> None:
    params = WindowsSapiTtsProvider().normalized_params(request(tmp_path, tone="mystery").params)

    assert params["toneApplied"] is False


def test_sapi_text_hash_is_stable(tmp_path: Path) -> None:
    provider = WindowsSapiTtsProvider()
    first = provider.normalized_params(request(tmp_path).params)
    second = provider.normalized_params(request(tmp_path).params)

    assert first["textHash"] == second["textHash"]
