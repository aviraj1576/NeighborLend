"""Gemini REST provider. Uses only the standard library (urllib) so the host
project does not need to add or reconcile any SDK dependency."""
import asyncio
import base64
import json
import time
import urllib.error
import urllib.request

from ..exceptions import ProviderError
from ..prompts import SYSTEM_PROMPT, user_text
from ..schemas import ViewResult
from .base import parse_view_result

_RETRY_CODES = (429, 500, 502, 503, 504)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash",
        timeout: float = 60.0,
        max_retries: int = 4,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        if not api_key:
            raise ProviderError("DAMAGE_GEMINI_API_KEY is not set.")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")

    def _payload(self, view, item_class, before, before_mime, after, after_mime) -> dict:
        def img(data: bytes, mime: str) -> dict:
            return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}}

        return {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_text(view, item_class or "")},
                        {"text": "BEFORE:"},
                        img(before, before_mime),
                        {"text": "AFTER:"},
                        img(after, after_mime),
                    ],
                }
            ],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }

    @staticmethod
    def _delay(exc, attempt: int) -> float:
        """Honor Retry-After when sent; otherwise back off harder on 429."""
        header = exc.headers.get("Retry-After") if exc.headers else None
        try:
            if header:
                return min(float(header), 30.0)
        except ValueError:
            pass
        base = 4.0 if exc.code == 429 else 1.0
        return min(base * (2 ** attempt), 30.0)

    @staticmethod
    def _error_detail(exc) -> str:
        """Short reason from Google's error body (it never contains the key)."""
        try:
            raw = exc.read().decode("utf-8", "replace")
            return str(json.loads(raw).get("error", {}).get("message", ""))[:200]
        except Exception:
            return ""

    def _call(self, payload: dict) -> str:
        url = "%s/models/%s:generateContent" % (self.base_url, self.model)
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._text(data)
            except urllib.error.HTTPError as exc:
                detail = self._error_detail(exc)
                delay = self._delay(exc, attempt)
                code = exc.code
                exc.close()
                if code in _RETRY_CODES and attempt < self.max_retries:
                    time.sleep(delay)
                    continue
                raise ProviderError(
                    "Gemini API returned HTTP %d%s." % (code, (": " + detail) if detail else "")
                )
            except ValueError:
                raise ProviderError("Gemini returned a response that is not valid JSON.")
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError("Could not reach the Gemini API.")
        raise ProviderError("Gemini call failed.")

    @staticmethod
    def _text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError("Gemini returned no answer (%s)." % reason)
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if not text.strip():
            raise ProviderError("Gemini returned an empty answer (%s)." % candidates[0].get("finishReason", "?"))
        return text

    async def compare(self, *, view, item_class, before, before_mime, after, after_mime) -> ViewResult:
        payload = self._payload(view, item_class, before, before_mime, after, after_mime)
        text = await asyncio.to_thread(self._call, payload)
        return parse_view_result(view, text)