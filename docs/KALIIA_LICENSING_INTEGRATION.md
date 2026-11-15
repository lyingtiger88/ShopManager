# Kaliia Soft licensing integration — ShopManager

Product ID: `shopmanager`. Platforms: Windows Python/Tkinter + SQLite and native Android Java/SQLite.

## Central entitlement API
Supabase project `yztithydgdvydaktuxlw`; POST `https://yztithydgdvydaktuxlw.supabase.co/functions/v1/kaliia-entitlement` with `{"action":"status","product_id":"shopmanager"}` or `{"action":"start_trial","product_id":"shopmanager"}`. Require verified Supabase Auth access token and publishable key. Never embed service-role credentials.

## Required client work
1. Add account sign-in/registration and verified email flow. The current ShopManager README describes a local-first single-user Windows app and Android companion; no central account login is documented. Do not issue a server trial to anonymous local installs.
2. Persist refresh/access tokens in Windows Credential Manager/DPAPI and Android Keystore-backed storage. Do not store plaintext credentials in SQLite.
3. Add a shared entitlement model: product ID, status, can_write, expiry, days_remaining, server_checked_at.
4. Windows: inject `LicenseGate` into database/service write paths. Guard customer/product create/update/delete, stock receipts and adjustments, repair/work-order edits, parts consumption, invoice/payment changes, and sync-server writes. Keep all reads, printing, exports and backup available.
5. Android: mirror the same gate in repository/DAO write paths and UI actions. Offline queue must refuse new writes after expiry; retain queued historical data and do not silently discard it.
6. Check entitlement at login/startup/resume and every 12 hours online. Use a bounded offline grace period only after the business policy is explicitly approved; default fail-closed for writes when no valid entitlement is available.
7. Approved manual payment changes the central `shopmanager` license. Refreshing entitlement restores writes without reinstalling or touching SQLite data.

## Commercial choices required
Decide if one ShopManager subscription covers one store, multiple branches, or each device. Current architecture describes Windows as the local master and Android as a companion synced over a private LAN; licensing should bind to the store/account, not accidentally create a separate trial for every companion device.

## Acceptance tests
45-day boundary; one trial per account/product; Windows + Android share one entitlement; expired read-only across every mutation path; offline/sync queue behavior; paid renewal; receipt approval; backup/export preserved; SQLite database unchanged by licensing; no privileged keys in client builds.
