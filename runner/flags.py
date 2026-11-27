"""Flagsmith access behind small interfaces so tests mock it.

Verified against the installed `flagsmith` package (6.7.0, flagsmith/flagsmith.py):
  * Flagsmith(environment_key=..., enable_events=True)         constructor kwarg `enable_events`
  * client.get_experiment_flag(feature_name, identifier, traits)  -> Flag | DefaultFlag; records
    the exposure event itself, ONLY if the flag exists, is enabled and the identity is in a running
    experiment (flag.experiment.in_experiment) with flag.variant set. Raises ValueError if events
    are not enabled.
  * client.track_event(event, identifier=..., value=..., traits=..., metadata=...)
  * client.flush_events() -> None; returns once events were delivered/dropped/kept for retry.
    It does NOT report failure, so "flush confirmed" means "flush returned without raising".
  * client.close(timeout_seconds=...) sends buffered events and stops background work.
Flag fields: .enabled, .value, .variant (variant key), .experiment.in_experiment.
VERIFIED live (2026-11-26, Development env): for `onboarding_method` the control bucket returns
value='prompt', variant='control'; the skill bucket returns value='skill', variant='skill'. So `.value` is the
handoff variant ('prompt'|'skill'); `.variant` is 'control'|'skill' and must NOT be used for control.
`resolve_variant` checks value first, which is correct.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from runner.config import EXPERIMENT_FEATURE, EXPERIMENT_KEY_ENV, VARIANTS


@dataclass
class ExposureResult:
    variant: str  # "prompt" | "skill"
    in_experiment: bool
    raw_value: str | None = None
    raw_variant: str | None = None


class FlagsmithClient(Protocol):
    def get_exposure(self, trial_id: str, stack: str) -> ExposureResult: ...

    def send_event(self, event: str, trial_id: str, stack: str) -> None: ...

    def flush(self) -> None:
        """Flush buffered events; must raise if delivery cannot be confirmed."""

    def close(self) -> None: ...


def resolve_variant(value, variant) -> str | None:
    for cand in (value, variant):
        if isinstance(cand, str) and cand.strip().lower() in VARIANTS:
            return cand.strip().lower()
    return None


class SdkFlagsmithClient:
    """Real implementation. Imports the SDK lazily so tests/dry-run never need it."""

    def __init__(self, environment_key: str | None = None, api_url: str | None = None):
        key = environment_key or os.environ.get(EXPERIMENT_KEY_ENV)
        if not key:
            raise RuntimeError(f"{EXPERIMENT_KEY_ENV} is not set")
        from flagsmith import Flagsmith  # lazy import

        kwargs = {"environment_key": key, "enable_events": True}
        if api_url:
            kwargs["api_url"] = api_url
        self._fs = Flagsmith(**kwargs)

    def get_exposure(self, trial_id: str, stack: str) -> ExposureResult:
        flag = self._fs.get_experiment_flag(EXPERIMENT_FEATURE, trial_id, {"stack": stack})
        exp = getattr(flag, "experiment", None)
        in_exp = bool(exp and exp.in_experiment)
        value = getattr(flag, "value", None)
        variant = getattr(flag, "variant", None)
        resolved = resolve_variant(value, variant)
        if not in_exp or resolved is None:
            raise RuntimeError(
                f"identity not enrolled in a running experiment or unknown variant "
                f"(in_experiment={in_exp}, value={value!r}, variant={variant!r})"
            )
        return ExposureResult(resolved, in_exp, str(value), None if variant is None else str(variant))

    def send_event(self, event: str, trial_id: str, stack: str) -> None:
        self._fs.track_event(event, identifier=trial_id, traits={"stack": stack})

    def flush(self) -> None:
        self._fs.flush_events()

    def close(self) -> None:
        self._fs.close()


class RolloutFlagsmithClient:
    """ROLLOUT mode (after the experiment ended): read the variant with a plain flag read and send
    NOTHING. Verified against flagsmith 6.7.0: `Flagsmith.get_identity_flags(identifier, traits,
    transient=...)` returns a `Flags` object whose `.get_flag(feature_name)` gives the flag with `.value`.
    Events are disabled (`enable_events=False`), so no exposure event is recorded either; the flag read is
    transient so no identity is persisted. `send_event`, `flush` and `close` never touch the network."""

    def __init__(self, environment_key: str | None = None, api_url: str | None = None):
        key = environment_key or os.environ.get(EXPERIMENT_KEY_ENV)
        if not key:
            raise RuntimeError(f"{EXPERIMENT_KEY_ENV} is not set")
        from flagsmith import Flagsmith  # lazy import

        kwargs = {"environment_key": key, "enable_events": False}
        if api_url:
            kwargs["api_url"] = api_url
        self._fs = Flagsmith(**kwargs)

    def get_exposure(self, trial_id: str, stack: str) -> ExposureResult:
        flags = self._fs.get_identity_flags(trial_id, {"stack": stack}, transient=True)
        flag = flags.get_flag(EXPERIMENT_FEATURE)
        value = getattr(flag, "value", None)
        variant = getattr(flag, "variant", None)
        resolved = resolve_variant(value, variant)
        if resolved is None:
            raise RuntimeError(f"rollout flag read returned an unknown variant (value={value!r}, variant={variant!r})")
        return ExposureResult(resolved, False, str(value), None if variant is None else str(variant))

    def send_event(self, event: str, trial_id: str, stack: str) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class SandboxCleaner(Protocol):
    def delete_flag(self, flag_name: str) -> str:
        """Delete the flag from the SANDBOX project only. Returns a status string.
        Optional additive method (record-only): `inspect_flag(name) -> {"exists", "created_date"} | None`."""


class NoopCleaner:
    def delete_flag(self, flag_name: str) -> str:
        return "skipped"

    def inspect_flag(self, flag_name: str) -> dict | None:
        return None


class AdminApiCleaner:
    """Deletes a feature from the sandbox project via the Flagsmith Admin API.

    UNVERIFIED (Phase 0 must confirm): base URL, `Authorization: Api-Key <key>` scheme for an
    organisation API key, `GET /api/v1/projects/{id}/features/?search=` list response shape
    ({"results": [{"id", "name"}]}), and `DELETE /api/v1/projects/{id}/features/{feature_id}/`.
    Only uses FS_SANDBOX_ADMIN_KEY / FS_SANDBOX_PROJECT_ID; never receives the experiment key.
    """

    def __init__(self, admin_key: str, project_id: str, base_url: str = "https://api.flagsmith.com"):
        self.admin_key, self.project_id, self.base = admin_key, project_id, base_url.rstrip("/")

    def _req(self, method: str, path: str):
        req = urllib.request.Request(
            f"{self.base}{path}",
            method=method,
            headers={"Authorization": f"Api-Key {self.admin_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return json.loads(body) if body else None

    def inspect_flag(self, flag_name: str) -> dict | None:
        """RECORD-ONLY, read-only: {"exists": bool, "created_date": str | None} for the exact-name feature, or
        None if it could not be determined. `created_date` is the feature's `created_date` field (assumed from
        the Admin API feature object; None when absent). Never raises, never deletes."""
        q = urllib.parse.urlencode({"search": flag_name})
        try:
            data = self._req("GET", f"/api/v1/projects/{self.project_id}/features/?{q}")
            matches = [f for f in (data or {}).get("results", []) if f.get("name") == flag_name]
        except (urllib.error.URLError, OSError, ValueError, KeyError, AttributeError):
            return None
        if not matches:
            return {"exists": False, "created_date": None}
        dates = [str(f["created_date"]) for f in matches if f.get("created_date")]
        return {"exists": True, "created_date": min(dates) if dates else None}

    def delete_flag(self, flag_name: str) -> str:
        q = urllib.parse.urlencode({"search": flag_name})
        try:
            data = self._req("GET", f"/api/v1/projects/{self.project_id}/features/?{q}")
            matches = [f for f in (data or {}).get("results", []) if f.get("name") == flag_name]
            if not matches:
                return "not_found"
            for f in matches:
                self._req("DELETE", f"/api/v1/projects/{self.project_id}/features/{f['id']}/")
            return "deleted"
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return f"error: {type(e).__name__}: {e}"


def cleaner_from_env(env=None) -> SandboxCleaner:
    env = os.environ if env is None else env
    key, pid = env.get("FS_SANDBOX_ADMIN_KEY"), env.get("FS_SANDBOX_PROJECT_ID")
    if key and pid:
        return AdminApiCleaner(key, pid)
    return NoopCleaner()
