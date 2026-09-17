"""ComfyUI HTTP + WebSocket client.

One shared WebSocket connection carries progress for every job. Messages are
dispatched by `prompt_id` to whichever job registered for it; messages that
arrive before the job has registered (the socket is faster than our own
`POST /prompt` response) are buffered briefly and replayed, so nothing is lost
to that race.

The socket is best-effort. It reconnects on its own, and the job runner also
polls `/history`, so a dropped connection costs progress updates but never a
result.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncIterator, Callable

import httpx

try:  # websockets >= 13
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # pragma: no cover - older websockets
    from websockets.client import connect as ws_connect  # type: ignore

log = logging.getLogger("makery.comfy")

# How long to hold messages for a prompt_id nobody has registered for yet.
_BUFFER_SECONDS = 30.0


class ComfyError(RuntimeError):
    """ComfyUI refused the job or could not be reached."""


def _describe_prompt_error(payload: dict) -> str:
    """Turn a POST /prompt rejection into something a human can act on.

    A missing custom node shows up here as a `node_errors` blob. Surfacing it
    verbatim is the difference between "it broke" and "install ResolutionSelector".
    """
    bits = []
    err = payload.get("error")
    if isinstance(err, dict):
        bits.append(err.get("message") or str(err))
        if err.get("details"):
            bits.append(str(err["details"]))
    elif err:
        bits.append(str(err))

    for node_id, node_err in (payload.get("node_errors") or {}).items():
        cls = node_err.get("class_type", "?")
        for e in node_err.get("errors") or []:
            bits.append(f"node {node_id} ({cls}): {e.get('message')} {e.get('details', '')}".strip())
        if not node_err.get("errors"):
            bits.append(f"node {node_id} ({cls}): rejected")

    return " | ".join(b for b in bits if b) or "ComfyUI rejected the job"


class ComfyClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        # Generation holds the connection open for minutes; /view streams can be
        # large. Connect fast, read slowly.
        self._http = httpx.AsyncClient(
            base_url=self.base,
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=120.0, pool=10.0),
        )
        self._listeners: dict[str, Callable[[str, dict], None]] = {}
        self._buffer: dict[str, list[tuple[float, str, dict]]] = {}
        self._ws_task: asyncio.Task | None = None
        self.ws_connected = False

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = asyncio.create_task(self._ws_loop(), name="comfy-ws")

    async def aclose(self) -> None:
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        await self._http.aclose()

    # --- progress dispatch -------------------------------------------------

    def listen(self, prompt_id: str, callback: Callable[[str, dict], None]) -> None:
        self._listeners[prompt_id] = callback
        for _, mtype, data in self._buffer.pop(prompt_id, []):
            callback(mtype, data)

    def unlisten(self, prompt_id: str) -> None:
        self._listeners.pop(prompt_id, None)
        self._buffer.pop(prompt_id, None)

    def _dispatch(self, msg: dict) -> None:
        mtype = msg.get("type")
        data = msg.get("data") or {}
        prompt_id = data.get("prompt_id")
        if not mtype or not prompt_id:
            return
        callback = self._listeners.get(prompt_id)
        if callback is not None:
            try:
                callback(mtype, data)
            except Exception:
                log.exception("progress callback failed")
            return
        self._prune_buffer()
        self._buffer.setdefault(prompt_id, []).append((time.monotonic(), mtype, data))

    def _prune_buffer(self) -> None:
        cutoff = time.monotonic() - _BUFFER_SECONDS
        for pid in [p for p, items in self._buffer.items() if items[-1][0] < cutoff]:
            del self._buffer[pid]

    async def _ws_loop(self) -> None:
        scheme = "wss" if self.base.startswith("https") else "ws"
        host = self.base.split("://", 1)[1]
        url = f"{scheme}://{host}/ws?clientId={self.client_id}"
        backoff = 1.0
        while True:
            try:
                async with ws_connect(url, max_size=None, ping_interval=20) as ws:
                    self.ws_connected = True
                    backoff = 1.0
                    log.info("comfy websocket connected")
                    async for raw in ws:
                        if isinstance(raw, (bytes, bytearray)):
                            continue  # binary preview frames; not needed
                        try:
                            self._dispatch(json.loads(raw))
                        except json.JSONDecodeError:
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("comfy websocket: %s", exc)
            finally:
                self.ws_connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    # --- HTTP API ----------------------------------------------------------

    async def submit(self, graph: dict) -> str:
        try:
            r = await self._http.post(
                "/prompt", json={"prompt": graph, "client_id": self.client_id}
            )
        except httpx.HTTPError as exc:
            raise ComfyError(f"could not reach ComfyUI: {exc}") from exc

        if r.status_code != 200:
            try:
                payload = r.json()
            except ValueError:
                raise ComfyError(f"ComfyUI returned HTTP {r.status_code}: {r.text[:400]}")
            raise ComfyError(_describe_prompt_error(payload))

        # A 200 is not a promise of JSON: a proxy in front of ComfyUI can
        # answer an HTML holding page with that status. Unguarded, the
        # ValueError escapes as itself rather than as ComfyError, and the job
        # runner - which only knows how to fail a job on ComfyError - dies
        # instead, leaving the app stuck saying it is busy until it restarts.
        try:
            payload = r.json()
        except ValueError:
            raise ComfyError(f"ComfyUI's reply was not JSON: {r.text[:200]}")
        prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
        if not prompt_id:
            raise ComfyError("ComfyUI accepted the job but returned no prompt_id")
        return prompt_id

    async def history(self, prompt_id: str) -> dict | None:
        try:
            r = await self._http.get(f"/history/{prompt_id}")
            r.raise_for_status()
            # ValueError alongside the HTTP errors, for the same reason
            # `queue_position` catches it: a non-JSON body (an error page, an
            # empty response, a proxy's timeout) is one poll that told us
            # nothing, not a reason to take the whole job runner down with it.
            # The loop simply asks again on its next pass.
            body = r.json() or {}
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("history poll failed: %s", exc)
            return None
        return body.get(prompt_id) if isinstance(body, dict) else None

    async def queue_position(self, prompt_id: str) -> int | None:
        """Return how many jobs are ahead of this one, or None if it is running."""
        try:
            r = await self._http.get("/queue")
            r.raise_for_status()
            q = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        for entry in q.get("queue_running") or []:
            if len(entry) > 1 and entry[1] == prompt_id:
                return None
        pending = q.get("queue_pending") or []
        for index, entry in enumerate(pending):
            if len(entry) > 1 and entry[1] == prompt_id:
                return index + 1
        return None

    async def cancel(self, prompt_id: str) -> None:
        """Cancel a job whether it is queued or already running.

        Two calls because they cover different states: /queue delete drops it if
        it is still pending, and /interrupt stops it if it is executing. The
        interrupt is targeted by prompt_id - ComfyUI checks it against the
        running prompt and does nothing if it does not match, so this can never
        kill a job that is not ours.
        """
        try:
            await self._http.post("/queue", json={"delete": [prompt_id]}, timeout=10.0)
        except httpx.HTTPError as exc:
            log.warning("queue delete failed for %s: %s", prompt_id, exc)
        try:
            await self._http.post("/interrupt", json={"prompt_id": prompt_id}, timeout=10.0)
        except httpx.HTTPError as exc:
            log.warning("interrupt failed for %s: %s", prompt_id, exc)

    async def free(self) -> None:
        """Ask ComfyUI to unload its models and release VRAM.

        Called once a job has finished so the card is clear for whatever runs
        next - Ollama for the idea helper, or a different ComfyUI workflow.
        Flux and LTX are different model sets, so switching between a picture
        and a video would otherwise mean both fighting for the same 16GB.

        The cost is that the next job reloads from disk. That is seconds, and
        it happens while they are still typing.
        """
        try:
            await self._http.post(
                "/free", json={"unload_models": True, "free_memory": True}, timeout=30.0
            )
            log.info("asked ComfyUI to release VRAM")
        except httpx.HTTPError as exc:
            log.warning("ComfyUI /free failed (harmless): %s", exc)

    async def upload_image(self, data: bytes, filename: str) -> str:
        """Upload into ComfyUI's *input* dir and return the LoadImage reference."""
        try:
            r = await self._http.post(
                "/upload/image",
                files={"image": (filename, data, "image/png")},
                data={"type": "input", "overwrite": "true"},
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise ComfyError(f"upload to ComfyUI failed: {exc}") from exc

        try:
            payload = r.json()
        except ValueError:
            raise ComfyError(f"ComfyUI's reply to the upload was not JSON: {r.text[:200]}")
        if not isinstance(payload, dict):
            payload = {}
        name = payload.get("name") or filename
        subfolder = payload.get("subfolder") or ""
        return f"{subfolder}/{name}" if subfolder else name

    def _view_params(self, ref: dict) -> dict:
        return {
            "filename": ref["filename"],
            "subfolder": ref.get("subfolder", ""),
            "type": ref.get("type", "output"),
        }

    async def fetch_view(self, ref: dict) -> bytes:
        try:
            r = await self._http.get("/view", params=self._view_params(ref))
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise ComfyError(f"could not fetch result from ComfyUI: {exc}") from exc
        return r.content

    async def stream_view(self, ref: dict) -> AsyncIterator[bytes]:
        async with self._http.stream("GET", "/view", params=self._view_params(ref)) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes(64 * 1024):
                yield chunk

    async def object_info(self) -> dict:
        """Everything ComfyUI can do, including which model files it can see.

        Big - a megabyte or so - so it is asked for once, at startup, to check
        the models the workflows name. Returns {} rather than raising: a check
        that cannot run must not stop the app from starting.
        """
        try:
            r = await self._http.get("/object_info", timeout=30.0)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return {}

    async def reachable(self) -> bool:
        try:
            r = await self._http.get("/system_stats", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False


def extract_outputs(history: dict) -> list[dict]:
    """Pull every saved file out of a history blob.

    SaveImage and SaveVideo use different keys (`images` vs `videos`), and that
    set grows with new node types, so scan every value for a list of dicts with
    a `filename` rather than hardcoding key names. Real saves land in `output`;
    previews land in `temp` and are ignored.
    """
    found = []
    for node_out in (history.get("outputs") or {}).values():
        if not isinstance(node_out, dict):
            continue
        for value in node_out.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and item.get("filename"):
                    found.append(item)
    preferred = [f for f in found if f.get("type", "output") == "output"]
    return preferred or found
