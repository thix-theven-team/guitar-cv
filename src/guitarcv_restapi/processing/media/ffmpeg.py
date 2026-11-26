from pathlib import Path
import subprocess


class FFmpegProcessor:
    def __init__(
        self,
        timeout_seconds: float,
        executable: str = "ffmpeg",
        video_codec: str = "libx264",
        fps: int = 15,
        max_dimension: int = 1280,
        strip_audio: bool = True,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not video_codec.strip():
            raise ValueError("video_codec must not be empty")
        if fps <= 0:
            raise ValueError("fps must be positive")
        if max_dimension <= 0:
            raise ValueError("max_dimension must be positive")

        self.timeout_seconds = timeout_seconds
        self.executable = executable
        self.video_codec = video_codec
        self.fps = fps
        self.max_dimension = max_dimension
        self.strip_audio = strip_audio

    def normalize_video(
        self,
        input_path: Path,
        output_path: Path,
        target_format: str = "mp4",
    ) -> Path:
        if not input_path.exists():
            raise FileNotFoundError(f"Input video not found: {input_path}")

        container = target_format.lstrip(".")
        if not container:
            raise ValueError("target_format must not be empty")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            self.executable,
            "-y",
            "-i",
            str(input_path),
            "-c:v",
            self.video_codec,
            "-pix_fmt",
            "yuv420p",
            "-vf",
            (
                f"fps={self.fps},"
                f"scale=min({self.max_dimension},iw):min({self.max_dimension},ih)"
                ":force_original_aspect_ratio=decrease,"
                "scale=trunc(iw/2)*2:trunc(ih/2)*2"
            ),
            "-r",
            str(self.fps),
        ]

        if container == "mp4":
            command.extend(["-movflags", "+faststart"])

        if self.strip_audio:
            command.append("-an")
        else:
            command.extend(["-c:a", "aac"])

        command.extend(["-map_metadata", "-1", "-f", container, str(output_path)])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )

        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.strip() or "unknown ffmpeg error"
            raise RuntimeError(f"FFmpeg normalization failed: {stderr}")

        return output_path
