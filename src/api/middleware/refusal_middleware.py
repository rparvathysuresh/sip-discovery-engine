"""
Refusal and compliance middleware for the FastAPI backend.

Acts as a catch-all guardrail inspecting outgoing API responses to ensure
no fund recommendations, stock tips, or FOMO framing escape to the client.
"""

from __future__ import annotations

import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.query.guardrails import GuardrailsChecker
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RefusalMiddleware(BaseHTTPMiddleware):
    """
    Middleware that inspects and sanitizes outgoing responses for compliance violations.
    """

    def __init__(self, app, guardrails: Optional[GuardrailsChecker] = None):
        super().__init__(app)
        self.guardrails = guardrails or GuardrailsChecker()

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only inspect JSON responses from API endpoints
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read response body
        body = [section async for section in response.body_iterator]
        body_bytes = b"".join(body)

        try:
            data = json.loads(body_bytes.decode("utf-8"))
            modified = False

            # Check if payload contains an answer field (e.g. from /chat)
            if isinstance(data, dict):
                if "answer" in data and isinstance(data["answer"], str):
                    clean_ans = self.guardrails.sanitize_response(data["answer"])
                    if clean_ans != data["answer"]:
                        data["answer"] = clean_ans
                        modified = True

                if "refusal" in data and data.get("refusal") is True:
                    modified = True

            if modified:
                new_body = json.dumps(data).encode("utf-8")
                headers = dict(response.headers)
                headers["content-length"] = str(len(new_body))
                return Response(content=new_body, status_code=response.status_code, headers=headers, media_type="application/json")

        except Exception as e:
            logger.debug("RefusalMiddleware pass-through: %s", e)

        # Return original body if not modified
        return Response(content=body_bytes, status_code=response.status_code, headers=dict(response.headers), media_type=content_type)

