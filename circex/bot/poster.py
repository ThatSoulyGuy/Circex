"""Turn SkyPortalActions into HTTP writes — or, by default, print them (dry-run).

Live posting requires BOTH an explicit `live=True` and a `token`; otherwise the
poster only renders the payloads it would send. This guards an outward-facing,
hard-to-reverse action (writing to a shared SkyPortal instance).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from circex.bot.skyportal_map import SkyPortalActions

log = structlog.get_logger(__name__)


@dataclass
class SkyPortalPoster:
    """Posts (or dry-runs) SkyPortalActions against a SkyPortal instance."""

    base_url: str = "https://skyportal.example/api"
    token: str | None = None
    live: bool = False
    timeout: float = 30.0
    continue_on_error: bool = False  # log + continue instead of raising (unattended use)

    def post(self, actions: SkyPortalActions) -> list[dict[str, Any]]:
        """Apply the actions. Returns the list of {method, path, payload} planned.

        In dry-run (default) nothing is sent. With `live=True` and a token, each
        planned request is executed in order: source upsert, photometry,
        redshift patch, comments.
        """
        plan = self._plan(actions)
        if not (self.live and self.token):
            for req in plan:
                log.info(
                    "skyportal_dryrun",
                    method=req["method"],
                    path=req["path"],
                    payload=req["payload"],
                )
            return plan
        self._execute(plan)
        return plan

    def _plan(self, actions: SkyPortalActions) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        if actions.source is not None:
            plan.append(
                {"method": "POST", "path": "/sources", "payload": actions.source.to_payload()}
            )
            obj_id = actions.source.id
            for point in actions.photometry:
                plan.append(
                    {"method": "POST", "path": "/photometry", "payload": point.to_payload()}
                )
            if actions.redshift is not None:
                z, z_err = actions.redshift
                plan.append(
                    {
                        "method": "PATCH",
                        "path": f"/sources/{obj_id}",
                        "payload": {"redshift": z, "redshift_error": z_err},
                    }
                )
            for text in actions.comments:
                plan.append(
                    {
                        "method": "POST",
                        "path": f"/sources/{obj_id}/comments",
                        "payload": {"text": text},
                    }
                )
        return plan

    def _execute(self, plan: list[dict[str, Any]]) -> None:
        import requests  # local import: only needed for live posting

        headers = {"Authorization": f"token {self.token}", "Content-Type": "application/json"}
        for req in plan:
            url = self.base_url.rstrip("/") + req["path"]
            try:
                resp = requests.request(
                    req["method"],
                    url,
                    headers=headers,
                    data=json.dumps(req["payload"]),
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                # SkyPortal also signals failure as HTTP 200 with status="error".
                body = resp.json()
                if isinstance(body, dict) and body.get("status") == "error":
                    raise RuntimeError(str(body.get("message", "skyportal error"))[:200])
            except Exception as exc:
                if not self.continue_on_error:
                    raise
                # Unattended: one bad request (e.g. a filter the instrument lacks)
                # must not kill the stream.
                log.warning(
                    "skyportal_post_failed",
                    method=req["method"],
                    path=req["path"],
                    error=str(exc)[:200],
                )
                continue
            log.info(
                "skyportal_posted",
                method=req["method"],
                path=req["path"],
                status=resp.status_code,
            )


def render_plan(plan: list[dict[str, Any]]) -> str:
    """Human-readable dump of a planned request list (for CLI dry-run output)."""
    lines: list[str] = []
    for req in plan:
        lines.append(f"{req['method']} {req['path']}")
        lines.append("  " + json.dumps(req["payload"], ensure_ascii=False))
    return "\n".join(lines)
