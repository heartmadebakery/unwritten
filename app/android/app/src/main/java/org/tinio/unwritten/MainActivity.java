package org.tinio.unwritten;

import android.Manifest;
import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/** Unwritten Craft — Recorder. One job: record one lesson, stop, keep
 *  the file. No roles, no steps, nothing performed for the machine;
 *  the pipeline (transcribe -> write-up -> corrections) works
 *  afterwards on the single take. Video + audio go through CameraEngine
 *  (Camera2 + MediaRecorder); clips live in the app's clips folder and
 *  export to Downloads/Unwritten. */
public class MainActivity extends Activity {

    private static final int BG = Color.parseColor("#17130E");
    private static final int PANEL = Color.parseColor("#241C12");
    private static final int TEXT = Color.parseColor("#F5EAD6");
    private static final int DIM = Color.parseColor("#B8A888");
    private static final int AMBER = Color.parseColor("#E8A13A");
    private static final int RED = Color.parseColor("#C0392B");
    private static final int PERM_RECORD = 7;

    private File clipsDir;
    private final Handler handler = new Handler();

    private TextureView preview;
    private TextView status;
    private Button recordButton;
    private ListView clipList;
    private ArrayAdapter<String> clipAdapter;
    private final List<String> clipNames = new ArrayList<String>();
    private CameraEngine engine;
    private long recordStartMs;
    private boolean pendingRecord;

    private final Runnable timerRunnable = new Runnable() {
        @Override public void run() {
            if (engine != null && engine.isRecording()) {
                long s = (SystemClock.elapsedRealtime() - recordStartMs) / 1000;
                recordButton.setText("■ Stop  " + (s / 60) + ":" + String.format(Locale.US, "%02d", s % 60));
                handler.postDelayed(this, 500);
            }
        }
    };

    // ---------- helpers ----------

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    private TextView label(String text, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(text); t.setTextSize(sp); t.setTextColor(color);
        t.setPadding(dp(4), dp(4), dp(4), dp(4));
        return t;
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text); b.setTextSize(18); b.setTextColor(TEXT);
        b.setBackgroundColor(PANEL); b.setAllCaps(false);
        b.setPadding(dp(12), dp(10), dp(12), dp(10));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(4), 0, dp(4));
        b.setLayoutParams(lp);
        return b;
    }

    // ---------- lifecycle ----------

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        clipsDir = new File(getExternalFilesDir(null), "clips");
        //noinspection ResultOfMethodCallIgnored
        clipsDir.mkdirs();
        buildScreen();
        refreshClipList();
        if (hasPermissions()) openPreview();
    }

    @Override protected void onPause() {
        super.onPause();
        // Leaving mid-recording stops and keeps the take.
        try { if (engine != null && engine.isRecording()) stopRecording(); } catch (Throwable ignored) {}
    }

    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        try { if (engine != null) engine.close(); } catch (Throwable ignored) {}
        engine = null;
        super.onDestroy();
    }

    private void buildScreen() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setBackgroundColor(BG);
        l.setPadding(dp(14), dp(14), dp(14), dp(14));

        TextView title = label("Unwritten Craft — Recorder", 24, TEXT); title.setGravity(Gravity.CENTER);
        l.addView(title);
        l.addView(label("Film one lesson, the way she'd teach it anyway. Press Record, let it happen, press Stop at the end.", 16, DIM));

        preview = new TextureView(this);
        l.addView(preview, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(300)));

        status = label("Point the camera at her hands and the work.", 16, TEXT);
        l.addView(status);

        recordButton = button("● Record the lesson");
        recordButton.setBackgroundColor(RED); recordButton.setTextColor(Color.WHITE);
        recordButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleRecord(); } });
        l.addView(recordButton);

        l.addView(label("Lessons on this device", 17, DIM));
        clipAdapter = new ArrayAdapter<String>(this, android.R.layout.simple_list_item_1, clipNames) {
            @Override public View getView(int pos, View convert, ViewGroup parent) {
                TextView t = (TextView) super.getView(pos, convert, parent);
                t.setTextColor(TEXT); t.setTextSize(15); t.setBackgroundColor(BG);
                return t;
            }
        };
        clipList = new ListView(this); clipList.setAdapter(clipAdapter); clipList.setBackgroundColor(BG);
        l.addView(clipList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(150)));

        Button exportBtn = button("Export lessons to Downloads");
        exportBtn.setBackgroundColor(AMBER); exportBtn.setTextColor(BG);
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        l.addView(exportBtn);

        ScrollView sv = new ScrollView(this); sv.setBackgroundColor(BG); sv.addView(l);
        setContentView(sv);
    }

    // ---------- permissions ----------

    private boolean hasPermissions() {
        return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
            && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    @Override public void onRequestPermissionsResult(int req, String[] perms, int[] results) {
        super.onRequestPermissionsResult(req, perms, results);
        boolean granted = results.length > 0;
        for (int r : results) if (r != PackageManager.PERMISSION_GRANTED) granted = false;
        if (req == PERM_RECORD) {
            if (granted) { openPreview(); if (pendingRecord) { pendingRecord = false; toggleRecord(); } }
            else { pendingRecord = false; status.setText("Camera and microphone permission denied — cannot record the lesson."); }
        }
    }

    // ---------- recording ----------

    private void openPreview() {
        try {
            if (engine == null) engine = new CameraEngine(this, new CameraEngine.ErrorListener() {
                @Override public void onError(final String message) {
                    runOnUiThread(new Runnable() { @Override public void run() { status.setText("Camera error: " + message); } });
                }
            });
            engine.openPreview(preview);
        } catch (Throwable e) { status.setText("Camera error: " + e.getMessage()); }
    }

    private void toggleRecord() {
        if (!hasPermissions()) {
            pendingRecord = true;
            requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}, PERM_RECORD);
            return;
        }
        if (engine == null) { openPreview(); status.setText("Camera not ready yet — try again in a moment."); return; }
        try {
            if (engine.isRecording()) { stopRecording(); return; }
            File f = new File(clipsDir, Names.lessonName("mp4"));
            if (engine.startVideo(f)) {
                recordStartMs = SystemClock.elapsedRealtime();
                recordButton.setText("■ Stop  0:00");
                handler.post(timerRunnable);
                status.setText("Recording " + f.getName() + " — teach the way you'd teach anyway.");
            } else status.setText("Could not start recording.");
        } catch (Throwable e) { status.setText("Record failed: " + e.getMessage()); }
    }

    private void stopRecording() {
        try {
            if (engine != null) engine.stopVideo();
        } catch (Throwable e) { status.setText("Stop failed: " + e.getMessage()); return; }
        handler.removeCallbacks(timerRunnable);
        recordButton.setText("● Record the lesson");
        status.setText("Lesson saved. Record another, or export below.");
        refreshClipList();
    }

    // ---------- clips / files / export ----------

    private List<File> clipFiles() {
        List<File> out = new ArrayList<File>();
        if (clipsDir == null) return out;
        File[] files = clipsDir.listFiles();
        if (files == null) return out;
        for (File f : files) {
            if (f.isFile() && mimeFor(f.getName()) != null) out.add(f);
        }
        Collections.sort(out, new Comparator<File>() {
            @Override public int compare(File a, File b) { return Long.compare(b.lastModified(), a.lastModified()); }
        });
        return out;
    }

    private void refreshClipList() {
        clipNames.clear();
        for (File f : clipFiles()) clipNames.add(f.getName());
        if (clipAdapter != null) clipAdapter.notifyDataSetChanged();
    }

    private String mimeFor(String name) {
        String n = name.toLowerCase(Locale.US);
        if (n.endsWith(".mp4")) return "video/mp4";
        if (n.endsWith(".wav")) return "audio/x-wav";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".webm")) return "video/webm";
        if (n.endsWith(".mov")) return "video/quicktime";
        if (n.endsWith(".m4a")) return "audio/mp4";
        return null;
    }

    private void copyStream(InputStream in, OutputStream out) throws Exception {
        byte[] buf = new byte[8192]; int r;
        while ((r = in.read(buf)) != -1) out.write(buf, 0, r);
    }

    private void exportClips() {
        // minSdk is 29 (Pixel 4 baseline): MediaStore Downloads needs
        // no storage permission, so export is unconditional.
        doExport();
    }

    private void doExport() {
        List<File> files = clipFiles();
        if (files.isEmpty()) { Toast.makeText(this, "Exported 0 lessons to Downloads/Unwritten", Toast.LENGTH_LONG).show(); return; }
        int count = 0;
        try {
            ContentResolver cr = getContentResolver();
            for (File f : files) {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, f.getName());
                cv.put(MediaStore.Downloads.MIME_TYPE, mimeFor(f.getName()));
                cv.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Unwritten");
                cv.put(MediaStore.Downloads.IS_PENDING, 1);
                Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (uri == null) throw new Exception("MediaStore insert failed for " + f.getName());
                OutputStream out = cr.openOutputStream(uri);
                if (out == null) throw new Exception("Could not open output for " + f.getName());
                FileInputStream in = new FileInputStream(f);
                copyStream(in, out); in.close(); out.close();
                ContentValues done = new ContentValues(); done.put(MediaStore.Downloads.IS_PENDING, 0);
                cr.update(uri, done, null, null);
                count++;
            }
            Toast.makeText(this, "Exported " + count + " lessons to Downloads/Unwritten", Toast.LENGTH_LONG).show();
        } catch (Throwable e) {
            Toast.makeText(this, "Export failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
        refreshClipList();
    }
}
