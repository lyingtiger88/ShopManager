package com.shopmanager.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Typeface;
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
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(16, 20, 16, 12);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        setContentView(root);
        TextView title = text("ShopManager | ثبت‌کننده ثانویه");
        title.setTextSize(20);
        title.setTypeface(null, Typeface.BOLD);
        root.addView(title);
        status = text("");
        root.addView(status);
        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(nav);
        tab(nav,"اتصال", () -> connectionPage());
        tab(nav,"مشتریان", () -> customersPage());
        tab(nav,"پذیرش", () -> intakePage());
        tab(nav,"پرونده‌ها", () -> jobsPage());
        ScrollView scroll = new ScrollView(this);
        root.addView(scroll, new LinearLayout.LayoutParams(-1,0,1));
        body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(4,8,4,8);
        scroll.addView(body);
        status();
        connectionPage();
        if(!url().isEmpty() && !key().isEmpty()) synchronize();
    }
    private TextView text(String content) {
        TextView t = new TextView(this);
        t.setText(content); t.setTextSize(15); t.setPadding(6,8,6,8);
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
        Button b = new Button(this); b.setText(name); b.setTextSize(11);
        container.addView(b, new LinearLayout.LayoutParams(0,-2,1));
        b.setOnClickListener(v -> action.run());
    }
    private void action(String name, Runnable run) {
        Button b = new Button(this); b.setText(name); body.addView(b);
        b.setOnClickListener(v -> run.run());
    }
    private void reset(String heading) {
        body.removeAllViews();
        TextView t=text(heading); t.setTextSize(18); t.setTypeface(null, Typeface.BOLD);
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
        EditText name=field("نام مشتری","");
        EditText phone=field("تلفن","");
        EditText address=field("آدرس","");
        action("ثبت مشتری و ارسال در همگام‌سازی",()->{
            if(name.getText().toString().trim().isEmpty()){toast("نام الزامی است");return;}
            JSONObject op=new JSONObject();
            try {
                op.put("kind","customer");op.put("ref",UUID.randomUUID().toString());
                op.put("name",name.getText().toString().trim());
                op.put("phone",phone.getText().toString().trim());
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
            String category=deviceType.getSelectedItem().toString();
            JSONObject brands=deviceCatalog.optJSONObject(category);
            ArrayList<String> brandNames=new ArrayList<>();
            if(brands!=null){Iterator<String> it=brands.keys();while(it.hasNext())brandNames.add(it.next());}
            java.util.Collections.sort(brandNames);
            brandPicker.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,brandNames));
            if(!brandNames.isEmpty())brandPicker.setSelection(0);
        };
        Runnable filterModels=()->{
            JSONObject brands=deviceCatalog.optJSONObject(deviceType.getSelectedItem().toString());
            String brand=brandPicker.getSelectedItem()==null?"":brandPicker.getSelectedItem().toString();
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
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){refreshModels.run();}
        });
        modelSearch.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence a,int b,int c,int d){}
            public void onTextChanged(CharSequence a,int b,int c){filterModels.run();}
            public void afterTextChanged(android.text.Editable e){}
        });
        modelList.setOnItemClickListener((parent,view,position,id)->{
            chosenModel[0]=String.valueOf(parent.getItemAtPosition(position));
            customModel.setText("");
            selectedModel.setText("مدل انتخاب‌شده: "+chosenBrand[0]+" "+chosenModel[0]);
        });
        body.addView(text("۴) در صورت نبود مدل در فهرست، نام آن را دستی وارد کنید."));
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
                op.put("device",deviceType.getSelectedItem().toString()+" | "+chosenBrand[0]+" | "+model);
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
                pending.put(op);save();toast("پذیرش با شناسه موقت ثبت شد");intakePage();
            }catch(Exception e){toast(e.getMessage());}
        });
    }
    private void jobsPage() {
        reset("پرونده‌های مشترک");
        JSONArray jobs=snapshot.optJSONArray("jobs");
        if(jobs!=null) for(int i=0;i<jobs.length();i++){
            JSONObject j=jobs.optJSONObject(i);if(j==null)continue;
            body.addView(text(j.optString("order_code")+" | "+j.optString("customer_name")
                +" | "+j.optString("device")+" | "+j.optString("status")
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
