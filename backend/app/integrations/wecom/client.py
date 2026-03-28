import json
from typing import Any
from urllib import request

from .errors import WeComAPIError


class WeComClient:
    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
        parsed = json.loads(data)
        errcode = int(parsed.get("errcode", 0))
        if errcode != 0:
            raise WeComAPIError(errcode, str(parsed.get("errmsg", "unknown")))
        return parsed

    def send_text(
        self,
        webhook_url: str,
        text: str,
        mentioned_list: list[str] | None = None,
        mentioned_mobile_list: list[str] | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise ValueError("webhook_url 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        payload = {
            "msgtype": "text",
            "text": {
                "content": text,
                "mentioned_list": mentioned_list or [],
                "mentioned_mobile_list": mentioned_mobile_list or [],
            },
        }
        self._post_json(webhook_url, payload)
