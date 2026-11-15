import json
import unittest
from unittest.mock import patch

import kaliia_license as licensing


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class KaliiaLicenseTests(unittest.TestCase):
    def _payload(self, **overrides):
        entitlement = {
            "product_id": "shopmanager",
            "status": "active",
            "can_write": True,
            "trial_available": False,
            "days_remaining": 45,
            "expires_at": "2026-12-30T12:00:00Z",
        }
        entitlement.update(overrides)
        return {"entitlement": entitlement, "checked_at": "2026-11-15T12:00:00Z"}

    def test_refresh_returns_active_entitlement(self):
        with patch.object(licensing.urllib.request, "urlopen",
                          return_value=_Response(self._payload())) as request:
            client = licensing.KaliiaLicenseClient(lambda: "verified-access-token")
            result = client.refresh()
        self.assertTrue(result.can_write)
        self.assertEqual(result.product_id, "shopmanager")
        args, kwargs = request.call_args
        sent = json.loads(args[0].data.decode("utf-8"))
        self.assertEqual(sent, {"action": "status", "product_id": "shopmanager"})
        self.assertEqual(args[0].get_header("Authorization"), "Bearer verified-access-token")
        self.assertEqual(kwargs["timeout"], 12)

    def test_start_trial_uses_server_action(self):
        with patch.object(licensing.urllib.request, "urlopen",
                          return_value=_Response(self._payload())) as request:
            licensing.KaliiaLicenseClient(lambda: "token").start_trial()
        self.assertEqual(json.loads(request.call_args.args[0].data),
                         {"action": "start_trial", "product_id": "shopmanager"})

    def test_missing_token_fails_closed(self):
        client = licensing.KaliiaLicenseClient(lambda: "")
        with self.assertRaises(licensing.EntitlementError):
            client.refresh()

    def test_wrong_product_is_rejected(self):
        with patch.object(licensing.urllib.request, "urlopen",
                          return_value=_Response(self._payload(product_id="maal"))):
            with self.assertRaises(licensing.EntitlementError):
                licensing.KaliiaLicenseClient(lambda: "token").refresh()

    def test_http_failure_fails_closed(self):
        error = licensing.urllib.error.HTTPError(
            "https://example.invalid", 401, "unauthorized", {}, None
        )
        with patch.object(licensing.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(licensing.EntitlementError):
                licensing.KaliiaLicenseClient(lambda: "token").refresh()

    def test_expired_entitlement_blocks_writes(self):
        entitlement = licensing.Entitlement.from_payload(
            self._payload(status="expired", can_write=False)["entitlement"]
        )
        with self.assertRaises(licensing.EntitlementError):
            licensing.require_write(entitlement)

    def test_unavailable_entitlement_blocks_writes(self):
        with self.assertRaises(licensing.EntitlementError):
            licensing.require_write(None)


if __name__ == "__main__":
    unittest.main()
