package com.shopmanager.mobile;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;

/** Durable, independent on-device database. The Windows database is never opened directly. */
public final class LocalDatabase extends SQLiteOpenHelper {
    private static final String DB_NAME = "shopmanager_local.db";
    public LocalDatabase(Context context) { super(context, DB_NAME, null, 1); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
        db.execSQL("CREATE TABLE customers (client_ref TEXT PRIMARY KEY, master_id INTEGER, name TEXT, phone TEXT, address TEXT)");
        db.execSQL("CREATE TABLE items (master_id INTEGER PRIMARY KEY, sku TEXT, name TEXT, qty INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE jobs (client_ref TEXT PRIMARY KEY, master_id INTEGER, order_code TEXT, customer_name TEXT, device TEXT, problem TEXT, status TEXT, labor INTEGER DEFAULT 0, discount INTEGER DEFAULT 0, paid INTEGER DEFAULT 0)");
        db.execSQL("CREATE TABLE pending_ops (ref TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL)");
    }
    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) { }

    public synchronized JSONObject loadObject(String key, String fallback) {
        try (Cursor c=getReadableDatabase().rawQuery("SELECT value FROM state WHERE key=?",new String[]{key})) {
            return c.moveToFirst()?new JSONObject(c.getString(0)):new JSONObject(fallback);
        } catch(Exception e) { return new JSONObject(); }
    }
    public synchronized JSONArray loadArray(String key, String fallback) {
        try (Cursor c=getReadableDatabase().rawQuery("SELECT value FROM state WHERE key=?",new String[]{key})) {
            return c.moveToFirst()?new JSONArray(c.getString(0)):new JSONArray(fallback);
        } catch(Exception e) { return new JSONArray(); }
    }
    public synchronized void saveState(String key, String value) {
        ContentValues v=new ContentValues(); v.put("key",key); v.put("value",value);
        getWritableDatabase().insertWithOnConflict("state",null,v,SQLiteDatabase.CONFLICT_REPLACE);
    }
    public synchronized void enqueue(JSONObject op) {
        String ref=op.optString("ref");
        ContentValues v=new ContentValues(); v.put("ref",ref); v.put("kind",op.optString("kind"));
        v.put("payload",op.toString()); v.put("created_at",System.currentTimeMillis());
        getWritableDatabase().insertWithOnConflict("pending_ops",null,v,SQLiteDatabase.CONFLICT_IGNORE);
        saveState("pending", appendPending(op));
    }
    private String appendPending(JSONObject op) {
        JSONArray a=loadArray("pending","[]");
        for(int i=0;i<a.length();i++) if(op.optString("ref").equals(a.optJSONObject(i).optString("ref"))) return a.toString();
        a.put(op); return a.toString();
    }
    public synchronized void replacePending(JSONArray pending) {
        SQLiteDatabase db=getWritableDatabase(); db.beginTransaction();
        try {
            db.delete("pending_ops",null,null);
            for(int i=0;i<pending.length();i++) {
                JSONObject op=pending.optJSONObject(i); if(op==null) continue;
                ContentValues v=new ContentValues(); v.put("ref",op.optString("ref"));
                v.put("kind",op.optString("kind")); v.put("payload",op.toString());
                v.put("created_at",System.currentTimeMillis());
                db.insertWithOnConflict("pending_ops",null,v,SQLiteDatabase.CONFLICT_REPLACE);
            }
            saveState("pending",pending.toString()); db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
    public synchronized void saveSnapshot(JSONObject snapshot) {
        SQLiteDatabase db=getWritableDatabase(); db.beginTransaction();
        try {
            saveState("snapshot",snapshot.toString());
            syncCustomers(db,snapshot.optJSONArray("customers"));
            syncItems(db,snapshot.optJSONArray("items"));
            syncJobs(db,snapshot.optJSONArray("jobs"));
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
    private void syncCustomers(SQLiteDatabase db, JSONArray a) {
        if(a==null)return;
        for(int i=0;i<a.length();i++){JSONObject o=a.optJSONObject(i);if(o==null)continue;
            ContentValues v=new ContentValues();v.put("client_ref",o.optString("client_ref","master-"+o.optLong("id")));
            v.put("master_id",o.optLong("id"));v.put("name",o.optString("name"));v.put("phone",o.optString("phone"));v.put("address",o.optString("address"));
            db.insertWithOnConflict("customers",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
    }
    private void syncItems(SQLiteDatabase db, JSONArray a) {
        if(a==null)return;
        for(int i=0;i<a.length();i++){JSONObject o=a.optJSONObject(i);if(o==null)continue;
            ContentValues v=new ContentValues();v.put("master_id",o.optLong("id"));v.put("sku",o.optString("sku"));v.put("name",o.optString("name"));v.put("qty",o.optInt("qty"));v.put("price",o.optLong("price"));
            db.insertWithOnConflict("items",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
    }
    private void syncJobs(SQLiteDatabase db, JSONArray a) {
        if(a==null)return;
        for(int i=0;i<a.length();i++){JSONObject o=a.optJSONObject(i);if(o==null)continue;
            ContentValues v=new ContentValues();String ref=o.optString("client_ref","master-"+o.optLong("id"));
            v.put("client_ref",ref);v.put("master_id",o.optLong("id"));v.put("order_code",o.optString("order_code"));v.put("customer_name",o.optString("customer_name"));v.put("device",o.optString("device"));v.put("problem",o.optString("problem"));v.put("status",o.optString("status"));v.put("labor",o.optLong("labor"));v.put("discount",o.optLong("discount"));v.put("paid",o.optLong("paid"));
            db.insertWithOnConflict("jobs",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
    }
}
