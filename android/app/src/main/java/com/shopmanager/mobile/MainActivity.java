package com.shopmanager.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.pdf.PdfDocument;
import android.os.Environment;
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
        headerBg.setCornerRadius(18*getResources().getDisplayMetrics().density);header.setBackground(headerBg);
        root.addView(header,new LinearLayout.LayoutParams(-1,-2));
        TextView gear=text("⚙");gear.setTextColor(Color.WHITE);gear.setTextSize(27);header.addView(gear);
        LinearLayout brandBlock=new LinearLayout(this);brandBlock.setOrientation(LinearLayout.VERTICAL);brandBlock.setGravity(android.view.Gravity.CENTER);header.addView(brandBlock,new LinearLayout.LayoutParams(0,-2,1));
        TextView role=text("مدیریت فروشگاه و تعمیرگاه");role.setTextColor(Color.rgb(224,237,255));role.setTextSize(12);role.setGravity(android.view.Gravity.CENTER);
        TextView brand=text("ShopManager");brand.setTextColor(Color.WHITE);brand.setTextSize(22);brand.setTypeface(null,Typeface.BOLD);brand.setGravity(android.view.Gravity.CENTER);
        brandBlock.addView(role);brandBlock.addView(brand);TextView shop=text("🏪");shop.setTextSize(27);header.addView(shop);
        status=text("");status.setTextColor(ink);status.setTextSize(12);root.addView(status);
        ScrollView scroll=new ScrollView(this);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(2,8,2,12);scroll.addView(body);
        LinearLayout nav=new LinearLayout(this);nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setPadding(4,6,4,6);nav.setBackground(round(Color.WHITE,18));
        root.addView(nav,new LinearLayout.LayoutParams(-1,-2));
        tab(nav,"خانه",()->homePage());tab(nav,"مشتریان",()->customersPage());tab(nav,"پذیرش",()->intakePage());
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
        e.setPadding(14,12,14,12);
        e.setBackground(round(Color.WHITE,12));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);
        params.setMargins(3,4,3,4);
        body.addView(e, params);
        return e;
    }
    private void tab(LinearLayout container, String name, Runnable action) {
        String glyph="خانه".equals(name)?"⌂":"پذیرش".equals(name)?"🔧":"پرونده‌ها".equals(name)?"▤":"انبار".equals(name)?"▣":"اتصال".equals(name)?"⚙":"مشتریان".equals(name)?"♟":"•";
        LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setGravity(android.view.Gravity.CENTER);item.setPadding(2,4,2,4);
        TextView icon=text(glyph);icon.setTextSize(19);icon.setTextColor(blue);icon.setGravity(android.view.Gravity.CENTER);
        TextView label=text(name);label.setTextSize(10);label.setTextColor(ink);label.setGravity(android.view.Gravity.CENTER);
        item.addView(icon);item.addView(label);container.addView(item,new LinearLayout.LayoutParams(0,-2,1));item.setOnClickListener(v -> action.run());
    }
    private void iconTile(LinearLayout row,String glyph,String label,int color,Runnable run) {
        LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);tile.setGravity(android.view.Gravity.CENTER);tile.setPadding(4,10,4,10);tile.setBackground(round(Color.WHITE,15));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,112,1);p.setMargins(4,4,4,4);row.addView(tile,p);
        TextView icon=text(glyph);icon.setTextSize(27);icon.setTextColor(color);icon.setGravity(android.view.Gravity.CENTER);
        TextView caption=text(label);caption.setTextSize(12);caption.setTypeface(null,Typeface.BOLD);caption.setGravity(android.view.Gravity.CENTER);
        tile.addView(icon);tile.addView(caption);tile.setElevation(2*getResources().getDisplayMetrics().density);tile.setOnClickListener(v->run.run());
    }
    private void quickRow(String a,String b,String c) {
        LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.HORIZONTAL);body.addView(row);
        if("فاکتور".equals(a)) iconTile(row,"▤",a,Color.rgb(125,65,210),this::jobsPage);else if("ثبت تعمیر".equals(a)) iconTile(row,"🔧",a,blue,this::intakePage);else iconTile(row,"▣",a,Color.rgb(25,155,100),this::inventoryPage);
        if("مشتریان".equals(b)) iconTile(row,"♟",b,Color.rgb(230,140,20),this::customersPage);else if("گزارش‌ها".equals(b)) iconTile(row,"▥",b,Color.rgb(225,65,95),this::jobsPage);else iconTile(row,"⚙",b,Color.rgb(95,115,160),this::connectionPage);
        if("تنظیمات".equals(c)) iconTile(row,"☷",c,Color.rgb(95,115,160),this::connectionPage);else iconTile(row,"♟",c,Color.rgb(125,65,210),this::customersPage);
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
        LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.HORIZONTAL);card.setGravity(android.view.Gravity.CENTER_VERTICAL);card.setPadding(7,9,7,9);card.setBackground(round(Color.WHITE,16));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,92,1);p.setMargins(3,3,3,3);
        TextView badge=text(glyph);badge.setTextSize(23);badge.setTextColor(Color.WHITE);badge.setGravity(android.view.Gravity.CENTER);badge.setBackground(round(color,40));card.addView(badge,new LinearLayout.LayoutParams(48,48));
        LinearLayout labels=new LinearLayout(this);labels.setOrientation(LinearLayout.VERTICAL);labels.setGravity(android.view.Gravity.CENTER);
        TextView v=text(value);v.setTextSize(22);v.setTextColor(ink);v.setTypeface(null,Typeface.BOLD);TextView t=text(title);t.setTextSize(10);t.setGravity(android.view.Gravity.CENTER);
        labels.addView(v);labels.addView(t);card.addView(labels,new LinearLayout.LayoutParams(0,-2,1));body.addView(card,p);card.setElevation(2*getResources().getDisplayMetrics().density);
    }
    private void homePage() {
        reset("داشبورد مدیریت تعمیرگاه");
        LinearLayout metrics1=new LinearLayout(this);metrics1.setOrientation(LinearLayout.HORIZONTAL);body.addView(metrics1);
        JSONArray jobs=snapshot.optJSONArray("jobs"), people=snapshot.optJSONArray("customers"), items=snapshot.optJSONArray("items");
        metricCard("تعمیرات جاری",String.valueOf(jobs==null?0:jobs.length()),blue,"🔧");metricCard("فروش امروز","۰",Color.rgb(25,155,100),"🛒");
        LinearLayout metrics2=new LinearLayout(this);metrics2.setOrientation(LinearLayout.HORIZONTAL);body.addView(metrics2);
        metricCard("مشتریان",String.valueOf(people==null?0:people.length()),Color.rgb(125,65,210),"♟");metricCard("کالا در انبار",String.valueOf(items==null?0:items.length()),Color.rgb(230,145,20),"▣");
        TextView quick=text("دسترسی سریع");quick.setTypeface(null,Typeface.BOLD);quick.setTextSize(17);body.addView(quick);
        quickRow("فاکتور","ثبت تعمیر","کالاها");quickRow("مشتریان","گزارش‌ها","تنظیمات");
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);info.setPadding(12,10,12,10);info.setBackground(round(Color.WHITE,14));
        TextView infoTitle=text("◷  تازه‌ترین فعالیت‌ها");infoTitle.setTypeface(null,Typeface.BOLD);infoTitle.setTextSize(16);info.addView(infoTitle);
        info.addView(text("•  در انتظار ارسال: "+pending.length()+" مورد"));info.addView(text("•  آخرین همگام‌سازی: "+(snapshot.length()==0?"هنوز انجام نشده":"اطلاعات دریافت شده")));body.addView(info);
        TextView recent=text("آخرین پرونده‌ها");recent.setTextSize(16);recent.setTypeface(null,Typeface.BOLD);body.addView(recent);
        if(jobs!=null)for(int i=Math.max(0,jobs.length()-4);i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);if(j!=null){LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(10,8,10,8);card.setBackground(round(Color.WHITE,12));card.addView(text("🔧  "+j.optString("order_code")+"  |  "+j.optString("customer_name")));card.addView(text(j.optString("device")+"  |  "+j.optString("status")));body.addView(card);}}
        action("⚙  اتصال و همگام‌سازی با نسخه ویندوز",this::connectionPage);
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
        deviceType.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){
                modelSearch.setText("");
                customModel.setText("");
                chosenBrand[0]="";
                chosenModel[0]="";
                selectedModel.setText("مدل انتخاب‌شده: هنوز انتخاب نشده");
                refreshModels.run();
            }
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
                "پیچ یا قطعه بدنه مفقود","سایر نقص‌ها"};
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

        int width=1240, lineHeight=52, height=Math.max(1754,120+lines.size()*lineHeight);
        Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);
        Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.rgb(25,39,58));
        paint.setTextAlign(Paint.Align.RIGHT);
        paint.setTextDirection(Paint.DIRECTION_RTL);
        int y=90;
        for(int i=0;i<lines.size();i++){
            paint.setTextSize(i==0?38:27);
            paint.setTypeface(i==0?Typeface.create("sans-serif",Typeface.BOLD):Typeface.create("sans-serif",Typeface.NORMAL));
            canvas.drawText(lines.get(i),1180,y,paint);
            y+=lineHeight;
        }
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

    private void jobsPage() {
        reset("پرونده‌های مشترک");
        JSONArray jobs=snapshot.optJSONArray("jobs");
        if(jobs!=null) for(int i=0;i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            body.addView(text(j.optString("order_code")+" | "+j.optString("customer_name")
                +" | "+j.optString("device")+" | "+j.optString("status")
                +"\nوضعیت هنگام تحویل: "+j.optString("power_state")
                +"\nوضعیت فیزیکی: "+j.optString("physical_condition")
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
