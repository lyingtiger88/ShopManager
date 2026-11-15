"""Kaliia Soft server-authoritative licensing client for ShopManager.

Pass a verified Supabase access token from the account/session layer.
Never store the service-role key or plain-text passwords in ShopManager's SQLite DB.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

SUPABASE_URL = "https://yztithydgdvydaktuxlw.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_UAKFYbxgWOCVRDDdv_0JLg_oIIiubmT"
PRODUCT_ID = "shopmanager"


@dataclass(frozen=True)
class Entitlement:
    product_id: str
    status: str
    can_write: bool
    trial_available: bool
    days_remaining: int
    expires_at: str | None = None
    checked_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "Entitlement":
        return cls(
            product_id=str(payload.get("product_id", "")),
            status=str(payload.get("status", "unknown")),
            can_write=payload.get("can_write") is True,
            trial_available=payload.get("trial_available") is True,
            days_remaining=max(0, int(payload.get("days_remaining") or 0)),
            expires_at=payload.get("expires_at"),
            checked_at=payload.get("checked_at"),
        )


class EntitlementError(RuntimeError):
    pass


class KaliiaLicenseClient:
    def __init__(self, access_token: Callable[[], str], timeout: float = 12):
        self._access_token = access_token
        self._timeout = timeout

    def _request(self, action: str) -> Entitlement:
        token = self._access_token()
        if not token:
            raise EntitlementError("برای بررسی اشتراک ابتدا وارد حساب تأییدشده شوید.")
        body = json.dumps({"action": action, "product_id": PRODUCT_ID}).encode("utf-8")
        request = urllib.request.Request(
            SUPABASE_URL + "/functions/v1/kaliia-entitlement",
            data=body,
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Authorization": "Bearer " + token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise EntitlementError(f"استعلام اشتراک ناموفق بود (HTTP {exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EntitlementError("ارتباط با سرویس اشتراک برقرار نشد.") from exc

        payload = result.get("entitlement")
        if not isinstance(payload, dict):
            raise EntitlementError("پاسخ سرویس اشتراک معتبر نیست.")
        entitlement = Entitlement.from_payload(payload)
        if entitlement.product_id != PRODUCT_ID:
            raise EntitlementError("شناسه محصول در پاسخ اشتراک مطابقت ندارد.")
        return entitlement

    def refresh(self) -> Entitlement:
        return self._request("status")

    def start_trial(self) -> Entitlement:
        return self._request("start_trial")


def require_write(entitlement: Entitlement | None) -> None:
    """Call before every data mutation; reads/exports/backups remain available."""
    if entitlement is None or not entitlement.can_write:
        raise EntitlementError("اشتراک پایان یافته یا تأیید نشده است؛ اطلاعات فقط قابل مشاهده هستند.")
