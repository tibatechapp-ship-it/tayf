"""VideoComposer - assembles keyframes into a real MP4 using ffmpeg.

Pipeline per scene: cover-scale -> Ken Burns (zoompan) -> x264 segment.
Segments are joined with xfade transitions (fade/wipe/slide cycle). The
legacy graph can burn a small "Al-Manazir" watermark; new jobs keep stored
chunks neutral and apply the brand once on the final video via
``apply_watermark``. Everything here is REAL video assembly - no simulation.

ffmpeg resolution order: system binary -> imageio-ffmpeg bundled binary.
On Termux: `pkg install ffmpeg` provides both ffmpeg and ffprobe.
"""

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.branding import WATERMARK_TEXT

ASPECT_DIMS: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (960, 960),
}
FPS = 30
TRANSITIONS = ["fade", "wipeleft", "slideup", "circleopen"]
TRANSITION_SECONDS = 0.5

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/system/fonts/Roboto-Regular.ttf",  # Termux/Android
]


class ComposerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComposeResult:
    video_bytes: bytes
    thumbnail_bytes: bytes | None
    duration_seconds: float
    width: int
    height: int


def _resolve_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def _find_font() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-400:]
        raise ComposerError(f"ffmpeg failed (exit {proc.returncode}): {tail}")
    return proc


def _probe_duration(ffprobe: str | None, path: Path) -> float | None:
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(proc.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def extract_thumbnail(video_bytes: bytes) -> bytes | None:
    """Grab a real JPEG frame from a vendor video. Best-effort, no fabrication."""
    ffmpeg = _resolve_binary("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory(prefix="vf_thumb_") as tmp:
        work = Path(tmp)
        video_path = work / "input.mp4"
        video_path.write_bytes(video_bytes)
        thumb = work / "thumb.jpg"
        try:
            _run([
                ffmpeg, "-y", "-ss", "0.1", "-i", str(video_path),
                "-frames:v", "1", "-q:v", "4", str(thumb),
            ])
        except ComposerError:
            return None
        if not thumb.is_file() or thumb.stat().st_size == 0:
            return None
        return thumb.read_bytes()


def compose_video(
    frames: list[tuple[bytes, float]], aspect: str, *, watermark: bool = True
) -> ComposeResult:
    """frames: list of (image_bytes, per-scene duration seconds), in order.

    ``watermark`` is kept for legacy/no-chunk jobs. Batch 2 callers pass False
    for stored chunks and brand the final video exactly once instead.
    """
    if not frames:
        raise ComposerError("no frames to compose")
    width, height = ASPECT_DIMS.get(aspect, ASPECT_DIMS["16:9"])
    ffmpeg = _resolve_binary("ffmpeg")
    if not ffmpeg:
        raise ComposerError("ffmpeg not found (system or imageio-ffmpeg)")
    ffprobe = _resolve_binary("ffprobe")
    font = _find_font()

    with tempfile.TemporaryDirectory(prefix="vf_compose_") as tmp:
        work = Path(tmp)
        segment_paths: list[Path] = []

        for i, (image_bytes, duration) in enumerate(frames):
            image_path = work / f"scene_{i:03d}.png"
            image_path.write_bytes(image_bytes)
            segment = work / f"seg_{i:03d}.mp4"
            total_frames = max(int(round(duration * FPS)), FPS)  # >= 1s of motion
            vf = (
                f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
                f"crop={width * 2}:{height * 2},"
                f"zoompan=z='min(zoom+0.0012,1.25)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={FPS},"
                f"format=yuv420p"
            )
            _run([
                ffmpeg, "-y", "-loop", "1", "-i", str(image_path),
                "-filter_complex", vf,
                "-t", f"{duration:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                str(segment),
            ])
            segment_paths.append(segment)

        final = work / "final.mp4"
        fade = TRANSITION_SECONDS

        if len(segment_paths) == 1:
            shutil.copyfile(segment_paths[0], final)
            graph = None
        else:
            inputs: list[str] = []
            for seg in segment_paths:
                inputs += ["-i", str(seg)]
            chain: list[str] = []
            offset = 0.0
            running = _probe_duration(ffprobe, segment_paths[0]) or frames[0][1]
            prev_label = "0:v"
            for k in range(1, len(segment_paths)):
                offset = running - fade
                if offset <= 0:
                    offset = 0.05
                out_label = f"v{k}"
                transition = TRANSITIONS[(k - 1) % len(TRANSITIONS)]
                chain.append(
                    f"[{prev_label}][{k}:v]xfade=transition={transition}:"
                    f"duration={fade}:offset={offset:.3f}[{out_label}]"
                )
                prev_label = out_label
                seg_dur = _probe_duration(ffprobe, segment_paths[k]) or frames[k][1]
                running = offset + fade + (seg_dur - fade)
            if font and watermark:
                text = WATERMARK_TEXT
                chain.append(
                    f"[{prev_label}]drawtext=fontfile={font}:text='{text}':"
                    f"fontsize={max(height // 36, 20)}:fontcolor=white@0.55:"
                    f"x=w-tw-24:y=24,format=yuv420p[vout]"
                )
                last_label = "vout"
            else:
                last_label = prev_label
            graph = ";".join(chain)
            cmd = [ffmpeg, "-y", *inputs, "-filter_complex", graph,
                   "-map", f"[{last_label}]", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "20", str(final)]
            _run(cmd)

        if not final.is_file() or final.stat().st_size == 0:
            raise ComposerError("composer produced an empty file")

        video_bytes = final.read_bytes()
        measured = _probe_duration(ffprobe, final)
        if measured is None:
            measured = sum(d for _, d in frames) - (len(frames) - 1) * fade

        thumbnail_bytes: bytes | None = None
        try:
            thumb = work / "thumb.jpg"
            _run([ffmpeg, "-y", "-i", str(final), "-ss", "0.1",
                  "-frames:v", "1", "-q:v", "4", str(thumb)])
            if thumb.is_file() and thumb.stat().st_size > 0:
                thumbnail_bytes = thumb.read_bytes()
        except ComposerError:
            thumbnail_bytes = None

        # silence lint about regex import usage stability
        _ = re.compile("")  # noqa: F841

        return ComposeResult(
            video_bytes=video_bytes,
            thumbnail_bytes=thumbnail_bytes,
            duration_seconds=round(float(measured), 2),
            width=width,
            height=height,
        )


def apply_watermark(video_bytes: bytes, extension: str) -> bytes:
    """Burn the Al-Manazir mark on final video bytes.

    This is intentionally the LAST video pass: stored chunks stay provider
    bytes (or clean keyframes), so resume never double-brands a video. Free
    videos fail closed when ffmpeg or a usable font is unavailable.
    """
    if not video_bytes:
        raise ComposerError("empty video cannot be branded")
    ffmpeg = _resolve_binary("ffmpeg")
    if not ffmpeg:
        raise ComposerError("ffmpeg not found (system or imageio-ffmpeg)")
    font = _find_font()
    if not font:
        raise ComposerError("branding font unavailable")

    with tempfile.TemporaryDirectory(prefix="vf_brand_") as tmp:
        work = Path(tmp)
        source = work / f"source.{_safe_extension(extension)}"
        source.write_bytes(video_bytes)
        final = work / "branded.mp4"
        drawtext = (
            f"drawtext=fontfile={font}:text='{WATERMARK_TEXT}':"
            "fontsize=28:fontcolor=white@0.55:"
            "x=w-tw-24:y=24,format=yuv420p"
        )
        _run([
            ffmpeg, "-y", "-i", str(source), "-vf", drawtext,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-movflags", "+faststart", str(final),
        ])
        if not final.is_file() or final.stat().st_size == 0:
            raise ComposerError("branding produced an empty file")
        return final.read_bytes()


def _safe_extension(extension: str) -> str:
    """Only a short alphanumeric container suffix reaches the filesystem."""
    cleaned = "".join(ch for ch in str(extension).lower() if ch.isalnum())
    return cleaned[:8] or "mp4"


def concat_videos(parts: list[tuple[bytes, str, float]], aspect: str) -> ComposeResult:
    """Join already-rendered chunks with ffmpeg's concat demuxer.

    ``parts`` holds ``(video_bytes, container_extension, duration_seconds)`` in
    playback order. Unlike the single-shot xfade graph, this keeps memory and
    filter complexity bounded for long videos: each chunk was rendered on its
    own and the final join is a stream copy whenever chunk parameters match.
    """
    if not parts:
        raise ComposerError("no chunks to concatenate")
    ffmpeg = _resolve_binary("ffmpeg")
    if not ffmpeg:
        raise ComposerError("ffmpeg not found (system or imageio-ffmpeg)")
    ffprobe = _resolve_binary("ffprobe")
    width, height = ASPECT_DIMS.get(aspect, ASPECT_DIMS["16:9"])

    with tempfile.TemporaryDirectory(prefix="vf_concat_") as tmp:
        work = Path(tmp)
        paths: list[Path] = []
        for index, (data, extension, _duration) in enumerate(parts):
            path = work / f"chunk_{index:03d}.{_safe_extension(extension)}"
            path.write_bytes(data)
            paths.append(path)

        listing = work / "chunks.txt"
        listing.write_text(
            "".join(f"file '{path}'\n" for path in paths), encoding="utf-8"
        )
        final = work / f"final.{_safe_extension(parts[0][1])}"
        base = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
        try:
            _run([*base, "-c", "copy", str(final)])
        except ComposerError:
            # Chunks with slightly different encoder settings still need one
            # re-encode pass; this is the bounded fallback, not the normal path.
            _run([
                *base, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "copy", str(final),
            ])

        if not final.is_file() or final.stat().st_size == 0:
            raise ComposerError("concat produced an empty file")
        measured = _probe_duration(ffprobe, final)
        if measured is None:
            measured = sum(duration for _, _, duration in parts)

        thumbnail_bytes: bytes | None = None
        try:
            thumb = work / "thumb.jpg"
            _run([
                ffmpeg, "-y", "-i", str(final), "-ss", "0.1",
                "-frames:v", "1", "-q:v", "4", str(thumb),
            ])
            if thumb.is_file() and thumb.stat().st_size > 0:
                thumbnail_bytes = thumb.read_bytes()
        except ComposerError:
            thumbnail_bytes = None

        return ComposeResult(
            video_bytes=final.read_bytes(),
            thumbnail_bytes=thumbnail_bytes,
            duration_seconds=round(float(measured), 2),
            width=width,
            height=height,
        )
