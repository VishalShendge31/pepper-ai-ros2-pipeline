#!/usr/bin/env python3
"""
Spark-TTS HTTP server using the exact Hugging Face model-card inference path for:
    Vishalshendge3198/spark_tts_finetune

This intentionally uses:
    from unsloth import FastLanguageModel
    FastLanguageModel.from_pretrained(... dtype=None, load_in_4bit=False)
    FastLanguageModel.for_inference(model)
    BiCodecTokenizer(...)
    model.generate(... do_sample=True, temperature=0.8, top_k=50, top_p=1.0)

The ROS node calls this server at POST /tts and receives a generated WAV path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import soundfile as sf
import torch


ALLOWED_EMOTIONS = {
    "happy",
    "angry",
    "sad",
    "thoughtful",
    "neutral",
    "sleepy",
    "whisper",
    "worried",
    "annoyed",
    "surprised",
    "fearful",
    "contemptuous",
    "disgusted",
}

TAG_PATTERN = re.compile(r"^\s*\[[^\]]+\]")
SEMANTIC_PATTERN = re.compile(r"<\|bicodec_semantic_(\d+)\|>")
GLOBAL_PATTERN = re.compile(r"<\|bicodec_global_(\d+)\|>")


class SparkTTSEngine:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.device = self._resolve_device(args.device)

        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        sys.path.insert(0, args.spark_repo_dir)

        # Exact model-card imports.
        from unsloth import FastLanguageModel
        from sparktts.models.audio_tokenizer import BiCodecTokenizer

        print("[Spark-TTS] Loading model with Unsloth FastLanguageModel...", flush=True)
        print(f"[Spark-TTS] model_name={args.model_name_or_path}", flush=True)
        print(f"[Spark-TTS] max_seq_length={args.max_seq_length}", flush=True)
        print(f"[Spark-TTS] load_in_4bit={args.load_in_4bit}", flush=True)
        print(f"[Spark-TTS] dtype=None, matching the Hugging Face model-card example", flush=True)

        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.model_name_or_path,
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=args.load_in_4bit,
        )
        FastLanguageModel.for_inference(self.model)

        print("[Spark-TTS] Loading BiCodecTokenizer...", flush=True)
        self.audio_tokenizer = BiCodecTokenizer(args.spark_tts_dir, device=self.device)

        self.lock = threading.Lock()
        print(f"[Spark-TTS] Ready on device={self.device}", flush=True)

    @staticmethod
    def _resolve_device(device_arg: str) -> str:
        device_arg = (device_arg or "auto").strip().lower()
        if device_arg == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device_arg

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "device": self.device,
            "model": self.args.model_name_or_path,
            "spark_tts_dir": self.args.spark_tts_dir,
            "backend": "unsloth_fast_language_model_exact_model_card",
        }

    def synthesize(self, text: str, emotion: str | None = None) -> Dict[str, Any]:
        text = self._prepare_text(text, emotion)

        with self.lock:
            start_time = time.time()

            # Exact prompt format from the model card.
            prompt = f"<|task_tts|><|start_content|>{text}<|end_content|><|start_global_token|>"
            inputs = self.tokenizer([prompt], return_tensors="pt").to(self.device)

            # Exact generation settings from the model card.
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.args.max_new_tokens,
                do_sample=True,
                temperature=self.args.temperature,
                top_k=self.args.top_k,
                top_p=self.args.top_p,
                eos_token_id=self.tokenizer.eos_token_id,
            )

            generated_ids_trimmed = generated_ids[:, inputs.input_ids.shape[1] :]
            predicts_text = self.tokenizer.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=False,
            )[0]

            global_ids, semantic_ids = self._extract_audio_tokens(predicts_text)

            waveform = self.audio_tokenizer.detokenize(
                global_ids.squeeze(0).to(self.device),
                semantic_ids.to(self.device),
            )

            waveform_np = self._to_numpy_audio(waveform)
            sample_rate = int(self.audio_tokenizer.config.get("sample_rate", 16000))

            wav_path = self.output_dir / f"pepper_spark_tts_{int(time.time() * 1000)}.wav"
            sf.write(str(wav_path), waveform_np, sample_rate)

            elapsed = time.time() - start_time

        return {
            "ok": True,
            "text": text,
            "wav_path": str(wav_path),
            "sample_rate": sample_rate,
            "elapsed_sec": elapsed,
            "semantic_tokens": int(semantic_ids.numel()),
        }

    def _prepare_text(self, text: str, emotion: str | None) -> str:
        text = (text or "").strip()
        text = text.replace("\u0000", "")
        text = " ".join(text.split())

        if not text:
            raise ValueError("Empty text received")

        if len(text) > self.args.max_text_chars:
            text = text[: self.args.max_text_chars].rsplit(" ", 1)[0].strip()

        # Preserve explicit model-card style tags, e.g. [happy], [sighs].
        if TAG_PATTERN.match(text):
            return text

        emotion = (emotion or self.args.default_emotion or "neutral").strip().lower()
        if emotion not in ALLOWED_EMOTIONS:
            emotion = "neutral"

        return f"[{emotion}] {text}"

    def _extract_audio_tokens(self, predicts_text: str) -> Tuple[torch.Tensor, torch.Tensor]:
        # Exact token extraction logic from the model card, with validation added.
        semantic_values = [int(t) for t in SEMANTIC_PATTERN.findall(predicts_text)]
        global_values = [int(t) for t in GLOBAL_PATTERN.findall(predicts_text)][:32]

        if not semantic_values:
            preview = predicts_text[:500].replace("\n", " ")
            raise RuntimeError(
                "The model generated no bicodec semantic audio tokens. "
                f"Decoded preview: {preview}"
            )

        global_values += [0] * (32 - len(global_values))

        semantic_ids = torch.tensor(semantic_values).long().unsqueeze(0)
        global_ids = torch.tensor(global_values).long().unsqueeze(0).unsqueeze(0)

        return global_ids, semantic_ids

    @staticmethod
    def _to_numpy_audio(waveform: Any) -> np.ndarray:
        if isinstance(waveform, torch.Tensor):
            waveform = waveform.detach().cpu().numpy()
        waveform = np.asarray(waveform, dtype=np.float32).squeeze()
        if waveform.ndim != 1:
            waveform = waveform.reshape(-1)
        waveform = np.nan_to_num(waveform)
        waveform = np.clip(waveform, -1.0, 1.0)
        return waveform


class RequestHandler(BaseHTTPRequestHandler):
    engine: SparkTTSEngine | None = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(self.engine.health() if self.engine else {"ok": False, "error": "engine not loaded"})
        else:
            self._send_json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/tts":
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body else {}

            text = payload.get("text", "")
            emotion = payload.get("emotion")

            if self.engine is None:
                raise RuntimeError("Spark-TTS engine not loaded")

            result = self.engine.synthesize(text=text, emotion=emotion)
            self._send_json(result)

        except Exception as exc:
            traceback.print_exc()
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[Spark-TTS HTTP] {self.address_string()} - {fmt % args}", flush=True)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--spark-repo-dir", required=True)
    parser.add_argument("--model-name-or-path", default="Vishalshendge3198/spark_tts_finetune")
    parser.add_argument("--spark-tts-dir", required=True)
    parser.add_argument("--output-dir", default="/tmp/pepper_custom_tts")
    parser.add_argument("--device", default="auto", help="auto, cuda, cuda:0, or cpu")
    parser.add_argument("--default-emotion", default="neutral")
    parser.add_argument("--max-text-chars", type=int, default=350)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--load-in-4bit", action="store_true", default=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not Path(args.spark_repo_dir).exists():
        raise FileNotFoundError(f"Spark-TTS repo not found: {args.spark_repo_dir}")
    if not Path(args.spark_tts_dir).exists():
        raise FileNotFoundError(f"Spark-TTS base tokenizer/model folder not found: {args.spark_tts_dir}")

    RequestHandler.engine = SparkTTSEngine(args)

    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    print(f"[Spark-TTS] HTTP server listening at http://{args.host}:{args.port}", flush=True)
    print("[Spark-TTS] Endpoints: GET /health, POST /tts", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[Spark-TTS] Shutting down", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
