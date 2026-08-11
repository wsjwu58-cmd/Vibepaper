"""模型供应商适配（ModelProvider 协议：estimate/submit/poll/cancel/healthcheck）。"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.config import settings

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_MOCK_PREVIEW_MP4 = _ASSETS_DIR / "mock_preview.mp4"


@dataclass
class GenerationRequest:
    task_id: int
    model_type: str
    model_name: str
    params: dict = field(default_factory=dict)
    output_dir: str = ""


@dataclass
class ProviderJob:
    job_id: str
    status: str = "running"
    result: dict = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ModelProvider(ABC):
    """供应商协议。业务代码不依赖供应商私有字段。"""

    name = "base"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> ProviderJob:
        ...

    def healthcheck(self) -> dict:
        return {"ok": True, "provider": self.name}


def _parse_resolution(resolution: str, default: tuple[int, int] = (1024, 1024)) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in resolution.lower().split("x"))
        return max(64, min(w, 4096)), max(64, min(h, 4096))
    except Exception:
        return default


def _resolve_local_media_path(src: str) -> Path | None:
    """把任务输出 / 素材 URL 映射到本地存储路径。"""
    import re
    from urllib.parse import unquote, urlparse, parse_qs

    if not src:
        return None
    p = Path(src)
    if p.exists():
        return p
    # /api/v1/tasks/{id}/outputs/file/{name}
    m = re.search(r"/tasks/(\d+)/outputs/file/([^/?#]+)", src)
    if m:
        candidate = Path(settings.storage_dir) / m.group(1) / unquote(m.group(2))
        if candidate.exists():
            return candidate
    # /api/v1/assets/file?path=objectKey
    if "/assets/file" in src:
        parsed = urlparse(src if "://" in src else f"http://local{src}")
        key = parse_qs(parsed.query).get("path", [None])[0]
        if key:
            candidate = Path(os.environ.get("VIBEPAPER_ASSET_PATH", r"E:\VibePaperProject\data\assets")) / unquote(key).replace("/", os.sep)
            if candidate.exists():
                return candidate
    return None


def _find_source_image(request: GenerationRequest):
    from PIL import Image, ImageDraw

    src = request.params.get("sourcePath") or request.params.get("sourceUrl")
    if isinstance(src, str):
        local = _resolve_local_media_path(src)
        if local is not None:
            return Image.open(local).convert("RGB")
    # 回退：带主体示意的浅色底图（避免三视图变成三块纯黑）
    w, h = _parse_resolution(str(request.params.get("resolution", "1024x1024")))
    img = Image.new("RGB", (w, h), (236, 238, 244))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    draw.ellipse([cx - w // 5, cy - h // 4, cx + w // 5, cy + h // 5], fill=(120, 150, 200), outline=(60, 80, 120), width=3)
    draw.rectangle([cx - w // 8, cy + h // 6, cx + w // 8, cy + h // 3], fill=(90, 110, 150))
    prompt = str(request.params.get("prompt") or "source")[:36]
    draw.text((16, 16), prompt, fill=(40, 40, 50))
    return img


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return []


def build_text_user_content(params: dict) -> str:
    """合并提示词与参考栏素材，供文本生成 Provider 使用。"""
    prompt = str(params.get("prompt") or "").strip()
    ref_texts = _normalize_str_list(params.get("referenceTexts"))
    ref_urls = _normalize_str_list(params.get("referenceUrls"))
    sections: list[str] = []
    if ref_texts:
        sections.append("【参考文本】\n" + "\n---\n".join(ref_texts))
    if ref_urls:
        sections.append("【参考素材】\n" + "\n".join(f"- {url}" for url in ref_urls))
    if prompt:
        sections.append("【提示词】\n" + prompt)
    return "\n\n".join(sections) if sections else "请生成一段文本"


def build_generation_prompt(params: dict) -> str:
    """合并提示词与参考文本，供图/音/视频生成使用（参考栏仅有上游文本时也可提交）。"""
    prompt = str(params.get("prompt") or "").strip()
    ref_texts = _normalize_str_list(params.get("referenceTexts"))
    parts: list[str] = []
    if ref_texts:
        parts.extend(ref_texts)
    if prompt:
        parts.append(prompt)
    return "\n".join(parts)


def first_reference_image(params: dict) -> str | None:
    for key in ("image", "imageUrl", "image_url", "referenceUrl", "sourceUrl", "firstFrameUrl"):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    refs = params.get("referenceImages") or params.get("reference_images") or params.get("referenceUrls") or []
    if isinstance(refs, str) and refs.strip():
        return refs.strip()
    if isinstance(refs, (list, tuple)):
        for item in refs:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


VIDEO_MODEL_ALIASES: dict[str, str] = {
    "seedance-1.0": "doubao-seedance-1-0-pro-250528",
    "wan-2.1": "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-5-pro-251215": "doubao-seedance-1-0-pro-250528",
}


def resolve_video_model(model_name: str | None) -> str:
    raw = (model_name or "").strip()
    if raw in VIDEO_MODEL_ALIASES:
        return VIDEO_MODEL_ALIASES[raw]
    if raw.startswith("doubao-seedance"):
        return raw
    return raw or settings.ark_video_model or "doubao-seedance-1-0-pro-250528"


def parse_ark_http_error(response) -> tuple[str, str]:
    """解析方舟 HTTP 错误体，返回 (error_code, user_message)。"""
    try:
        payload = response.json()
    except Exception:
        return "MODEL_UNAVAILABLE", f"方舟 API 错误 HTTP {response.status_code}"
    err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = str(err.get("code") or "MODEL_UNAVAILABLE")
    message = str(err.get("message") or payload.get("message") or response.text or "")
    if code == "ModelNotOpen":
        return "MODEL_UNAVAILABLE", (
            f"视频模型未开通（{message}）。请前往火山方舟控制台 → 模型广场，开通对应 Seedance 模型后再试。"
        )
    if code in {"InvalidEndpointOrModel.NotFound", "NotFound"}:
        return "MODEL_UNAVAILABLE", (
            f"视频模型不可用（{message}）。请确认模型 ID 正确，且当前账号已开通该模型。"
        )
    if message:
        return code if code else "MODEL_UNAVAILABLE", message[:500]
    return "MODEL_UNAVAILABLE", f"方舟 API 错误 HTTP {response.status_code}"


class MockTextProvider(ModelProvider):
    name = "mock-text"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        content = build_text_user_content(request.params)
        count = int(request.params.get("count", 1))
        results = []
        for i in range(count):
            results.append({
                "text": f"# {request.model_name} 生成结果 {i + 1}\n\n{content}\n\n> VibePaper Mock Provider 输出（用于本地联调）。",
                "meta": {"index": i, "text": f"# {request.model_name} 生成结果 {i + 1}\n\n{content}"},
            })
        return ProviderJob(job_id=f"txt-{request.task_id}", status="succeeded", result={"outputs": results})


class OpenAICompatibleTextProvider(ModelProvider):
    """OpenAI 兼容文本生成（DeepSeek / Qwen / OpenAI）。"""

    name = "openai-text"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        api_key = settings.llm_api_key or os.getenv("VIBEPAPER_LLM_API_KEY", "")
        if not api_key:
            # 本地无 Key 才允许 mock；有 Key 时失败必须暴露，禁止静默假成功
            return MockTextProvider().generate(request)
        try:
            import httpx

            user_content = build_text_user_content(request.params)
            model = request.model_name or settings.llm_model
            base = (settings.llm_base_url or "https://api.deepseek.com/v1").rstrip("/")
            if "deepseek.com" in base and not base.endswith("/v1"):
                base = f"{base}/v1"
            resp = httpx.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是 VibePaper 创作助手，输出可直接用于画布的高质量文本。"},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.7,
                },
                timeout=90,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return ProviderJob(
                job_id=f"oai-{request.task_id}",
                status="succeeded",
                result={"outputs": [{"text": text, "meta": {"text": text, "provider": self.name}}]},
            )
        except Exception as e:
            return ProviderJob(
                job_id=f"oai-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message=f"文本模型调用失败：{e}"[:500],
            )


class MockImageProvider(ModelProvider):
    name = "mock-image"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

        prompt = build_generation_prompt(request.params) or "default"
        operation = str(request.params.get("operation") or "")
        resolution = str(request.params.get("resolution", "1024x1024"))
        count = int(request.params.get("count", 1))
        w, h = _parse_resolution(resolution)
        outputs = []
        for i in range(count):
            if operation in {"裁剪", "扩图", "超分", "三视图", "director"}:
                img = _find_source_image(request)
                if operation == "裁剪":
                    mode = request.params.get("cropMode", "single")
                    cw, ch = img.size
                    if mode == "四宫格":
                        img = img.crop((0, 0, cw // 2, ch // 2))
                    elif mode == "九宫格":
                        img = img.crop((0, 0, cw // 3, ch // 3))
                    else:
                        margin = min(cw, ch) // 8
                        img = img.crop((margin, margin, cw - margin, ch - margin))
                elif operation == "扩图":
                    border = max(32, min(img.size) // 8)
                    img = ImageOps.expand(img, border=border, fill=(24, 24, 32))
                elif operation == "超分":
                    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
                    img = ImageEnhance.Sharpness(img).enhance(1.4)
                elif operation == "三视图":
                    category = str(request.params.get("threeViewCategory") or request.params.get("category") or "人物")
                    canvas = Image.new("RGB", (w, h), (245, 246, 250))
                    gap, pad = 10, 12
                    tile_w = (w - pad * 2 - gap * 2) // 3
                    tile_h = h - pad * 2 - 28
                    labels = ["正视", "侧视", "俯视"]
                    for idx, label in enumerate(labels):
                        # 三视角轻微不同变换，避免三块完全一样
                        tile = img.copy()
                        if idx == 1:
                            tile = ImageOps.mirror(tile)
                        elif idx == 2:
                            tile = tile.rotate(90, expand=True, fillcolor=(245, 246, 250))
                        tile = ImageOps.fit(tile, (tile_w, tile_h), method=Image.Resampling.LANCZOS)
                        draw = ImageDraw.Draw(tile)
                        draw.rectangle([0, 0, tile.width - 1, tile.height - 1], outline=(30, 30, 36), width=2)
                        draw.rectangle([0, 0, tile.width, 26], fill=(20, 20, 24))
                        draw.text((8, 6), f"{category}·{label}", fill=(255, 255, 255))
                        canvas.paste(tile, (pad + idx * (tile_w + gap), pad + 24))
                    draw = ImageDraw.Draw(canvas)
                    draw.text((pad, 6), f"三视图 · {category}", fill=(40, 40, 48))
                    img = canvas
                elif operation == "director":
                    canvas = Image.new("RGB", (1280, 720), (24, 24, 36))
                    draw = ImageDraw.Draw(canvas)
                    draw.text((30, 10), "VibePaper Director Stage", fill=(255, 255, 255))
                    for m in request.params.get("models", []) or []:
                        if not isinstance(m, dict):
                            continue
                        x = int(640 + float(m.get("pos", [0, 0])[0]) * 6)
                        y = int(360 + float(m.get("pos", [0, 0])[1]) * 6)
                        color = m.get("color", "#ff5d5d")
                        draw.ellipse([x - 18, y - 18, x + 18, y + 18], outline=color, width=3)
                        draw.text((x - 20, y + 22), str(m.get("name", "model")), fill=color)
                    img = canvas
            else:
                seed = random.randint(0, 2**31)
                img = Image.new("RGB", (w, h))
                pixels = img.load()
                for y in range(h):
                    for x in range(w):
                        pixels[x, y] = (
                            (x * 255 // max(w, 1) + seed % 80) % 256,
                            (y * 255 // max(h, 1) + seed % 130) % 256,
                            ((x + y) * 255 // max(w + h, 1) + seed % 200) % 256,
                        )
                draw = ImageDraw.Draw(img)
                draw.rectangle([0, 0, w - 1, h - 1], outline=(255, 255, 255), width=4)
                draw.text((20, 20), f"VibePaper · {prompt[:40]}", fill=(255, 255, 255))
                draw.text((20, h - 60), f"{request.model_name} · {w}x{h}", fill=(255, 255, 255))
                if request.params.get("style"):
                    draw.text((20, 50), f"style: {request.params.get('style')}", fill=(230, 230, 230))

            out_path = Path(request.output_dir) / f"output_{i}.jpg"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img = img.convert("RGB")
            img.save(out_path, "JPEG", quality=90)
            outputs.append({
                "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                "file_path": str(out_path),
                "content_type": "image/jpeg",
                "meta": {"index": i, "operation": operation or "generate", "outputType": "image"},
            })
        return ProviderJob(job_id=f"img-{request.task_id}", status="succeeded", result={"outputs": outputs})


def _media_url_for_remote_api(url: str) -> str:
    """外部模型 API 无法拉取 localhost / 内网 URL，本地文件转为 data URL。"""
    from urllib.parse import urlparse

    src = (url or "").strip()
    if not src:
        return src
    if src.startswith("data:"):
        return src
    if src.startswith("http://") or src.startswith("https://"):
        host = (urlparse(src).hostname or "").lower()
        if host not in {"localhost", "127.0.0.1"} and not host.startswith("192.168.") and not host.startswith("10."):
            return src
    local = _resolve_local_media_path(src)
    if local and local.is_file():
        import base64
        import mimetypes

        mime = mimetypes.guess_type(str(local))[0] or "application/octet-stream"
        encoded = base64.b64encode(local.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return src


def _local_reference_image(request: GenerationRequest) -> Path | None:
    ref = first_reference_image(request.params or {})
    if not ref:
        return None
    return _resolve_local_media_path(ref)


def _resolve_ffmpeg() -> str | None:
    configured = (settings.ffmpeg_path or os.environ.get("FFMPEG_PATH") or "").strip()
    if configured:
        p = Path(configured)
        if p.is_file():
            return str(p)

    found = shutil.which("ffmpeg")
    if found:
        return found

    # WinGet 安装的 Gyan.FFmpeg 不一定在服务进程 PATH 中
    if os.name == "nt":
        winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.is_dir():
            candidates = sorted(winget_root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"), key=lambda x: x.stat().st_mtime, reverse=True)
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.strip().lower()
    if c.startswith("0x"):
        c = c[2:]
    if len(c) == 6:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return 99, 102, 241


def _is_valid_mp4(path: Path) -> bool:
    try:
        head = path.read_bytes()[:64]
    except OSError:
        return False
    return len(head) >= 8 and b"ftyp" in head[:32]


def _write_mock_mp4(out_path: Path, *, prompt: str, color: str, duration: int = 2) -> None:
    """生成可播放 mock MP4；优先 ffmpeg 合成带文案预览，失败则复制内置样例。"""
    from PIL import Image, ImageDraw

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _resolve_ffmpeg()
    if ffmpeg:
        poster = out_path.with_suffix(".poster.png")
        try:
            img = Image.new("RGB", (1280, 720), _hex_to_rgb(color))
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, 1279, 719], outline=(255, 255, 255), width=4)
            draw.text((40, 40), "VibePaper Mock Video", fill=(255, 255, 255))
            draw.text((40, 90), (prompt or "video preview")[:72], fill=(230, 230, 240))
            draw.text((40, 680), f"{duration}s · mock provider", fill=(200, 200, 210))
            img.save(poster, "PNG")

            cmd = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-framerate",
                "24",
                "-i",
                str(poster),
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={duration}",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(out_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            if _is_valid_mp4(out_path):
                return
            out_path.unlink(missing_ok=True)
        except Exception:
            out_path.unlink(missing_ok=True)
        finally:
            poster.unlink(missing_ok=True)

    if _MOCK_PREVIEW_MP4.is_file():
        shutil.copy2(_MOCK_PREVIEW_MP4, out_path)
        if _is_valid_mp4(out_path):
            return
        out_path.unlink(missing_ok=True)

    raise RuntimeError("mock mp4 生成失败：请检查 ffmpeg 或内置样例文件")


def _write_mock_mp4_from_image(out_path: Path, image_path: Path, *, prompt: str, duration: int = 2) -> None:
    """用参考图生成 Mock 图生视频（本地联调）。"""
    from PIL import Image, ImageDraw, ImageOps

    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("图生视频 Mock 需要 ffmpeg（或 imageio-ffmpeg）")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    poster = out_path.with_suffix(".poster.png")
    try:
        img = ImageOps.fit(Image.open(image_path).convert("RGB"), (1280, 720), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1279, 719], outline=(255, 255, 255), width=3)
        if prompt:
            draw.text((32, 32), prompt[:72], fill=(255, 255, 255))
        draw.text((32, 680), "Mock · 参考图预览", fill=(220, 220, 230))
        img.save(poster, "PNG")

        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-framerate",
            "24",
            "-i",
            str(poster),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    finally:
        poster.unlink(missing_ok=True)

    if not _is_valid_mp4(out_path):
        out_path.unlink(missing_ok=True)
        raise RuntimeError("参考图转视频失败")


class MockVideoProvider(ModelProvider):
    name = "mock-video"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        prompt = build_generation_prompt(request.params) or "default"
        operation = str(request.params.get("operation") or "")
        count = int(request.params.get("count", 1))
        camera = str(request.params.get("camera") or "")
        outputs = []
        for i in range(count):
            out_dir = Path(request.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            if operation == "提帧":
                # 提帧：输出一张关键帧图片
                from PIL import Image, ImageDraw

                out_path = out_dir / f"frame_{i}.jpg"
                img = Image.new("RGB", (1280, 720), (16, 20, 28))
                draw = ImageDraw.Draw(img)
                draw.text((40, 40), f"Extracted Frame · {prompt[:50]}", fill=(255, 255, 255))
                draw.text((40, 80), f"camera={camera or 'none'}", fill=(200, 200, 200))
                img.save(out_path, "JPEG", quality=90)
                outputs.append({
                    "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                    "file_path": str(out_path),
                    "content_type": "image/jpeg",
                    "meta": {"index": i, "operation": operation, "outputType": "image"},
                })
                continue

            out_path = out_dir / f"output_{i}.mp4"
            color = "0x6366f1"
            if operation == "剪辑":
                color = "0x334155"
            elif operation == "超分":
                color = "0x0f766e"
            elif operation == "compose":
                color = "0x7c3aed"
            ref_image = _local_reference_image(request)
            try:
                if ref_image and ref_image.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    _write_mock_mp4_from_image(out_path, ref_image, prompt=prompt, duration=2)
                    used_ref = True
                else:
                    _write_mock_mp4(out_path, prompt=prompt, color=color, duration=2)
                    used_ref = False
            except Exception as exc:
                return ProviderJob(
                    job_id=f"vid-err-{request.task_id}",
                    status="failed",
                    error_code="MODEL_UNAVAILABLE",
                    error_message=f"Mock 视频生成失败：{exc}",
                )
            outputs.append({
                "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                "file_path": str(out_path),
                "content_type": "video/mp4",
                "meta": {
                    "index": i,
                    "operation": operation or "generate",
                    "camera": camera,
                    "outputType": "video",
                    "usedReference": used_ref,
                    "mockProvider": True,
                },
            })
        return ProviderJob(job_id=f"vid-{request.task_id}", status="succeeded", result={"outputs": outputs})


class MockAudioProvider(ModelProvider):
    name = "mock-audio"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        count = int(request.params.get("count", 1))
        outputs = []
        for i in range(count):
            out_path = Path(request.output_dir) / f"output_{i}.wav"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 44100
            duration = 3
            freq = 220 + i * 80
            with wave.open(str(out_path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                frames = bytearray()
                for n in range(sample_rate * duration):
                    value = int(12000 * math.sin(2 * math.pi * freq * n / sample_rate) * (1 - n / (sample_rate * duration)))
                    frames += value.to_bytes(2, "little", signed=True)
                wf.writeframes(bytes(frames))
            outputs.append({
                "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                "file_path": str(out_path),
                "content_type": "audio/wav",
                "meta": {"index": i, "outputType": "audio"},
            })
        return ProviderJob(job_id=f"aud-{request.task_id}", status="succeeded", result={"outputs": outputs})


class VolcengineArkImageProvider(ModelProvider):
    """火山方舟 Seedream：POST /images/generations（文生图 / 图生图）。"""

    name = "seedream"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        import httpx

        api_key = settings.ark_api_key
        operation = str(request.params.get("operation") or "")
        # 本地轻量加工仍走 Pillow，避免白白烧云额度
        if operation in {"裁剪", "三视图"}:
            return MockImageProvider().generate(request)
        if not api_key:
            return MockImageProvider().generate(request)

        # 仅官方 Endpoint ID 直传；别名回落到配置的免费额度默认
        if request.model_name and request.model_name.startswith("doubao-seedream"):
            model = request.model_name
        else:
            model = settings.ark_image_model or "doubao-seedream-5-0-260128"
        prompt = build_generation_prompt(request.params)
        if operation == "扩图":
            prompt = (prompt or "扩展画面边缘，保持主体完整") + "，outpainting，扩图"
        elif operation == "超分":
            prompt = (prompt or "提升清晰度与细节") + "，高清超分，保留原构图"
        if request.params.get("style"):
            prompt = f"{prompt}\n风格：{request.params.get('style')}"
        if not prompt:
            return ProviderJob(
                job_id=f"seedream-empty-{request.task_id}",
                status="failed",
                error_code="INVALID_INPUT",
                error_message="图片生成需要 prompt",
            )

        size = self._size({**request.params, "_ark_model": model})
        body: dict = {
            "model": model,
            "prompt": prompt[:600],
            "size": size,
            "watermark": bool(request.params.get("watermark", False)),
            "response_format": "url",
        }
        # 图生图 / 扩图超分：传入参考图 URL
        image = first_reference_image(request.params)
        refs = request.params.get("referenceImages") or request.params.get("reference_images") or []
        if not image and refs:
            image = refs[0]
        if image:
            body["image"] = _media_url_for_remote_api(str(image))
        if operation in {"扩图", "超分"} and not image:
            # 无参考图时仍可文生图，但提示调用方
            pass

        count = max(1, min(int(request.params.get("count", 1)), 4))
        # Seedream 单次默认 1 张；多份则循环调用（比开组图更可控）
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        base = settings.ark_base_url.rstrip("/")
        outputs = []
        try:
            with httpx.Client(timeout=120.0) as client:
                for i in range(count):
                    resp = client.post(f"{base}/images/generations", headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    url = self._extract_image_url(data)
                    if not url:
                        return ProviderJob(
                            job_id=f"seedream-bad-{request.task_id}",
                            status="failed",
                            error_code="MODEL_UNAVAILABLE",
                            error_message=f"Seedream 未返回图片 URL: {data}",
                        )
                    out_path = Path(request.output_dir) / f"seedream_{i}.jpg"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    if url.startswith("data:"):
                        import base64

                        raw = url.split(",", 1)[-1]
                        out_path.write_bytes(base64.b64decode(raw))
                    else:
                        with client.stream("GET", url, timeout=120.0) as dl:
                            dl.raise_for_status()
                            with out_path.open("wb") as f:
                                for chunk in dl.iter_bytes():
                                    f.write(chunk)
                    outputs.append({
                        "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                        "file_path": str(out_path),
                        "content_type": "image/jpeg",
                        "meta": {
                            "outputType": "image",
                            "provider": self.name,
                            "model": model,
                            "operation": operation or "generate",
                            "remoteUrl": url,
                            "index": i,
                        },
                    })
            return ProviderJob(
                job_id=f"seedream-{request.task_id}",
                status="succeeded",
                result={"outputs": outputs},
            )
        except Exception as e:
            return ProviderJob(
                job_id=f"seedream-err-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message=str(e)[:500],
            )

    @staticmethod
    def _size(params: dict) -> str:
        explicit = str(params.get("size") or "").strip()
        model = str(params.get("_ark_model") or settings.ark_image_model or "")
        # Seedream 5.x：只接受 WIDTHxHEIGHT / 2K / 3K / 4K，且像素数 ≥ 3686400（约 2K）
        if "seedream-5" in model or "seedream_5" in model:
            if explicit.upper() in {"2K", "3K", "4K"}:
                return explicit.upper()
            if "x" in explicit.lower():
                try:
                    w, h = (int(x) for x in explicit.lower().split("x", 1))
                    if w * h >= 3686400:
                        return f"{w}x{h}"
                except Exception:
                    pass
            resolution = str(params.get("resolution") or "")
            mapping = {
                "512x512": "2K",
                "768x768": "2K",
                "1024x1024": "2K",
                "1280x720": "2K",
                "1920x1080": "1920x1080",
                "3840x2160": "4K",
            }
            return mapping.get(resolution, "2K")
        if explicit.upper() in {"1K", "2K", "4K"}:
            return explicit.upper()
        resolution = str(params.get("resolution") or "")
        mapping = {
            "512x512": "1K",
            "768x768": "1K",
            "1024x1024": "1K",
            "1280x720": "2K",
            "1920x1080": "2K",
            "3840x2160": "4K",
        }
        return mapping.get(resolution, settings.ark_image_size or "1K")

    @staticmethod
    def _extract_image_url(payload: dict) -> str | None:
        data = payload.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if first.get("url"):
                    return first["url"]
                b64 = first.get("b64_json")
                if b64:
                    return f"data:image/jpeg;base64,{b64}"
        if isinstance(data, dict) and data.get("url"):
            return data["url"]
        if payload.get("url"):
            return payload["url"]
        return None


class VolcengineArkVideoProvider(ModelProvider):
    """火山方舟 Seedance：POST /contents/generations/tasks + 轮询下载。"""

    name = "volcengine-ark"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        import time

        import httpx

        api_key = settings.ark_api_key
        if not api_key:
            return ProviderJob(
                job_id=f"ark-no-key-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message="未配置火山方舟 API Key（VIBEPAPER_ARK_API_KEY），无法调用视频生成",
            )

        base = settings.ark_base_url.rstrip("/")
        model = resolve_video_model(request.model_name)
        prompt = build_generation_prompt(request.params)
        if not prompt:
            return ProviderJob(
                job_id=f"ark-empty-{request.task_id}",
                status="failed",
                error_code="INVALID_INPUT",
                error_message="视频生成需要 prompt",
            )

        resolution = str(request.params.get("resolution") or "")
        ratio_map = {
            "1280x720": "16:9",
            "1920x1080": "16:9",
            "720x1280": "9:16",
            "1080x1920": "9:16",
            "1024x1024": "1:1",
        }
        ratio = str(request.params.get("ratio") or ratio_map.get(resolution, "16:9"))
        duration = int(request.params.get("duration") or settings.ark_video_duration or 5)
        duration = max(2, min(duration, 12))
        text = prompt
        if request.params.get("camera"):
            text = f"{prompt}\n运镜：{request.params.get('camera')}"
        if request.params.get("style"):
            text = f"{text}\n风格：{request.params.get('style')}"

        content: list[dict] = [{"type": "text", "text": text}]
        first = request.params.get("firstFrameUrl")
        last = request.params.get("lastFrameUrl")
        if isinstance(first, str) and first.strip():
            content.append({
                "type": "image_url",
                "image_url": {"url": _media_url_for_remote_api(first.strip())},
                "role": "first_frame",
            })
        if isinstance(last, str) and last.strip():
            content.append({
                "type": "image_url",
                "image_url": {"url": _media_url_for_remote_api(last.strip())},
                "role": "last_frame",
            })
        ref_urls = _normalize_str_list(
            request.params.get("referenceUrls") or request.params.get("referenceImages") or request.params.get("reference_images"),
        )
        skip = {str(first or "").strip(), str(last or "").strip()}
        for url in ref_urls:
            if url in skip:
                continue
            content.append({
                "type": "image_url",
                "image_url": {"url": _media_url_for_remote_api(url)},
                "role": "reference_image",
            })
        single = request.params.get("imageUrl") or request.params.get("image_url") or request.params.get("referenceUrl")
        if single and not any(c.get("type") == "image_url" for c in content):
            content.append({
                "type": "image_url",
                "image_url": {"url": _media_url_for_remote_api(str(single))},
                "role": "reference_image",
            })
        for url in request.params.get("referenceVideos") or request.params.get("reference_videos") or []:
            if url:
                content.append({"type": "video_url", "video_url": {"url": url}, "role": "reference_video"})
        for url in request.params.get("referenceAudios") or request.params.get("reference_audios") or []:
            if url:
                content.append({"type": "audio_url", "audio_url": {"url": url}, "role": "reference_audio"})

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "content": content,
            "generate_audio": bool(request.params.get("generate_audio", True)),
            "ratio": ratio,
            "duration": duration,
            "watermark": bool(request.params.get("watermark", False)),
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                create = client.post(f"{base}/contents/generations/tasks", headers=headers, json=body)
                if create.status_code >= 400:
                    err_code, err_msg = parse_ark_http_error(create)
                    return ProviderJob(
                        job_id=f"ark-http-{request.task_id}",
                        status="failed",
                        error_code=err_code,
                        error_message=err_msg,
                    )
                created = create.json()
                ark_id = created.get("id") or created.get("task_id") or (created.get("data") or {}).get("id")
                if not ark_id:
                    return ProviderJob(
                        job_id=f"ark-bad-{request.task_id}",
                        status="failed",
                        error_code="MODEL_UNAVAILABLE",
                        error_message=f"方舟未返回任务 ID: {created}",
                    )

                deadline = time.time() + max(60, settings.ark_poll_timeout_seconds)
                last: dict = {}
                while time.time() < deadline:
                    poll = client.get(f"{base}/contents/generations/tasks/{ark_id}", headers=headers)
                    if poll.status_code >= 400:
                        err_code, err_msg = parse_ark_http_error(poll)
                        return ProviderJob(
                            job_id=str(ark_id),
                            status="failed",
                            error_code=err_code,
                            error_message=err_msg,
                        )
                    last = poll.json()
                    data = last.get("data") if isinstance(last.get("data"), dict) else last
                    status = str((data or {}).get("status") or last.get("status") or "").lower()
                    if status in {"succeeded", "success", "completed", "done"}:
                        video_url = self._extract_video_url(last)
                        if not video_url:
                            return ProviderJob(
                                job_id=str(ark_id),
                                status="failed",
                                error_code="MODEL_UNAVAILABLE",
                                error_message=f"任务成功但无视频 URL: {last}",
                            )
                        out_path = Path(request.output_dir) / "seedance.mp4"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        with client.stream("GET", video_url, timeout=180.0) as resp:
                            resp.raise_for_status()
                            with out_path.open("wb") as f:
                                for chunk in resp.iter_bytes():
                                    f.write(chunk)
                        return ProviderJob(
                            job_id=str(ark_id),
                            status="succeeded",
                            result={
                                "outputs": [{
                                    "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                                    "file_path": str(out_path),
                                    "content_type": "video/mp4",
                                    "meta": {
                                        "outputType": "video",
                                        "provider": self.name,
                                        "arkTaskId": ark_id,
                                        "remoteUrl": video_url,
                                    },
                                }]
                            },
                        )
                    if status in {"failed", "error", "cancelled", "canceled"}:
                        return ProviderJob(
                            job_id=str(ark_id),
                            status="failed",
                            error_code="MODEL_UNAVAILABLE",
                            error_message=str(last.get("error") or last.get("message") or last)[:500],
                        )
                    time.sleep(max(2, settings.ark_poll_interval_seconds))
                return ProviderJob(
                    job_id=str(ark_id),
                    status="failed",
                    error_code="MODEL_TIMEOUT",
                    error_message=f"方舟视频任务超时: {last}",
                )
        except httpx.HTTPStatusError as e:
            resp = e.response
            err_code, err_msg = parse_ark_http_error(resp) if resp is not None else ("MODEL_UNAVAILABLE", str(e))
            return ProviderJob(
                job_id=f"ark-err-{request.task_id}",
                status="failed",
                error_code=err_code,
                error_message=err_msg,
            )
        except Exception as e:
            return ProviderJob(
                job_id=f"ark-err-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message=str(e)[:500],
            )

    @staticmethod
    def _extract_video_url(payload: dict) -> str | None:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        content = data.get("content") if isinstance(data, dict) else None

        def from_video_field(val: object) -> str | None:
            if isinstance(val, str) and val.startswith("http"):
                return val
            if isinstance(val, dict):
                url = val.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    return url
            return None

        # Seedance 成功体：content 为对象 {"video_url": "https://..."}
        if isinstance(content, dict):
            for key in ("video_url", "url", "output_url"):
                found = from_video_field(content.get(key))
                if found:
                    return found
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                found = from_video_field(item.get("video_url"))
                if found:
                    return found
                if item.get("type") == "video_url":
                    found = from_video_field(item.get("url")) or from_video_field(item.get("video_url"))
                    if found:
                        return found
        for key in ("video_url", "url", "output_url"):
            found = from_video_field(data.get(key) if isinstance(data, dict) else None)
            if found:
                return found
        output = data.get("output") if isinstance(data, dict) else None
        if isinstance(output, dict):
            for key in ("video_url", "url"):
                found = from_video_field(output.get(key))
                if found:
                    return found
        return None


class ComfyUIProvider(ModelProvider):
    """ComfyUI 适配占位：仅当配置 VIBEPAPER_COMFYUI_BASE_URL 时启用，否则不可用。"""

    name = "comfyui"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        if not settings.comfyui_base_url:
            return ProviderJob(
                job_id=f"comfy-off-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message="ComfyUI 未接入：请配置 VIBEPAPER_COMFYUI_BASE_URL 并启动 ComfyUI",
            )
        # 最小探测：/system_stats；完整工作流提交后续按 workflow 注册表扩展
        try:
            import httpx

            base = settings.comfyui_base_url.rstrip("/")
            r = httpx.get(f"{base}/system_stats", timeout=10)
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI 不可用: HTTP {r.status_code}")
            return ProviderJob(
                job_id=f"comfy-stub-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message="ComfyUI 已连通，但 workflow 提交尚未实现（仅探测在线）",
            )
        except Exception as e:
            return ProviderJob(
                job_id=f"comfy-err-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message=str(e)[:300],
            )


class ComposeProvider(ModelProvider):
    """多段视频按顺序拼接（FFmpeg concat）。"""

    name = "mock-compose"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        import httpx

        urls = _normalize_str_list(request.params.get("inputUrls") or request.params.get("inputs"))
        if len(urls) < 2:
            return ProviderJob(
                job_id=f"compose-bad-{request.task_id}",
                status="failed",
                error_code="INVALID_INPUT",
                error_message="合成至少需要 2 段视频输入",
            )

        ffmpeg = _resolve_ffmpeg()
        if not ffmpeg:
            return ProviderJob(
                job_id=f"compose-ff-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message="合成需要 ffmpeg，请安装后重试",
            )

        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        work = out_dir / "_compose_inputs"
        work.mkdir(parents=True, exist_ok=True)

        local_paths: list[Path] = []
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                for i, url in enumerate(urls):
                    local = _resolve_local_media_path(url)
                    if local and local.is_file():
                        local_paths.append(local)
                        continue
                    if url.startswith("data:"):
                        import base64

                        header, _, b64 = url.partition(",")
                        ext = ".mp4"
                        if "webm" in header:
                            ext = ".webm"
                        dest = work / f"input_{i}{ext}"
                        dest.write_bytes(base64.b64decode(b64))
                        local_paths.append(dest)
                        continue
                    if url.startswith("http://") or url.startswith("https://"):
                        dest = work / f"input_{i}.mp4"
                        with client.stream("GET", url) as resp:
                            resp.raise_for_status()
                            with dest.open("wb") as f:
                                for chunk in resp.iter_bytes():
                                    f.write(chunk)
                        local_paths.append(dest)
                        continue
                    return ProviderJob(
                        job_id=f"compose-miss-{request.task_id}",
                        status="failed",
                        error_code="INVALID_INPUT",
                        error_message=f"无法读取第 {i + 1} 段视频：{url[:120]}",
                    )

            if len(local_paths) < 2:
                return ProviderJob(
                    job_id=f"compose-few-{request.task_id}",
                    status="failed",
                    error_code="INVALID_INPUT",
                    error_message="有效视频不足 2 段，无法合成",
                )

            out_path = out_dir / "compose.mp4"
            # 统一重编码再拼接，避免编码/分辨率不一致导致 concat 失败
            normalized: list[Path] = []
            for i, src in enumerate(local_paths):
                norm = work / f"norm_{i}.mp4"
                cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(src),
                    "-vf",
                    "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-shortest",
                    str(norm),
                ]
                proc = subprocess.run(cmd, capture_output=True, timeout=180)
                if proc.returncode != 0 or not _is_valid_mp4(norm):
                    err = (proc.stderr or b"").decode("utf-8", errors="ignore")[-400:]
                    return ProviderJob(
                        job_id=f"compose-norm-{request.task_id}",
                        status="failed",
                        error_code="MODEL_UNAVAILABLE",
                        error_message=f"第 {i + 1} 段视频转码失败：{err or 'unknown'}",
                    )
                normalized.append(norm)

            list_file = work / "concat.txt"
            list_file.write_text(
                "".join(f"file '{p.resolve().as_posix()}'\n" for p in normalized),
                encoding="utf-8",
            )
            concat_cmd = [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(out_path),
            ]
            proc = subprocess.run(concat_cmd, capture_output=True, timeout=180)
            if proc.returncode != 0 or not _is_valid_mp4(out_path):
                # copy 失败时再尝试重编码拼接
                concat_cmd = [
                    ffmpeg,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_file),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(out_path),
                ]
                proc = subprocess.run(concat_cmd, capture_output=True, timeout=240)
                if proc.returncode != 0 or not _is_valid_mp4(out_path):
                    err = (proc.stderr or b"").decode("utf-8", errors="ignore")[-400:]
                    return ProviderJob(
                        job_id=f"compose-cat-{request.task_id}",
                        status="failed",
                        error_code="MODEL_UNAVAILABLE",
                        error_message=f"视频拼接失败：{err or 'unknown'}",
                    )

            return ProviderJob(
                job_id=f"compose-{request.task_id}",
                status="succeeded",
                result={
                    "outputs": [
                        {
                            "url": f"/api/v1/tasks/{request.task_id}/outputs/file/{out_path.name}",
                            "file_path": str(out_path),
                            "content_type": "video/mp4",
                            "meta": {
                                "outputType": "video",
                                "operation": "compose",
                                "inputCount": len(normalized),
                                "provider": self.name,
                            },
                        }
                    ]
                },
            )
        except Exception as e:
            return ProviderJob(
                job_id=f"compose-err-{request.task_id}",
                status="failed",
                error_code="MODEL_UNAVAILABLE",
                error_message=str(e)[:500],
            )


class MockComposeProvider(ComposeProvider):
    """兼容旧注册名。"""

    name = "mock-compose"


class MockDirectorProvider(MockImageProvider):
    name = "mock-director"

    def generate(self, request: GenerationRequest) -> ProviderJob:
        params = dict(request.params)
        params["operation"] = "director"
        return super().generate(GenerationRequest(
            task_id=request.task_id,
            model_type=request.model_type,
            model_name=request.model_name,
            params=params,
            output_dir=request.output_dir,
        ))


_openai_text = OpenAICompatibleTextProvider()

PROVIDER_REGISTRY: dict[str, ModelProvider] = {
    "mock": MockTextProvider(),
    "mock-text": MockTextProvider(),
    "mock-image": MockImageProvider(),
    "mock-video": MockVideoProvider(),
    "mock-audio": MockAudioProvider(),
    "mock-compose": ComposeProvider(),
    "mock-director": MockDirectorProvider(),
    "openai": _openai_text,
    "openai-text": _openai_text,
    "deepseek": _openai_text,
    "qwen": _openai_text,
    "seedream": VolcengineArkImageProvider(),
    "volcengine-ark-image": VolcengineArkImageProvider(),
    "volcengine-ark": VolcengineArkVideoProvider(),
    "seedance": VolcengineArkVideoProvider(),
    "comfyui": ComfyUIProvider(),
}


def get_provider(provider_name: str, model_type: str | None = None) -> ModelProvider:
    modality = (model_type or "").lower()
    pname = (provider_name or "").lower()

    # 按模型名优先分流（同 Key 下图/视频不同 endpoint）
    if "seedream" in pname or "seedream" in modality:
        return PROVIDER_REGISTRY["seedream"]
    if "seedance" in pname or "seedance" in modality:
        return PROVIDER_REGISTRY["seedance"]

    if pname in PROVIDER_REGISTRY and pname != "mock":
        # volcengine-ark 可能被误标在图片模型上，按模态纠正
        if pname == "volcengine-ark" and (
            modality in {"image"} or modality.startswith("flux") or modality.startswith("seedream")
        ):
            return PROVIDER_REGISTRY["seedream"]
        return PROVIDER_REGISTRY[pname]

    if modality in {"compose"} or "compose" in modality:
        return PROVIDER_REGISTRY["mock-compose"]
    if modality in {"director"} or "director" in modality:
        return PROVIDER_REGISTRY["mock-director"]
    if modality in {"image"} or modality.startswith("flux") or modality.startswith("sd"):
        if settings.ark_api_key:
            return PROVIDER_REGISTRY["seedream"]
        return PROVIDER_REGISTRY["mock-image"]
    if modality in {"video"} or modality.startswith("wan") or modality.startswith("kling"):
        if pname == "mock-video":
            return PROVIDER_REGISTRY["mock-video"]
        return PROVIDER_REGISTRY["seedance"]
    if modality in {"audio"} or modality.startswith("music") or modality.startswith("audio"):
        return PROVIDER_REGISTRY["mock-audio"]
    if pname in {"openai", "openai-text", "deepseek", "qwen"} or modality in {"text"}:
        return PROVIDER_REGISTRY["openai-text"]
    if pname == "comfyui":
        return PROVIDER_REGISTRY["comfyui"]
    return PROVIDER_REGISTRY["mock-text"]
