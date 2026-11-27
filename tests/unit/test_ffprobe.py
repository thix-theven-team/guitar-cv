import json
from pathlib import Path
import subprocess

import pytest

from guitarcv_restapi.core.exceptions import ApiException
from guitarcv_restapi.processing.media.ffprobe import FFprobeValidator


def make_validator() -> FFprobeValidator:
    return FFprobeValidator(
        timeout_seconds=1.0,
        allowed_mime_types=("video/mp4", "video/webm"),
    )


def test_mime_validation_accepts_parameters_and_normalizes_case() -> None:
    make_validator().validate_mime_type("Video/MP4; charset=binary")


@pytest.mark.parametrize("content_type", [None, "", "image/png", "text/plain"])
def test_mime_validation_rejects_missing_or_unsupported_types(content_type) -> None:
    with pytest.raises(ApiException) as error:
        make_validator().validate_mime_type(content_type)
    assert error.value.status_code == 415


def test_probe_rejects_file_without_video_stream(tmp_path, monkeypatch) -> None:
    video = tmp_path / "not-video.mp4"
    video.write_bytes(b"not empty")
    monkeypatch.setattr(
        "guitarcv_restapi.processing.media.ffprobe.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps({
                "format": {"format_name": "image2", "duration": "1.0"},
                "streams": [{
                    "codec_type": "video",
                    "codec_name": "mjpeg",
                    "disposition": {"attached_pic": 1},
                }],
            }),
            stderr="",
        ),
    )

    with pytest.raises(ApiException) as error:
        make_validator().probe_video(video)
    assert error.value.status_code == 415
    assert error.value.code == "NO_VIDEO_STREAM"


def test_probe_accepts_real_video_stream(tmp_path, monkeypatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    payload = {
        "format": {"format_name": "mov,mp4", "duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "disposition": {"attached_pic": 0},
            }
        ],
    }
    monkeypatch.setattr(
        "guitarcv_restapi.processing.media.ffprobe.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    result = make_validator().probe_video(video)

    assert result.format_name == "mov,mp4"
    assert result.duration_seconds == 12.5
    assert result.video_codec_names == ("h264",)


def test_probe_timeout_maps_to_gateway_timeout(tmp_path, monkeypatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(
        "guitarcv_restapi.processing.media.ffprobe.subprocess.run",
        timeout,
    )

    with pytest.raises(ApiException) as error:
        make_validator().probe_video(video)
    assert error.value.status_code == 504


def test_probe_malformed_ffprobe_json_is_internal_error(
    tmp_path,
    monkeypatch,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        "guitarcv_restapi.processing.media.ffprobe.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="{broken", stderr=""
        ),
    )

    with pytest.raises(ApiException) as error:
        make_validator().probe_video(video)
    assert error.value.status_code == 500


def test_ffprobe_treats_null_disposition_as_non_attached_video(monkeypatch, tmp_path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    payload = {
        "format": {"format_name": "mov,mp4", "duration": "1.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "disposition": None}
        ],
    }
    monkeypatch.setattr(
        "guitarcv_restapi.processing.media.ffprobe.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )

    result = FFprobeValidator(5.0, ("video/mp4",)).probe_video(video_path)

    assert result.video_codec_names == ("h264",)
