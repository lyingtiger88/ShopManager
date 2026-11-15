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

## Canonical multi-device architecture — one master, one database

This is the required operating model for ShopManager. It overrides any design that creates an independent writable database on each workstation or handset.

- **One store has one authoritative master device and one authoritative database.** The master hosts the SQLite database and ShopManager LAN service. All records and stock balances belong to this database.
- **Every other device is a paired subordinate client.** Windows/Android clients connect to the master over the local network using a per-device pairing identity and authenticated session. They do not create a second authoritative store database.
- **All writes are committed by the master.** Customer, product, stock receipt/adjustment, repair order, invoice, payment, expense and inventory operations are submitted to the master API. The master validates permissions, business rules, stock availability and idempotency, then commits the transaction.
- **One shared live view.** Clients fetch current data from the master and refresh after accepted writes or server change notifications. IDs, invoice numbers, stock balances and timestamps are generated or confirmed by the master.
- **Offline policy.** If a subordinate loses connection, it clearly shows disconnected/read-only state. It may retain a temporary cache for viewing, but must not present offline edits as committed or silently diverge from the master database. A future outbox must use unique idempotency keys and visible pending/accepted/rejected states. Stock consumption, payments and conflict-sensitive operations require a live master response.
- **Master availability and backup.** The master must be running and reachable for live operation. It owns scheduled backups and restore. A subordinate must never automatically promote itself or create a competing database when the master is unavailable. Master replacement is an explicit restore/migration procedure.
- **Pairing and security.** Pairing is administrator-controlled; each subordinate has a revocable device identity. Network traffic must use authenticated encrypted transport (TLS), and the service must be limited to private LAN/VPN access. The current plain HTTP shared-token implementation is a prototype, not production-ready.
- **Licensing scope.** The subscription/trial belongs to the store/master identity, not each paired device. Paired clients inherit that store's entitlement. Adding a subordinate must not create another trial or consume another subscription unless a device limit is explicitly introduced as a commercial rule.
- **Master failure and recovery.** Subordinates keep only a non-authoritative cache and pairing metadata. Restore a verified master backup onto a replacement master, then re-pair clients. Never automatically merge two independently writable databases.

### Existing implementation gap

The current `sync_server.py` is a limited prototype: its snapshot returns capped lists of customers, items and jobs; its operation endpoint accepts only customer/job intake and explicitly rejects stock consumption. It is not yet a complete shared-database API for all ShopManager modules. Before expanding licensing enforcement, migrate every subordinate operation to the master service and ensure there is exactly one write authority. Do not treat the current partial snapshot/operation endpoints as full multi-device synchronization.

### Multi-device acceptance criteria

1. A store is initialized once on the master; other devices join by pairing.
2. Every paired device sees the same customers, products, stock, orders, payments and reports.
3. A write from any subordinate is committed to the master and appears on all other clients.
4. Concurrent stock changes are serialized and validated by the master; negative or oversold stock is rejected atomically.
5. Duplicate network retries do not create duplicate customers, orders, payments or stock movements.
6. When the master is offline, subordinate clients show the outage and cannot claim a write succeeded.
7. Revoking one paired device blocks its access without affecting other clients or the database.
8. One store entitlement covers the master and paired clients; expiry applies consistently and preserves stored data.
9. Backups are generated from the authoritative master database and can be restored without data loss.
