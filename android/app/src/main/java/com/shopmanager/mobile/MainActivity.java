package com.shopmanager.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.pdf.PdfDocument;
import android.os.Environment;
import android.text.Spannable;
import android.text.SpannableStringBuilder;
import android.text.style.StyleSpan;
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
import java.security.MessageDigest;
import java.security.SecureRandom;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class MainActivity extends Activity {
    private SharedPreferences prefs;
    private LinearLayout root, body;
    private TextView status;
    private int navy=Color.rgb(4,18,34), blue=Color.rgb(0,126,255), pale=Color.rgb(4,18,34), ink=Color.rgb(243,247,255);
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
        getWindow().setStatusBarColor(Color.rgb(3,13,26));
        getWindow().setNavigationBarColor(Color.rgb(3,13,26));
        root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(12),dp(8),dp(12),dp(8));
        root.setBackgroundColor(pale);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        setContentView(root);
        LinearLayout header=new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(android.view.Gravity.CENTER_VERTICAL);
        header.setPadding(dp(12),dp(10),dp(12),dp(10));
        header.setBackground(gradient(new int[]{Color.rgb(10,38,64),Color.rgb(4,18,34)},20));
        root.addView(header,new LinearLayout.LayoutParams(-1,dp(78)));
        LinearLayout brand=new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        TextView product=text("⚙  ShopManager");
        product.setTextColor(Color.rgb(250,202,87));product.setTypeface(null,Typeface.BOLD);
        product.setTextSize(23);product.setPadding(0,0,0,0);
        brand.addView(product);
        TextView tagline=text("مدیریت هوشمند فروشگاه و تعمیرگاه");
        tagline.setTextSize(11);tagline.setTextColor(Color.rgb(171,202,230));
        tagline.setPadding(0,0,0,0);brand.addView(tagline);
        TextView menu=text("☰");
        menu.setTextSize(26);menu.setTextColor(Color.WHITE);menu.setGravity(android.view.Gravity.CENTER);
        header.addView(menu,new LinearLayout.LayoutParams(dp(44),dp(44)));
        menu.setOnClickListener(v->showMoreMenu());
        status=text("");status.setTextSize(11);status.setTextColor(Color.rgb(145,180,212));
        status.setPadding(dp(7),dp(8),dp(7),dp(8));root.addView(status);
        ScrollView scroll=new ScrollView(this);
        scroll.setFillViewport(false);scroll.setVerticalScrollBarEnabled(false);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(1),dp(6),dp(1),dp(22));scroll.addView(body);
        LinearLayout nav=new LinearLayout(this);nav.setGravity(android.view.Gravity.CENTER_VERTICAL);
        nav.setOrientation(LinearLayout.HORIZONTAL);nav.setPadding(dp(5),dp(5),dp(5),dp(5));
        nav.setBackground(gradient(new int[]{Color.rgb(12,42,68),Color.rgb(4,20,37)},20));
        LinearLayout.LayoutParams np=new LinearLayout.LayoutParams(-1,dp(72));np.topMargin=dp(7);root.addView(nav,np);
        tab(nav,"خانه",this::homePage);tab(nav,"پذیرش",this::intakePage);
        tab(nav,"پرونده‌ها",this::jobsPage);tab(nav,"مشتریان",this::customersPage);
        tab(nav,"بیشتر",this::showMoreMenu);
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
        e.setPadding(14,12,14,12);
        e.setTextColor(Color.WHITE);e.setHintTextColor(Color.rgb(151,177,202));
        e.setBackground(round(Color.rgb(15,43,68),12));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);
        params.setMargins(3,4,3,4);
        body.addView(e, params);
        return e;
    }
    private int dp(float value){return (int)(value*getResources().getDisplayMetrics().density+0.5f);}
    private void showMoreMenu(){
        String[] options={"انبار و کالا","فاکتورها","گزارش‌ها","تنظیمات","اتصال به ویندوز"};
        new AlertDialog.Builder(this).setTitle("بخش‌های ShopManager").setItems(options,(dialog,index)->{
            switch(index){case 0:inventoryPage();break;case 1:invoicePage();break;
                case 2:reportsPage();break;case 3:settingsPage();break;default:connectionPage();}
        }).show();
    }
    private void tab(LinearLayout container,String label,Runnable run){
        String glyph="خانه".equals(label)?"⌂":"پذیرش".equals(label)?"✚":"پرونده‌ها".equals(label)?"▤":
                "مشتریان".equals(label)?"♙":"☷";
        LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(android.view.Gravity.CENTER);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-1,1);
        p.setMargins(dp(1),0,dp(1),0);container.addView(tile,p);
        TextView icon=text(glyph);icon.setTextSize(22);icon.setTextColor(Color.rgb(90,174,255));
        icon.setGravity(android.view.Gravity.CENTER);icon.setPadding(0,0,0,0);tile.addView(icon);
        TextView name=text(label);name.setTextSize(10);name.setSingleLine(true);
        name.setTextColor(Color.rgb(215,230,247));name.setGravity(android.view.Gravity.CENTER);
        name.setPadding(0,dp(1),0,0);tile.addView(name);
        tile.setOnClickListener(v->run.run());
    }
    private void iconTile(LinearLayout row,String glyph,String label,int color,Runnable run){
        LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(android.view.Gravity.CENTER);
        tile.setPadding(dp(7),dp(10),dp(7),dp(10));
        tile.setBackground(gradient(new int[]{color,Color.rgb(8,34,59)},17));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(100),1);
        p.setMargins(dp(4),dp(4),dp(4),dp(4));row.addView(tile,p);
        TextView symbol=text(glyph);symbol.setTextSize(26);symbol.setTextColor(Color.WHITE);
        symbol.setGravity(android.view.Gravity.CENTER);symbol.setPadding(0,0,0,dp(3));tile.addView(symbol);
        TextView caption=text(label);caption.setTextSize(12);caption.setTypeface(null,Typeface.BOLD);
        caption.setSingleLine(true);caption.setTextColor(Color.WHITE);
        caption.setGravity(android.view.Gravity.CENTER);caption.setPadding(0,0,0,0);
        tile.addView(caption);
        tile.setOnClickListener(v->run.run());
    }
    private void quickRow(String a,String b,String c){
        LinearLayout row1=new LinearLayout(this);row1.setOrientation(LinearLayout.HORIZONTAL);body.addView(row1);
        iconTile(row1,"✚","پذیرش جدید",Color.rgb(16,106,219),this::intakePage);
        iconTile(row1,"♙","مشتری جدید",Color.rgb(13,154,104),this::customersPage);
        LinearLayout row2=new LinearLayout(this);row2.setOrientation(LinearLayout.HORIZONTAL);body.addView(row2);
        iconTile(row2,"▣","کالا و انبار",Color.rgb(214,133,20),this::inventoryPage);
        iconTile(row2,"▤","فاکتورها",Color.rgb(116,52,188),this::invoicePage);
    }
    private void action(String name, Runnable run) {
        Button b = new Button(this); b.setText(name); b.setTextColor(Color.WHITE); b.setAllCaps(false); b.setBackground(round(blue,14)); b.setPadding(12,10,12,10); LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,-2);bp.setMargins(3,6,3,6);body.addView(b,bp);
        b.setOnClickListener(v -> run.run());
    }
    private void reset(String heading) {
        body.removeAllViews();
        TextView t=text(heading); t.setTextSize(19); t.setTextColor(Color.WHITE); t.setTypeface(null, Typeface.BOLD);
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

    private GradientDrawable gradient(int[] colors,int radiusDp) {
        GradientDrawable d=new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,colors);
        d.setCornerRadius(radiusDp*getResources().getDisplayMetrics().density);
        d.setStroke((int)(1*getResources().getDisplayMetrics().density),Color.rgb(20,78,120));return d;
    }
    private GradientDrawable round(int color,int radiusDp) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);
        d.setCornerRadius(radiusDp*getResources().getDisplayMetrics().density);return d;
    }
    private void metricCard(LinearLayout target,String title,String value,int accent,String glyph){
        LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(12),dp(11),dp(12),dp(10));
        card.setBackground(gradient(new int[]{Color.rgb(12,45,76),Color.rgb(5,27,49)},17));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(109),1);
        p.setMargins(dp(4),dp(4),dp(4),dp(4));target.addView(card,p);
        LinearLayout top=new LinearLayout(this);top.setGravity(android.view.Gravity.CENTER_VERTICAL);
        card.addView(top,new LinearLayout.LayoutParams(-1,0,1));
        TextView titleView=text(title);titleView.setTextSize(12);titleView.setTypeface(null,Typeface.BOLD);
        titleView.setTextColor(Color.rgb(199,220,241));titleView.setPadding(0,0,0,0);
        top.addView(titleView,new LinearLayout.LayoutParams(0,-2,1));
        TextView symbol=text(glyph);symbol.setTextSize(19);symbol.setTextColor(accent);
        symbol.setGravity(android.view.Gravity.CENTER);symbol.setPadding(0,0,0,0);
        top.addView(symbol,new LinearLayout.LayoutParams(dp(30),dp(30)));
        TextView v=text(value);v.setTextSize(26);v.setTypeface(null,Typeface.BOLD);
        v.setTextColor(Color.WHITE);v.setPadding(0,0,0,0);
        card.addView(v);
        View strip=new View(this);strip.setBackground(round(accent,5));
        LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(dp(43),dp(3));sp.topMargin=dp(6);
        card.addView(strip,sp);
    }
    private LinearLayout dashboardPanel(String title){
        LinearLayout outer=new LinearLayout(this);outer.setOrientation(LinearLayout.VERTICAL);
        outer.setPadding(dp(12),dp(10),dp(12),dp(12));
        outer.setBackground(gradient(new int[]{Color.rgb(10,37,63),Color.rgb(5,23,43)},17));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);
        p.setMargins(dp(4),dp(9),dp(4),dp(3));body.addView(outer,p);
        TextView heading=text(title);heading.setTextColor(Color.WHITE);
        heading.setTypeface(null,Typeface.BOLD);heading.setTextSize(15);
        heading.setPadding(0,0,0,dp(7));outer.addView(heading);
        return outer;
    }
    private void homePage(){
        reset("داشبورد مدیریت تعمیرگاه");
        JSONArray jobs=snapshot.optJSONArray("jobs"),customers=snapshot.optJSONArray("customers"),
                items=snapshot.optJSONArray("items");
        int active=0,delivered=0,low=0;long paid=0;
        if(jobs!=null)for(int i=0;i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            String state=j.optString("status");
            if("تحویل شده".equals(state)||"تکمیل شده".equals(state))delivered++;
            else active++;
            paid+=j.optLong("paid");
        }
        if(items!=null)for(int i=0;i<items.length();i++){
            JSONObject item=items.optJSONObject(i);if(item!=null&&item.optInt("qty")<=2)low++;
        }
        LinearLayout first=new LinearLayout(this);first.setOrientation(LinearLayout.HORIZONTAL);body.addView(first);
        metricCard(first,"تعمیرات فعال",String.valueOf(active),Color.rgb(9,213,232),"✚");
        metricCard(first,"مشتریان",String.valueOf(customers==null?0:customers.length()),Color.rgb(26,222,133),"♙");
        LinearLayout second=new LinearLayout(this);second.setOrientation(LinearLayout.HORIZONTAL);body.addView(second);
        metricCard(second,"موجودی کالا",String.valueOf(items==null?0:items.length()),Color.rgb(255,176,46),"▣");
        metricCard(second,"دریافتی ثبت‌شده",compactMoney(paid),Color.rgb(186,115,253),"﷼");

        LinearLayout quick=dashboardPanel("عملیات سریع");
        // Keep quick actions inside their own card, not the root, to match the reference.
        LinearLayout firstQuick=new LinearLayout(this);firstQuick.setOrientation(LinearLayout.HORIZONTAL);quick.addView(firstQuick);
        iconTile(firstQuick,"✚","پذیرش جدید",Color.rgb(15,101,221),this::intakePage);
        iconTile(firstQuick,"♙","مشتری جدید",Color.rgb(12,156,108),this::customersPage);
        LinearLayout secondQuick=new LinearLayout(this);secondQuick.setOrientation(LinearLayout.HORIZONTAL);quick.addView(secondQuick);
        iconTile(secondQuick,"▣","انبار و کالا",Color.rgb(207,130,19),this::inventoryPage);
        iconTile(secondQuick,"▤","فاکتورها",Color.rgb(118,48,188),this::invoicePage);

        LinearLayout recent=dashboardPanel("آخرین پرونده‌های تعمیر");
        if(jobs==null||jobs.length()==0){
            TextView empty=text("هنوز پرونده‌ای ثبت نشده است. برای شروع، پذیرش جدید ایجاد کنید.");
            empty.setTextColor(Color.rgb(169,196,220));empty.setTextSize(12);recent.addView(empty);
        }else{
            int count=0;for(int i=0;i<jobs.length()&&count<4;i++){
                JSONObject j=jobs.optJSONObject(i);if(j==null)continue;count++;
                LinearLayout line=new LinearLayout(this);line.setGravity(android.view.Gravity.CENTER_VERTICAL);
                line.setPadding(dp(9),dp(6),dp(9),dp(6));
                line.setBackground(round(Color.rgb(13,49,79),11));
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,dp(3),0,dp(3));recent.addView(line,lp);
                LinearLayout names=new LinearLayout(this);names.setOrientation(LinearLayout.VERTICAL);
                line.addView(names,new LinearLayout.LayoutParams(0,-2,1));
                TextView code=text(j.optString("order_code")+"  •  "+j.optString("customer_name"));
                code.setTextColor(Color.WHITE);code.setTextSize(12);code.setTypeface(null,Typeface.BOLD);
                code.setPadding(0,0,0,0);names.addView(code);
                TextView device=text(j.optString("device"));
                device.setTextColor(Color.rgb(174,201,225));device.setTextSize(11);device.setPadding(0,0,0,0);names.addView(device);
                TextView state=text(j.optString("status"));
                state.setTextColor(Color.rgb(54,218,149));state.setTextSize(11);line.addView(state);
            }
        }

        LinearLayout alerts=dashboardPanel("یادآوری‌ها و هشدارها");
        TextView line1=text("●  "+pending.length()+" ثبت در انتظار همگام‌سازی با ویندوز");
        line1.setTextColor(Color.rgb(255,188,77));alerts.addView(line1);
        TextView line2=text("●  "+low+" قلم کالا با موجودی پایین");
        line2.setTextColor(Color.rgb(181,211,240));alerts.addView(line2);
        LinearLayout sync=dashboardPanel("اتصال به سیستم اصلی");
        TextView hint=text(url().isEmpty()?"سیستم ویندوز هنوز متصل نشده است.":"نشانی مستر: "+url());
        hint.setTextSize(12);hint.setTextColor(Color.rgb(176,207,237));sync.addView(hint);
        Button connect=new Button(this);connect.setText("اتصال و همگام‌سازی");
        connect.setAllCaps(false);connect.setTextColor(Color.WHITE);connect.setBackground(round(blue,13));
        sync.addView(connect,new LinearLayout.LayoutParams(-1,dp(48)));
        connect.setOnClickListener(v->connectionPage());
    }
    private String compactMoney(long amount){
        return String.format(java.util.Locale.US,"%,d",amount);
    }

    private String currency(){return prefs.getString("currency","تومان");}
    private String moneyText(long value){return String.format(java.util.Locale.US,"%,d",value)+" "+currency();}
    private void reportsPage(){
        reset("گزارش‌های مدیریتی");
        JSONArray jobs=snapshot.optJSONArray("jobs"),customers=snapshot.optJSONArray("customers"),items=snapshot.optJSONArray("items");
        int active=0,done=0,low=0;long paid=0;
        if(jobs!=null)for(int i=0;i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            String st=j.optString("status");if(st.equals("تحویل شده")||st.equals("تکمیل شده"))done++;else active++;paid+=j.optLong("paid");}
        if(items!=null)for(int i=0;i<items.length();i++){JSONObject it=items.optJSONObject(i);if(it!=null&&it.optInt("qty")<=2)low++;}
        reportCard("کل پرونده‌ها",String.valueOf(jobs==null?0:jobs.length()));
        reportCard("پرونده‌های فعال",String.valueOf(active));reportCard("تحویل‌شده",String.valueOf(done));
        reportCard("مشتریان",String.valueOf(customers==null?0:customers.length()));
        reportCard("مجموع پرداخت ثبت‌شده",moneyText(paid));reportCard("اقلام کم‌موجودی",String.valueOf(low));
        action("به‌روزرسانی از سیستم اصلی",this::synchronize);
    }
    private void reportCard(String title,String value){
        LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(14,10,14,10);
        card.setBackground(gradient(new int[]{Color.rgb(12,43,70),Color.rgb(5,24,43)},14));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(3,5,3,5);body.addView(card,p);
        TextView t=text(title);t.setTextColor(Color.rgb(177,203,227));card.addView(t);
        TextView v=text(value);v.setTextSize(20);v.setTextColor(Color.WHITE);v.setTypeface(null,Typeface.BOLD);card.addView(v);
    }
    private void invoicePage(){
        reset("فاکتورها و صورت‌حساب‌ها");
        JSONArray jobs=snapshot.optJSONArray("jobs");
        if(jobs==null||jobs.length()==0){body.addView(text("پرونده‌ای برای صدور فاکتور دریافت نشده است."));return;}
        for(int i=0;i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            long parts=j.optLong("estimate_parts"),labor=j.optLong("labor"),discount=j.optLong("discount"),paid=j.optLong("paid");
            long total=Math.max(0,parts+labor-discount);
            LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(12,10,12,10);
            card.setBackground(gradient(new int[]{Color.rgb(12,43,70),Color.rgb(5,24,43)},14));
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(3,5,3,5);body.addView(card,p);
            TextView h=text(j.optString("order_code")+"  |  "+j.optString("customer_name"));h.setTextColor(Color.WHITE);h.setTypeface(null,Typeface.BOLD);card.addView(h);
            card.addView(text(j.optString("device")+"  |  "+j.optString("status")));
            card.addView(text("قطعات برآوردی: "+moneyText(parts)+"   دستمزد: "+moneyText(labor)));
            card.addView(text("تخفیف: "+moneyText(discount)+"   جمع: "+moneyText(total)));
            card.addView(text("پرداخت: "+moneyText(paid)+"   مانده: "+moneyText(Math.max(0,total-paid))));
            actionIn(card,"نمایش صورت‌حساب",()->new AlertDialog.Builder(this).setTitle("صورت‌حساب "+j.optString("order_code"))
                .setMessage("مشتری: "+j.optString("customer_name")+"\\nدستگاه: "+j.optString("device")+"\\nقطعات: "+moneyText(parts)
                +"\\nدستمزد: "+moneyText(labor)+"\\nتخفیف: "+moneyText(discount)+"\\nمبلغ نهایی: "+moneyText(total)
                +"\\nپرداخت: "+moneyText(paid)+"\\nمانده: "+moneyText(Math.max(0,total-paid)))
                .setPositiveButton("بستن",null).show());
        }
    }
    private void actionIn(LinearLayout parent,String label,Runnable run){
        Button b=new Button(this);b.setText(label);b.setTextColor(Color.WHITE);b.setAllCaps(false);b.setBackground(round(blue,12));
        parent.addView(b,new LinearLayout.LayoutParams(-1,-2));b.setOnClickListener(v->run.run());
    }
    private void settingsPage(){
        reset("تنظیمات برنامه");
        body.addView(text("ظاهر و پوسته"));
        Spinner themes=new Spinner(this);String[] themeNames={"سرمه‌ای نئونی","تیره ساده","روشن"};
        themes.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,themeNames));
        String savedTheme=prefs.getString("theme",themeNames[0]);for(int i=0;i<themeNames.length;i++)if(themeNames[i].equals(savedTheme))themes.setSelection(i);
        body.addView(themes,new LinearLayout.LayoutParams(-1,-2));
        body.addView(text("واحد مالی"));
        Spinner currencies=new Spinner(this);String[] units={"تومان","ریال"};currencies.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,units));
        currencies.setSelection("ریال".equals(currency())?1:0);body.addView(currencies,new LinearLayout.LayoutParams(-1,-2));
        action("ذخیره تنظیمات",()->{
            String theme=String.valueOf(themes.getSelectedItem()),unit=String.valueOf(currencies.getSelectedItem());
            prefs.edit().putString("theme",theme).putString("currency",unit).apply();
            applyMobileTheme(theme);toast("تنظیمات ذخیره شد.");
        });
        body.addView(text("امنیت و رمز عبور برنامه"));
        EditText current=field("رمز فعلی (در صورت وجود)","");
        EditText pass=field("رمز جدید (حداقل ۶ کاراکتر)","");
        action("ثبت یا تغییر رمز برنامه",()->{
            String value=pass.getText().toString();
            if(value.length()<6){toast("رمز جدید باید حداقل ۶ کاراکتر باشد.");return;}
            if(prefs.contains("password_hash")&&!verifyMobilePassword(current.getText().toString())){
                toast("رمز فعلی صحیح نیست.");return;
            }
            storeMobilePassword(value);current.setText("");pass.setText("");toast("رمز برنامه ذخیره شد.");
        });
        body.addView(text("تغییرات و حذف اطلاعات اصلی فقط روی نسخه مستر ویندوز انجام می‌شود؛ این رمز محلی جایگزین احراز هویت مستر نیست."));
    }
    private void applyMobileTheme(String theme){
        int bg=Color.rgb(4,18,34),panel=Color.rgb(12,43,70),fg=Color.WHITE;
        if("تیره ساده".equals(theme)){bg=Color.rgb(25,29,36);panel=Color.rgb(42,48,58);}
        if("روشن".equals(theme)){bg=Color.rgb(237,242,248);panel=Color.WHITE;fg=Color.rgb(25,39,58);}
        pale=bg;ink=fg;root.setBackgroundColor(bg);body.setBackgroundColor(bg);
        if("روشن".equals(theme))blue=Color.rgb(24,91,190);else blue=Color.rgb(0,126,255);
        if(body.getChildCount()>0)toast("تم جدید برای صفحات بعدی اعمال شد.");
    }
    private void storeMobilePassword(String password){
        try{
            byte[] salt=new byte[16];new SecureRandom().nextBytes(salt);
            PBEKeySpec spec=new PBEKeySpec(password.toCharArray(),salt,180000,256);
            byte[] hash=SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            prefs.edit().putString("password_salt",android.util.Base64.encodeToString(salt,android.util.Base64.NO_WRAP))
                .putString("password_hash",android.util.Base64.encodeToString(hash,android.util.Base64.NO_WRAP)).apply();
        }catch(Exception e){toast("خطا در ذخیره رمز: "+e.getMessage());}
    }
    private boolean verifyMobilePassword(String password){
        try{
            byte[] salt=android.util.Base64.decode(prefs.getString("password_salt",""),android.util.Base64.NO_WRAP);
            byte[] expected=android.util.Base64.decode(prefs.getString("password_hash",""),android.util.Base64.NO_WRAP);
            PBEKeySpec spec=new PBEKeySpec(password.toCharArray(),salt,180000,256);
            byte[] actual=SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return MessageDigest.isEqual(expected,actual);
        }catch(Exception e){return false;}
    }

    private void connectionPage() {
        reset("اتصال به سیستم اصلی (ویندوز)");
        body.addView(text("هر دو دستگاه باید در یک شبکه خصوصی باشند. از برنامه ویندوز دکمه فعال‌سازی همگام‌سازی را بزنید."));
        EditText address=field("http://192.168.1.10:8765",url());
        EditText token=field("کد اتصال نمایش‌داده‌شده روی ویندوز",key());
        action("ذخیره نشانی و کد اتصال",()->{
            prefs.edit().putString("url",address.getText().toString().trim())
                    .putString("key",token.getText().toString().trim()).apply();
            toast("تنظیمات اتصال ذخیره شد");
        });
        action("همگام‌سازی اکنون",()->{
            prefs.edit().putString("url",address.getText().toString().trim())
                    .putString("key",token.getText().toString().trim()).apply();
            synchronize();
        });
        body.addView(text("در حالت آفلاین، مشتری و پذیرش جدید در صف ثبت می‌شوند. کد نهایی سفارش فقط پس از تأیید ویندوز صادر می‌شود. مصرف قطعات از موبایل فعلاً غیرفعال است."));
        action("مشاهده اقلام موجودی سیستم",()->inventoryPage());
    }

    private JSONArray customers() {
        JSONArray result=new JSONArray(), master=snapshot.optJSONArray("customers");
        if(master!=null) for(int i=0;i<master.length();i++) result.put(master.optJSONObject(i));
        for(int i=0;i<pending.length();i++) {
            JSONObject op=pending.optJSONObject(i);
            if(op!=null && "customer".equals(op.optString("kind"))) {
                JSONObject customer=new JSONObject();
                try {
                    customer.put("name",op.optString("name")+" (در انتظار)");
                    customer.put("first_name",op.optString("first_name"));
                    customer.put("last_name",op.optString("last_name"));
                    customer.put("phone",op.optString("phone"));
                    customer.put("address",op.optString("address"));
                    customer.put("client_ref",op.optString("ref"));
                    customer.put("id",0);
                    result.put(customer);
                } catch(Exception ignored){}
            }
        }
        return result;
    }
    private void customersPage() {
        reset("ثبت مشتری");
        body.addView(text("پروفایل مشتری"));
        EditText firstName=field("نام (اجباری)","");
        EditText lastName=field("نام خانوادگی (اجباری)","");
        EditText phone=field("شماره تماس (اجباری)","");
        EditText address=field("آدرس محل سکونت (اختیاری)","");
        action("ثبت پروفایل مشتری",()->{
            String first=firstName.getText().toString().trim();
            String last=lastName.getText().toString().trim();
            String mobile=phone.getText().toString().trim();
            if(first.isEmpty()||last.isEmpty()||mobile.isEmpty()){
                toast("نام، نام خانوادگی و شماره تماس الزامی هستند");return;
            }
            JSONObject op=new JSONObject();
            try {
                op.put("kind","customer");op.put("ref",UUID.randomUUID().toString());
                op.put("first_name",first);
                op.put("last_name",last);
                op.put("name",first+" "+last);
                op.put("phone",mobile);
                op.put("address",address.getText().toString().trim());
                pending.put(op);save();toast("مشتری در صف ثبت شد");
                customersPage();
            } catch(Exception e){toast(e.getMessage());}
        });
        body.addView(text("مشتریان مشترک و در انتظار"));
        JSONArray list=customers();
        for(int i=0;i<list.length();i++) {
            JSONObject c=list.optJSONObject(i);
            if(c!=null)body.addView(text(c.optString("name")+" | "+c.optString("phone")));
        }
    }
    private void intakePage() {
        reset("پذیرش دستگاه / سفارش");
        JSONArray people=customers();
        if(people.length()==0){body.addView(text("ابتدا مشتری ثبت کنید یا اطلاعات سیستم را همگام کنید."));return;}
        String[] choices=new String[people.length()];
        for(int i=0;i<people.length();i++) choices[i]=people.optJSONObject(i).optString("name");
        Spinner picker=new Spinner(this);
        picker.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,choices));
        body.addView(picker);
        body.addView(text("۱) نوع دستگاه"));
        Spinner deviceType=new Spinner(this);
        deviceType.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,
                new String[]{"گوشی لمسی","گوشی دکمه‌ای"}));
        body.addView(deviceType);
        body.addView(text("۲) برند"));
        Spinner brandPicker=new Spinner(this); body.addView(brandPicker);
        body.addView(text("۳) جست‌وجو و انتخاب مدل"));
        EditText modelSearch=field("نام مدل را جست‌وجو کنید...","");
        ListView modelList=new ListView(this);
        body.addView(modelList,new LinearLayout.LayoutParams(-1,260));
        EditText customModel=field("اگر مدل در فهرست نیست، اینجا وارد کنید","");
        TextView selectedModel=text("مدل انتخاب‌شده: هنوز انتخاب نشده");
        body.addView(selectedModel);
        final String[] chosenModel={""};
        final String[] chosenBrand={""};
        Runnable refreshModels=()->{
            String category=String.valueOf(deviceType.getSelectedItem());
            JSONObject brands=deviceCatalog.optJSONObject(category);
            ArrayList<String> brandNames=new ArrayList<>();
            if(brands!=null){Iterator<String> it=brands.keys();while(it.hasNext())brandNames.add(it.next());}
            java.util.Collections.sort(brandNames,String.CASE_INSENSITIVE_ORDER);
            chosenBrand[0]="";
            chosenModel[0]="";
            selectedModel.setText("مدل انتخاب‌شده: هنوز انتخاب نشده");
            brandPicker.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,brandNames));
            if(!brandNames.isEmpty()) brandPicker.setSelection(0);
            else {
                modelList.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_list_item_1,new ArrayList<String>()));
            }
        };
        Runnable filterModels=()->{
            String category=String.valueOf(deviceType.getSelectedItem());
            JSONObject brands=deviceCatalog.optJSONObject(category);
            String brand=brandPicker.getSelectedItem()==null?"":brandPicker.getSelectedItem().toString();
            if(brands==null || !brands.has(brand)) {
                modelList.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_list_item_1,new ArrayList<String>()));
                chosenBrand[0]="";
                chosenModel[0]="";
                selectedModel.setText("مدل انتخاب‌شده: هنوز انتخاب نشده");
                return;
            }
            chosenBrand[0]=brand;
            JSONArray models=brands==null?new JSONArray():brands.optJSONArray(brand);
            ArrayList<String> filtered=new ArrayList<>();
            String query=modelSearch.getText().toString().trim().toLowerCase(java.util.Locale.ROOT);
            if(models!=null)for(int i=0;i<models.length();i++){
                String model=models.optString(i);
                if(model.toLowerCase(java.util.Locale.ROOT).contains(query))filtered.add(model);
            }
            modelList.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_list_item_1,filtered));
            chosenModel[0]="";
            selectedModel.setText("مدل انتخاب‌شده: هنوز انتخاب نشده");
        };
        refreshModels.run();
        brandPicker.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){filterModels.run();}
        });
        modelSearch.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence a,int b,int c,int d){}
            public void onTextChanged(CharSequence a,int b,int c,int d){filterModels.run();}
            public void afterTextChanged(android.text.Editable e){}
        });
        modelList.setOnItemClickListener((parent,view,position,id)->{
            chosenModel[0]=String.valueOf(parent.getItemAtPosition(position));
            customModel.setText("");
            selectedModel.setText("مدل انتخاب‌شده: "+chosenBrand[0]+" "+chosenModel[0]);
        });
        body.addView(text("۴) در صورت نبود مدل در فهرست، نام آن را دستی وارد کنید."));
        body.addView(text("وضعیت دستگاه هنگام تحویل"));
        Spinner powerState=new Spinner(this);
        powerState.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,
                new String[]{"انتخاب وضعیت","روشن","خاموش"}));
        body.addView(powerState);
        body.addView(text("وضعیت فیزیکی و قطعات"));
        String[] physicalOptions={"شکستگی نمایشگر","ترک‌خوردگی قاب","شکستگی قاب/بدنه",
                "آسیب‌دیدگی سوکت شارژ","آثار رطوبت یا آب‌خوردگی","خط‌وخش یا فرورفتگی",
                "باتری مفقود","سیم‌کارت مفقود","کارت حافظه مفقود","خشاب سیم‌کارت مفقود",
                "درب پشت مفقود","درپوش باتری مفقود","شارژر مفقود","کابل USB مفقود",
                "لوازم جانبی مفقود","قلم لمسی مفقود","پیچ یا قطعه بدنه مفقود","سایر نقص‌ها"};
        CheckBox[] physicalChecks=new CheckBox[physicalOptions.length];
        for(int i=0;i<physicalOptions.length;i++){
            physicalChecks[i]=new CheckBox(this);
            physicalChecks[i].setText(physicalOptions[i]);
            body.addView(physicalChecks[i]);
        }
        EditText physicalOther=field("شرح سایر نقص‌ها یا قطعات مفقود (اختیاری)","");
        body.addView(text("گزارش عیب"));
        EditText reported=field("عیب اعلامی مشتری","");
        EditText diagnosis=field("تشخیص تعمیرکار (در صورت مشخص‌بودن)","");
        EditText estimateParts=field("برآورد اولیه قطعات (تومان)","0");
        EditText estimateLabor=field("برآورد اولیه دستمزد (تومان)","0");
        body.addView(text("این مبالغ صرفاً برآورد اولیه‌اند و مبلغ قطعی فاکتور نیستند."));
        body.addView(text("موارد مشاهده‌شده هنگام تحویل"));
        CheckBox[] checkboxes=new CheckBox[faults.length];
        LinearLayout keypadPanel=new LinearLayout(this);
        keypadPanel.setOrientation(LinearLayout.VERTICAL);
        body.addView(keypadPanel);
        CheckBox[] keys=new CheckBox[21];
        String[][] rows={{"چراغ‌قوه","بلندتر","کمتر"},{"کلید چپ","جهت بالا","کلید راست"},
                {"جهت چپ","OK","جهت راست"},{"جهت پایین","بازگشت","منو"},
                {"تماس","پایان تماس","پاک‌کردن"},{"1","2","3"},{"4","5","6"},
                {"7","8","9"},{"*","0","#"}};
        java.util.ArrayList<String> keyNames=new java.util.ArrayList<>();
        for(String[] row:rows) for(String key:row) keyNames.add(key);
        for(int i=0;i<faults.length;i++){
            final int index=i;
            checkboxes[i]=new CheckBox(this);
            checkboxes[i].setText(faults[i]);body.addView(checkboxes[i]);
            if("خرابی دکمه‌ها".equals(faults[i])) checkboxes[i].setOnCheckedChangeListener((v,checked)->{
                boolean feature=deviceType.getSelectedItemPosition()==1;
                keypadPanel.setVisibility(checked&&feature?View.VISIBLE:View.GONE);
            });
        }
        deviceType.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){
                modelSearch.setText("");
                customModel.setText("");
                chosenBrand[0]="";
                chosenModel[0]="";
                selectedModel.setText("مدل انتخاب‌شده: هنوز انتخاب نشده");
                refreshModels.run();
                boolean buttonFault=checkboxes[9]!=null&&checkboxes[9].isChecked();
                keypadPanel.setVisibility(pos==1&&buttonFault?View.VISIBLE:View.GONE);
            }
        });
        keypadPanel.addView(text("روی تصویر کلیدها، دکمه‌های معیوب را انتخاب کنید"));
        for(String[] row:rows){
            LinearLayout line=new LinearLayout(this);line.setOrientation(LinearLayout.HORIZONTAL);
            keypadPanel.addView(line);
            for(String key:row){
                CheckBox cb=new CheckBox(this);cb.setText(key);cb.setTextSize(12);
                line.addView(cb,new LinearLayout.LayoutParams(0,-2,1));
                cb.setTag(key);
            }
        }
        keypadPanel.setVisibility(View.GONE);
        action("ثبت پذیرش (کد نهایی پس از همگام‌سازی)",()->{
            JSONObject person=people.optJSONObject(picker.getSelectedItemPosition());
            if(person==null){toast("مشتری انتخاب نشده");return;}
            JSONObject op=new JSONObject();
            try {
                op.put("kind","job");op.put("ref",UUID.randomUUID().toString());
                String clientRef=person.isNull("client_ref")?"":person.optString("client_ref","");
                if(!clientRef.isEmpty())op.put("customer_ref",clientRef);
                else op.put("customer_id",person.optLong("id"));
                String manualModel=customModel.getText().toString().trim();
                String model=manualModel.isEmpty()?chosenModel[0]:manualModel;
                if(model.isEmpty()){toast("مدل گوشی را از فهرست انتخاب کنید یا دستی وارد کنید");return;}
                if(powerState.getSelectedItemPosition()==0){
                    toast("وضعیت روشن یا خاموش بودن دستگاه را مشخص کنید");return;
                }
                op.put("device",deviceType.getSelectedItem().toString()+" | "+chosenBrand[0]+" | "+model);
                op.put("power_state",powerState.getSelectedItem().toString());
                op.put("reported",reported.getText().toString().trim());
                op.put("diagnosis",diagnosis.getText().toString().trim());
                op.put("estimate_parts",parseMoney(estimateParts.getText().toString()));
                op.put("estimate_labor",parseMoney(estimateLabor.getText().toString()));
                JSONArray selected=new JSONArray();
                for(int i=0;i<faults.length;i++)if(checkboxes[i].isChecked())selected.put(faults[i]);
                if(checkboxes[9].isChecked()&&deviceType.getSelectedItemPosition()==1){
                    for(int i=0;i<keypadPanel.getChildCount();i++){
                        View child=keypadPanel.getChildAt(i);
                        if(child instanceof LinearLayout){
                            LinearLayout line=(LinearLayout)child;
                            for(int j=0;j<line.getChildCount();j++){
                                CheckBox cb=(CheckBox)line.getChildAt(j);
                                if(cb.isChecked())selected.put("دکمه معیوب: "+cb.getText());
                            }
                        }
                    }
                }
                op.put("checks",selected);
                JSONArray physical=new JSONArray();
                for(int i=0;i<physicalChecks.length;i++)if(physicalChecks[i].isChecked())physical.put(physicalOptions[i]);
                String extraPhysical=physicalOther.getText().toString().trim();
                if(!extraPhysical.isEmpty())physical.put("سایر: "+extraPhysical);
                op.put("physical_conditions",physical);
                try {
                    createIntakeArchive(op,person);
                    toast("گزارش پذیرش در بایگانی گوشی ذخیره شد");
                } catch(Exception reportError) {
                    toast("پذیرش ثبت شد؛ ساخت گزارش ناموفق بود: "+reportError.getMessage());
                }
                pending.put(op);save();toast("پذیرش با شناسه موقت ثبت شد");intakePage();
            }catch(Exception e){toast(e.getMessage());}
        });
    }
    private String createIntakeArchive(JSONObject op, JSONObject person) throws Exception {
        File base=getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS);
        if(base==null)base=getFilesDir();
        File archive=new File(base,"Archive/IntakeReports");
        if(!archive.exists()&&!archive.mkdirs())throw new IOException("ساخت پوشه بایگانی ممکن نشد");
        String id=op.optString("ref").replace("-","");
        if(id.length()>8)id=id.substring(0,8);
        String code="TEMP-"+id;
        ArrayList<String> lines=new ArrayList<>();
        lines.add("گزارش پذیرش دستگاه - ShopManager");
        lines.add("شناسه موقت پرونده: "+code);
        lines.add("تاریخ: "+new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",java.util.Locale.getDefault()).format(new java.util.Date()));
        lines.add("");
        lines.add("مشخصات مشتری");
        lines.add("نام: "+person.optString("first_name",person.optString("name"))+" "+person.optString("last_name"));
        lines.add("شماره تماس: "+person.optString("phone"));
        lines.add("آدرس: "+person.optString("address","ثبت نشده"));
        lines.add("");
        lines.add("مشخصات دستگاه: "+op.optString("device"));
        lines.add("وضعیت هنگام تحویل: "+op.optString("power_state"));
        lines.add("عیب اعلامی مشتری: "+op.optString("reported","ثبت نشده"));
        lines.add("تشخیص تعمیرکار: "+op.optString("diagnosis","ثبت نشده"));
        lines.add("");
        lines.add("وضعیت فیزیکی و قطعات:");
        JSONArray physical=op.optJSONArray("physical_conditions");
        if(physical==null||physical.length()==0)lines.add("موردی ثبت نشده");
        else for(int i=0;i<physical.length();i++)lines.add("• "+physical.optString(i));
        lines.add("");
        lines.add("موارد عیب و عملکرد:");
        JSONArray checks=op.optJSONArray("checks");
        if(checks==null||checks.length()==0)lines.add("موردی ثبت نشده");
        else for(int i=0;i<checks.length();i++)lines.add("• "+checks.optString(i));
        lines.add("");
        lines.add("امضای مشتری: ........................................");
        lines.add("امضای تحویل‌گیرنده: ........................................");

        int width=1240;
        String reportText=android.text.TextUtils.join("\n",lines);
        SpannableStringBuilder styled=new SpannableStringBuilder(reportText);
        styled.setSpan(new StyleSpan(Typeface.BOLD),0,lines.get(0).length(),Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        TextView reportView=new TextView(this);
        reportView.setText(styled);
        reportView.setTextDirection(View.TEXT_DIRECTION_RTL);
        reportView.setGravity(android.view.Gravity.RIGHT);
        reportView.setTextColor(Color.rgb(25,39,58));
        reportView.setTextSize(22);
        reportView.setLineSpacing(14,1.15f);
        reportView.setPadding(70,65,70,65);
        reportView.measure(
                View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED));
        int height=Math.max(1754,reportView.getMeasuredHeight());
        reportView.layout(0,0,width,height);
        Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);
        reportView.draw(canvas);
        File png=new File(archive,code+".png");
        try(FileOutputStream out=new FileOutputStream(png)){bitmap.compress(Bitmap.CompressFormat.PNG,100,out);}

        PdfDocument document=new PdfDocument();
        PdfDocument.PageInfo info=new PdfDocument.PageInfo.Builder(595,842,1).create();
        PdfDocument.Page page=document.startPage(info);
        Canvas pdfCanvas=page.getCanvas();
        pdfCanvas.drawColor(Color.WHITE);
        float scale=Math.min(595f/width,842f/height);
        pdfCanvas.save();
        pdfCanvas.scale(scale,scale);
        pdfCanvas.drawBitmap(bitmap,0,0,null);
        pdfCanvas.restore();
        document.finishPage(page);
        File pdf=new File(archive,code+".pdf");
        try(FileOutputStream out=new FileOutputStream(pdf)){document.writeTo(out);}
        document.close();
        bitmap.recycle();
        return pdf.getAbsolutePath();
    }

    private String readableList(String raw) {
        try {
            JSONArray values=new JSONArray(raw);
            ArrayList<String> items=new ArrayList<>();
            for(int i=0;i<values.length();i++)items.add(values.optString(i));
            return items.isEmpty()?"موردی ثبت نشده":android.text.TextUtils.join("، ",items);
        } catch(Exception ignored) {
            return raw==null||raw.isEmpty()?"موردی ثبت نشده":raw;
        }
    }
    private void jobsPage() {
        reset("پرونده‌های مشترک");
        JSONArray jobs=snapshot.optJSONArray("jobs");
        if(jobs!=null) for(int i=0;i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            body.addView(text(j.optString("order_code")+" | "+j.optString("customer_name")
                +" | "+j.optString("device")+" | "+j.optString("status")
                +"\nوضعیت هنگام تحویل: "+j.optString("power_state")
                +"\nوضعیت فیزیکی: "+readableList(j.optString("physical_condition"))
                +"\nموارد عیب و عملکرد: "+readableList(j.optString("intake_checks"))
                +"\nعیب مشتری: "+j.optString("problem")
                +"\nتشخیص: "+j.optString("diagnosed_fault")
                +"\nدستمزد: "+j.optLong("labor")+" تومان"));
        }
        body.addView(text("پذیرش‌های ارسال‌نشده"));
        for(int i=0;i<pending.length();i++){
            JSONObject op=pending.optJSONObject(i);
            if(op!=null && "job".equals(op.optString("kind")))
                body.addView(text("در انتظار تأیید ویندوز | "+op.optString("device")
                        +" | "+op.optString("reported")));
        }
        action("همگام‌سازی",this::synchronize);
    }
    private void inventoryPage() {
        reset("موجودی (نمایش اطلاعات آخرین همگام‌سازی)");
        JSONArray list=snapshot.optJSONArray("items");
        if(list==null || list.length()==0){body.addView(text("اطلاعاتی دریافت نشده است."));return;}
        for(int i=0;i<list.length();i++){
            JSONObject item=list.optJSONObject(i);
            if(item!=null)body.addView(text(item.optString("sku")+" | "+item.optString("name")
                    +" | موجودی "+item.optInt("qty")+" | قیمت "+item.optLong("price")+" تومان"));
        }
    }
    private long parseMoney(String raw) {
        try { return Math.max(0, Long.parseLong(raw.trim().replace(",","").replace("٬",""))); }
        catch(Exception e) { return 0; }
    }
    private JSONObject http(String path,JSONObject payload)throws Exception {
        if(!url().startsWith("http://"))throw new IOException("نشانی شبکه محلی با http:// وارد شود");
        HttpURLConnection c=(HttpURLConnection)new URL(url()+path).openConnection();
        c.setConnectTimeout(5000);c.setReadTimeout(6000);
        c.setRequestProperty("X-ShopManager-Token",key());
        c.setRequestProperty("Accept","application/json");
        if(payload!=null){
            c.setRequestMethod("POST");c.setDoOutput(true);
            c.setRequestProperty("Content-Type","application/json; charset=utf-8");
            byte[] raw=payload.toString().getBytes(StandardCharsets.UTF_8);
            try(OutputStream out=c.getOutputStream()){out.write(raw);}
        }
        int code=c.getResponseCode();
        InputStream stream=code<400?c.getInputStream():c.getErrorStream();
        ByteArrayOutputStream data=new ByteArrayOutputStream();
        if(stream!=null)try(InputStream input=stream){
            byte[] buf=new byte[4096];int n;
            while((n=input.read(buf))!=-1) data.write(buf,0,n);
        }
        c.disconnect();
        JSONObject result=new JSONObject(data.toString("UTF-8"));
        if(code>=400) throw new IOException(result.optString("error","HTTP "+code));
        return result;
    }
    private void synchronize() {
        if(url().isEmpty()||key().isEmpty()){toast("ابتدا آدرس و کد اتصال را وارد کنید");return;}
        JSONArray tasks;
        try { tasks=new JSONArray(pending.toString()); }
        catch(Exception e) { toast("صف همگام‌سازی معتبر نیست"); return; }
        toast("در حال اتصال به سیستم اصلی");
        executor.execute(()->{
            JSONArray remaining=new JSONArray();
            String error=null;
            try{
                for(int i=0;i<tasks.length();i++){
                    JSONObject op=tasks.getJSONObject(i);
                    try { http("/operation",op); }
                    catch(Exception e) {
                        error=e.getMessage();
                        for(int j=i;j<tasks.length();j++)remaining.put(tasks.getJSONObject(j));
                        break;
                    }
                }
                // Only refresh after every write was acknowledged; accepted ops have stable refs.
                JSONObject master=http("/snapshot",null);
                JSONArray rest=remaining;
                runOnUiThread(()->{
                    pending=rest;snapshot=master;save();jobsPage();
                    toast("همگام‌سازی انجام شد؛ در انتظار: "+pending.length());
                });
            } catch(Exception e){error=e.getMessage();}
            if(error!=null){
                String message=error;
                JSONArray rest=remaining;
                runOnUiThread(()->{
                    pending=rest.length()>0?rest:tasks;
                    save();
                    new AlertDialog.Builder(this).setTitle("همگام‌سازی کامل نشد")
                            .setMessage(message+"\nثبت‌های ارسال‌نشده حفظ شدند.")
                            .setPositiveButton("باشه",null).show();
                });
            }
        });
    }
    @Override protected void onDestroy(){executor.shutdown();super.onDestroy();}
}
