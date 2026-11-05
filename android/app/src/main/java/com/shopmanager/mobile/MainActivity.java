package com.shopmanager.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private SharedPreferences prefs;
    private LinearLayout root, body;
    private TextView status;
    private int navy=Color.rgb(13,27,49), blue=Color.rgb(24,91,190), pale=Color.rgb(241,245,251), ink=Color.rgb(25,39,58);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private JSONObject snapshot = new JSONObject();
    private JSONArray pending = new JSONArray();
    private JSONObject deviceCatalog = new JSONObject();
    private String[] faults = {"روشن نمی‌شود","شارژ نمی‌شود","باتری ضعیف","شکستگی نمایشگر",
            "مشکل تاچ","خرابی دوربین","مشکل صدا/میکروفون","آنتن‌دهی","آب‌خوردگی",
            "خرابی دکمه‌ها","مشکل نرم‌افزاری","خرابی سوکت شارژ","شکستگی بدنه","سایر"};

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("shopmanager_sync", MODE_PRIVATE);
        try { pending = new JSONArray(prefs.getString("pending", "[]")); } catch(Exception ignored) {}
        try { snapshot = new JSONObject(prefs.getString("snapshot", "{}")); } catch(Exception ignored) {}
        try (InputStream in=getAssets().open("device_catalog.json")) {
            ByteArrayOutputStream out=new ByteArrayOutputStream(); byte[] buf=new byte[4096]; int n;
            while((n=in.read(buf))!=-1)out.write(buf,0,n);
            deviceCatalog=new JSONObject(out.toString("UTF-8"));
        } catch(Exception ignored) {}
        getWindow().setStatusBarColor(navy);
        getWindow().setNavigationBarColor(navy);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(14,12,14,8);
        root.setBackgroundColor(pale);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        setContentView(root);
        LinearLayout header=new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(android.view.Gravity.CENTER_VERTICAL);
        header.setPadding(14,12,14,12);
        GradientDrawable headerBg=new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{Color.rgb(20,105,225),Color.rgb(13,53,135)});
        headerBg.setCornerRadius(18*getResources().getDisplayMetrics().density);
        header.setBackground(headerBg);
        root.addView(header,new LinearLayout.LayoutParams(-1,-2));
        TextView gear=text("⚙");
        gear.setTextColor(Color.WHITE);gear.setTextSize(27);
        header.addView(gear);
        LinearLayout brandBlock=new LinearLayout(this);
        brandBlock.setOrientation(LinearLayout.VERTICAL);
        brandBlock.setGravity(android.view.Gravity.CENTER);
        header.addView(brandBlock,new LinearLayout.LayoutParams(0,-2,1));
        TextView role=text("مدیریت فروشگاه و تعمیرگاه");
        role.setTextColor(Color.rgb(224,237,255));role.setTextSize(12);
        role.setGravity(android.view.Gravity.CENTER);
        TextView brand=text("ShopManager");
        brand.setTextColor(Color.WHITE);brand.setTextSize(22);brand.setTypeface(null,Typeface.BOLD);
        brand.setGravity(android.view.Gravity.CENTER);
        brandBlock.addView(role);brandBlock.addView(brand);
        TextView shop=text("🏪");shop.setTextSize(27);header.addView(shop);
        status=text("");status.setTextColor(ink);status.setTextSize(12);root.addView(status);
        ScrollView scroll=new ScrollView(this);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(2,8,2,12);scroll.addView(body);
        LinearLayout nav=new LinearLayout(this);nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setPadding(4,6,4,6);nav.setBackground(round(Color.WHITE,18));
        root.addView(nav,new LinearLayout.LayoutParams(-1,-2));
        tab(nav,"خانه",()->homePage());tab(nav,"پذیرش",()->intakePage());
        tab(nav,"پرونده‌ها",()->jobsPage());tab(nav,"انبار",()->inventoryPage());
        tab(nav,"اتصال",()->connectionPage());
        status();
        homePage();
        if(!url().isEmpty() && !key().isEmpty()) synchronize();
    }
    private TextView text(String content) {
        TextView t = new TextView(this);
        t.setText(content); t.setTextSize(14); t.setTextColor(ink); t.setPadding(8,9,8,9);
        t.setTextDirection(View.TEXT_DIRECTION_RTL);
        return t;
    }
    private EditText field(String hint, String initial) {
        EditText e = new EditText(this);
        e.setSingleLine(true); e.setTextSize(15); e.setHint(hint);
        e.setText(initial); e.setTextDirection(View.TEXT_DIRECTION_RTL);
        body.addView(e, new LinearLayout.LayoutParams(-1,-2));
        return e;
    }
    private void tab(LinearLayout container, String name, Runnable action) {
        String glyph="خانه".equals(name)?"⌂":"پذیرش".equals(name)?"🔧":"پرونده‌ها".equals(name)?"▤":"انبار".equals(name)?"▣":"اتصال".equals(name)?"⚙":"•";
        LinearLayout item=new LinearLayout(this);
        item.setOrientation(LinearLayout.VERTICAL);
        item.setGravity(android.view.Gravity.CENTER);
        item.setPadding(2,4,2,4);
        TextView icon=text(glyph);icon.setTextSize(19);icon.setTextColor(blue);icon.setGravity(android.view.Gravity.CENTER);
        TextView label=text(name);label.setTextSize(10);label.setTextColor(ink);label.setGravity(android.view.Gravity.CENTER);
        item.addView(icon);item.addView(label);
        container.addView(item,new LinearLayout.LayoutParams(0,-2,1));
        item.setOnClickListener(v -> action.run());
    }
    private void iconTile(LinearLayout row,String glyph,String label,int color,Runnable run) {
        LinearLayout tile=new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(android.view.Gravity.CENTER);
        tile.setPadding(4,10,4,10);
        tile.setBackground(round(Color.WHITE,15));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,112,1);
        p.setMargins(4,4,4,4);
        row.addView(tile,p);
        TextView icon=text(glyph);icon.setTextSize(27);icon.setTextColor(color);icon.setGravity(android.view.Gravity.CENTER);
        TextView caption=text(label);caption.setTextSize(12);caption.setTypeface(null,Typeface.BOLD);caption.setGravity(android.view.Gravity.CENTER);
        tile.addView(icon);tile.addView(caption);
        tile.setElevation(2*getResources().getDisplayMetrics().density);
        tile.setOnClickListener(v->run.run());
    }
    private void quickRow(String a,String b,String c) {
        LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.HORIZONTAL);
        body.addView(row);
        if("فاکتور".equals(a)) iconTile(row,"▤",a,Color.rgb(125,65,210),this::jobsPage);
        else if("ثبت تعمیر".equals(a)) iconTile(row,"🔧",a,blue,this::intakePage);
        else iconTile(row,"▣",a,Color.rgb(25,155,100),this::inventoryPage);
        if("مشتریان".equals(b)) iconTile(row,"♟",b,Color.rgb(230,140,20),this::customersPage);
        else if("گزارش‌ها".equals(b)) iconTile(row,"▥",b,Color.rgb(225,65,95),this::jobsPage);
        else iconTile(row,"⚙",b,Color.rgb(95,115,160),this::connectionPage);
        if("تنظیمات".equals(c)) iconTile(row,"☷",c,Color.rgb(95,115,160),this::connectionPage);
        else iconTile(row,"♟",c,Color.rgb(125,65,210),this::customersPage);
    }
    private void action(String name, Runnable run) {
        Button b = new Button(this); b.setText(name); b.setTextColor(Color.WHITE); b.setAllCaps(false); b.setBackground(round(blue,14)); b.setPadding(12,10,12,10); LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,-2);bp.setMargins(3,6,3,6);body.addView(b,bp);
        b.setOnClickListener(v -> run.run());
    }
    private void reset(String heading) {
        body.removeAllViews();
        TextView t=text(heading); t.setTextSize(19); t.setTextColor(navy); t.setTypeface(null, Typeface.BOLD);
        body.addView(t);
    }
    private void status() {
        JSONArray knownJobs = snapshot.optJSONArray("jobs");
        status.setText("در انتظار ارسال: " + pending.length() +
                " | اطلاعات دریافت‌شده: " + (knownJobs == null ? 0 : knownJobs.length()) + " پرونده");
    }
    private void save() {
        prefs.edit().putString("pending",pending.toString())
                .putString("snapshot",snapshot.toString()).apply();
        status();
    }
    private void toast(String text) { Toast.makeText(this,text,Toast.LENGTH_LONG).show(); }
    private String url() { return prefs.getString("url","").trim().replaceAll("/+$",""); }
    private String key() { return prefs.getString("key","").trim(); }

    private GradientDrawable round(int color,int radiusDp) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);
        d.setCornerRadius(radiusDp*getResources().getDisplayMetrics().density);return d;
    }
    private void metricCard(String title,String value,int color,String glyph) {
        LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(android.view.Gravity.CENTER_VERTICAL);card.setPadding(7,9,7,9);
        card.setBackground(round(Color.WHITE,16));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,92,1);p.setMargins(3,3,3,3);
        TextView badge=text(glyph);badge.setTextSize(23);badge.setTextColor(Color.WHITE);
        badge.setGravity(android.view.Gravity.CENTER);badge.setBackground(round(color,40));
        LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(48,48);card.addView(badge,bp);
        LinearLayout labels=new LinearLayout(this);labels.setOrientation(LinearLayout.VERTICAL);
        labels.setGravity(android.view.Gravity.CENTER);
        TextView v=text(value);v.setTextSize(22);v.setTextColor(ink);v.setTypeface(null,Typeface.BOLD);
        TextView t=text(title);t.setTextSize(10);t.setGravity(android.view.Gravity.CENTER);
        labels.addView(v);labels.addView(t);card.addView(labels,new LinearLayout.LayoutParams(0,-2,1));
        body.addView(card,p);card.setElevation(2*getResources().getDisplayMetrics().density);
    }
    private void homePage() {
        reset("داشبورد مدیریت تعمیرگاه");
        LinearLayout metrics1=new LinearLayout(this);metrics1.setOrientation(LinearLayout.HORIZONTAL);body.addView(metrics1);
        JSONArray jobs=snapshot.optJSONArray("jobs"), people=snapshot.optJSONArray("customers"), items=snapshot.optJSONArray("items");
        metricCard("تعمیرات جاری",String.valueOf(jobs==null?0:jobs.length()),blue,"🔧");
        metricCard("فروش امروز","۰",Color.rgb(25,155,100),"🛒");
        LinearLayout metrics2=new LinearLayout(this);metrics2.setOrientation(LinearLayout.HORIZONTAL);body.addView(metrics2);
        metricCard("مشتریان",String.valueOf(people==null?0:people.length()),Color.rgb(125,65,210),"♟");
        metricCard("کالا در انبار",String.valueOf(items==null?0:items.length()),Color.rgb(230,145,20),"▣");
        TextView quick=text("دسترسی سریع");quick.setTypeface(null,Typeface.BOLD);quick.setTextSize(17);body.addView(quick);
        quickRow("فاکتور","ثبت تعمیر","کالاها");
        quickRow("مشتریان","گزارش‌ها","تنظیمات");
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);
        info.setPadding(12,10,12,10);info.setBackground(round(Color.WHITE,14));
        TextView infoTitle=text("◷  تازه‌ترین فعالیت‌ها");infoTitle.setTypeface(null,Typeface.BOLD);infoTitle.setTextSize(16);info.addView(infoTitle);
        info.addView(text("•  در انتظار ارسال: "+pending.length()+" مورد"));
        info.addView(text("•  آخرین همگام‌سازی: "+(snapshot.length()==0?"هنوز انجام نشده":"اطلاعات دریافت شده")));
        body.addView(info);
        TextView recent=text("آخرین پرونده‌ها");recent.setTextSize(16);recent.setTypeface(null,Typeface.BOLD);body.addView(recent);
        if(jobs!=null)for(int i=Math.max(0,jobs.length()-4);i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j!=null){
                LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);
                card.setPadding(10,8,10,8);card.setBackground(round(Color.WHITE,12));
                card.addView(text("🔧  "+j.optString("order_code")+"  |  "+j.optString("customer_name")));
                card.addView(text(j.optString("device")+"  |  "+j.optString("status")));body.addView(card);
            }
        }
        action("اتصال و همگام‌سازی با نسخه ویندوز",this::connectionPage);
    }

