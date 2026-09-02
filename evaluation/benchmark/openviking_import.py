from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any


def auth_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    mappings = (
        ("api_key_env", "X-API-Key"),
        ("account_env", "X-OpenViking-Account"),
        ("user_env", "X-OpenViking-User"),
        ("actor_peer_env", "X-OpenViking-Actor-Peer"),
    )
    for config_key, header in mappings:
        env_name = config.get(config_key)
        if env_name and os.environ.get(str(env_name)):
            headers[header] = os.environ[str(env_name)]
    return headers


def request_json(
    base_url: str,
    method: str,
    path: str,
    headers: dict[str, str],
    timeout_seconds: int,
    *,
    body: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> Any:
    if body is not None and raw_body is not None:
        raise ValueError("body and raw_body are mutually exclusive")
    data = json.dumps(body).encode("utf-8") if body is not None else raw_body
    request_headers = {**headers, "Content-Type": content_type}
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"OpenViking HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenViking connection failed: {exc.reason}") from exc


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("status") == "ok" and "result" in payload:
        return payload["result"]
    return payload


def build_zip(corpus_dir: Path, destination: Path) -> None:
    evidence_dir = corpus_dir / "evidence-pages"
    if not evidence_dir.is_dir():
        raise ValueError(f"evidence-pages directory not found: {evidence_dir}")
    files = sorted(path for path in evidence_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"corpus directory contains no files: {corpus_dir}")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(corpus_dir).as_posix())


def multipart_file(field: str, path: Path) -> tuple[bytes, str]:
    boundary = f"----data-context-eval-{uuid.uuid4().hex}"
    filename = path.name.replace('"', "")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return prefix + path.read_bytes() + suffix, f"multipart/form-data; boundary={boundary}"


def import_corpus(
    corpus_dir: Path,
    config: dict[str, Any],
    *,
    wait: bool = True,
) -> dict[str, Any]:
    corpus_dir = corpus_dir.resolve()
    if not (corpus_dir / "corpus-manifest.json").is_file():
        raise ValueError("corpus-manifest.json not found; materialize the neutral corpus first")
    base_url = str(config.get("base_url", "http://127.0.0.1:1933"))
    target_uri = str(config.get("target_uri", ""))
    if not target_uri.startswith("viking://resources/"):
        raise ValueError("target_uri must be an explicit viking://resources/... URI")
    timeout_seconds = int(config.get("timeout_seconds", 300))
    headers = auth_headers(config)

    with tempfile.TemporaryDirectory(prefix="data-context-eval-") as temp_dir:
        zip_path = Path(temp_dir) / "enterprise-context-eval-corpus.zip"
        build_zip(corpus_dir, zip_path)
        upload_body, upload_type = multipart_file("file", zip_path)
        upload_payload = request_json(
            base_url,
            "POST",
            "/api/v1/resources/temp_upload",
            headers,
            timeout_seconds,
            raw_body=upload_body,
            content_type=upload_type,
        )
        upload_result = unwrap(upload_payload)
        temp_file_id = upload_result.get("temp_file_id") if isinstance(upload_result, dict) else None
        if not temp_file_id:
            raise RuntimeError("OpenViking temp upload did not return temp_file_id")
        add_payload = request_json(
            base_url,
            "POST",
            "/api/v1/resources",
            headers,
            timeout_seconds,
            body={
                "temp_file_id": temp_file_id,
                "to": target_uri,
                "wait": wait,
                "timeout": timeout_seconds if wait else None,
                "strict": False,
                "preserve_structure": True,
                "reason": "Versioned enterprise-context retrieval evaluation corpus",
                "instruction": (
                    "Preserve factual text, EVIDENCE_ID markers, assertion status, review status, "
                    "semantic relations, and source provenance. Do not invent missing facts."
                ),
                "telemetry": True,
                "tags": ["enterprise-context-eval"],
            },
        )
    return {
        "target_uri": target_uri,
        "wait": wait,
        "result": unwrap(add_payload),
    }
