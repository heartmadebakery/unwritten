package org.tinio.unwritten;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
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
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.SeekBar;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

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
    private static final int AMBER = Color.parseColor("#E8A13A"); // retained for compat, not used
    private static final int RED = Color.parseColor("#C0392B"); // retained for compat, not used
    private static final int PERM_RECORD = 7;

    private File clipsDir;
    private final Handler handler = new Handler();

    private TextureView preview;
    private TextView status;
    private Button recordButton;
    private LinearLayout lessonContainer;
    private final List<String> clipNames = new ArrayList<String>();
    private CameraEngine engine;
    private long recordStartMs;
    private boolean pendingRecord;
    private android.widget.VideoView localPlayer;
    private android.widget.FrameLayout viewfinderBox;
    private LinearLayout playerControls;
    private boolean isViewfinderPlaying = false;

    // Cloud streaming (on by default, prefilled at build time): per-lesson link state.
    private static final String CLOUD_PREFS = "unwritten_cloud";
    private static final String CLOUD_SIGNER_DEFAULT = "https://unwritten-cloud-signer.heartmade.workers.dev";
    private Button cloudToggleButton, exportBtn;
    private TextView zoomLabel;
    private SeekBar zoomSeek;
    private File lastLessonFile;
    private final ExecutorService cloudExec = Executors.newCachedThreadPool();
    private final Set<String> cloudInFlight = new HashSet<String>();

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
        try { b.setBackgroundTintList(null); } catch (Throwable ignored) {}
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
        // Allow file:// playback intents on Android 7+ without a FileProvider (simple recorder, external player).
        try { android.os.StrictMode.setVmPolicy(new android.os.StrictMode.VmPolicy.Builder().build()); } catch (Throwable ignored) {}
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        clipsDir = new File(getExternalFilesDir(null), "clips");
        //noinspection ResultOfMethodCallIgnored
        clipsDir.mkdirs();
        buildScreen();
        refreshClipList();
        migrateCloudPrefs();
        paintCloudToggle();
        cloudResumePending();
        if (hasPermissions()) openPreview();
    }

    @Override protected void onPause() {
        super.onPause();
        // Leaving mid-recording stops and keeps the take.
        try { if (engine != null && engine.isRecording()) stopRecording(); } catch (Throwable ignored) {}
    }

    @Override protected void onDestroy() {
        try { cloudExec.shutdownNow(); } catch (Throwable ignored) { }
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

        TextView title = label("Unwritten Craft", 24, TEXT); title.setGravity(Gravity.CENTER);
        l.addView(title);
        l.addView(label("Film mentor session. Record and let it happen.", 16, DIM));

        // Viewfinder with in-player overlay (playback appears inside viewfinder)
        viewfinderBox = new android.widget.FrameLayout(this);
        preview = new TextureView(this);
        viewfinderBox.addView(preview, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(280)));
        localPlayer = new android.widget.VideoView(this);
        localPlayer.setVisibility(View.GONE);
        viewfinderBox.addView(localPlayer, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(280)));
        // playback controls overlay at bottom of viewfinder
        playerControls = new LinearLayout(this);
        playerControls.setOrientation(LinearLayout.HORIZONTAL);
        playerControls.setGravity(Gravity.CENTER);
        playerControls.setBackgroundColor(Color.parseColor("#AA000000"));
        playerControls.setVisibility(View.GONE);
        playerControls.setPadding(dp(6), dp(4), dp(6), dp(4));
        Button vfPlay = new Button(this);
        vfPlay.setText("▶"); vfPlay.setTextSize(14); vfPlay.setTextColor(TEXT); vfPlay.setBackgroundColor(PANEL); vfPlay.setAllCaps(false);
        try { vfPlay.setBackgroundTintList(null); } catch (Throwable ignored) {}
        vfPlay.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (localPlayer != null && isViewfinderPlaying) localPlayer.start(); } });
        Button vfPause = new Button(this);
        vfPause.setText("⏸"); vfPause.setTextSize(14); vfPause.setTextColor(TEXT); vfPause.setBackgroundColor(PANEL); vfPause.setAllCaps(false);
        try { vfPause.setBackgroundTintList(null); } catch (Throwable ignored) {}
        vfPause.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (localPlayer != null) localPlayer.pause(); } });
        LinearLayout.LayoutParams vfp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        vfp.setMargins(dp(4), 0, dp(4), 0);
        vfPlay.setLayoutParams(vfp); vfPause.setLayoutParams(vfp);
        playerControls.addView(vfPlay); playerControls.addView(vfPause);
        android.widget.FrameLayout.LayoutParams ctrlLp = new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ctrlLp.gravity = Gravity.BOTTOM;
        viewfinderBox.addView(playerControls, ctrlLp);
        l.addView(viewfinderBox, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        // Zoom directly below viewfinder
        LinearLayout zoomRow = new LinearLayout(this);
        zoomRow.setOrientation(LinearLayout.HORIZONTAL);
        zoomRow.setGravity(Gravity.CENTER_VERTICAL);
        zoomRow.setPadding(0, dp(6), 0, dp(6));
        Button zoomOut = button("−");
        zoomOut.setTextSize(18);
        LinearLayout.LayoutParams zp = new LinearLayout.LayoutParams(dp(48), ViewGroup.LayoutParams.WRAP_CONTENT);
        zoomOut.setLayoutParams(zp);
        zoomSeek = new SeekBar(this);
        zoomSeek.setMax(100);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        zoomSeek.setLayoutParams(sp);
        Button zoomIn = button("+");
        zoomIn.setTextSize(18);
        zoomIn.setLayoutParams(zp);
        zoomLabel = label("1.0×", 14, DIM);
        zoomLabel.setMinWidth(dp(48));
        zoomLabel.setGravity(Gravity.CENTER);
        zoomRow.addView(zoomOut);
        zoomRow.addView(zoomSeek);
        zoomRow.addView(zoomIn);
        zoomRow.addView(zoomLabel);
        l.addView(zoomRow);
        zoomOut.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(-0.2f); } });
        zoomIn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(+0.2f); } });
        zoomSeek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean fromUser) { if (fromUser) applyZoomFromSlider(); }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });

        status = label("", 16, TEXT); // hidden - status conveyed via list icons
        recordButton = button("● Record");
        recordButton.setBackgroundColor(PANEL); recordButton.setTextColor(TEXT);
        try { recordButton.setBackgroundTintList(null); } catch (Throwable ignored) {}
        recordButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleRecord(); } });
        l.addView(recordButton);

        // Cloud toggle directly below Record
        cloudToggleButton = button("☁ Cloud: on");
        try { cloudToggleButton.setBackgroundTintList(null); } catch (Throwable ignored) {}
        cloudToggleButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleCloudEnabled(); } });
        l.addView(cloudToggleButton);

        exportBtn = button("Export sessions to Downloads");
        exportBtn.setBackgroundColor(PANEL); exportBtn.setTextColor(TEXT);
        try { exportBtn.setBackgroundTintList(null); } catch (Throwable ignored) {}
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        l.addView(exportBtn);

        // Sessions at bottom: left icon (☁/device), middle date+duration, right share/download
        l.addView(label("Sessions", 17, DIM));
        lessonContainer = new LinearLayout(MainActivity.this);
        lessonContainer.setOrientation(LinearLayout.VERTICAL);
        lessonContainer.setBackgroundColor(BG);
        l.addView(lessonContainer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView sv = new ScrollView(MainActivity.this); sv.setBackgroundColor(BG); sv.addView(l);
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
            else { pendingRecord = false; if (status != null) status.setText("Camera and microphone permission denied."); }
        }
    }

    // ---------- recording ----------

    private void openPreview() {
        try {
            if (engine == null) engine = new CameraEngine(this, new CameraEngine.ErrorListener() {
                @Override public void onError(final String message) {
                    runOnUiThread(new Runnable() { @Override public void run() { if (status != null) status.setText("Camera error: " + message); } });
                }
            });
            engine.openPreview(preview);
            handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); }}, 1200);
            handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); }}, 2500);
        } catch (Throwable e) { if (status != null) status.setText("Camera error: " + e.getMessage()); }
    }

    private void toggleRecord() {
        if (!hasPermissions()) {
            pendingRecord = true;
            requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}, PERM_RECORD);
            return;
        }
        if (engine == null) { openPreview(); if (status != null) status.setText("Camera not ready yet — try again in a moment."); return; }
        // auto-close viewfinder playback if a recording begins
        if (isViewfinderPlaying) stopLocalPlayback();
        try {
            if (engine.isRecording()) { stopRecording(); return; }
            File f = new File(clipsDir, Names.lessonName("mp4"));
            if (engine.startVideo(f)) {
                lastLessonFile = f;
                recordStartMs = SystemClock.elapsedRealtime();
                recordButton.setText("■ Stop  0:00");
                handler.post(timerRunnable);
            } else if (status != null) status.setText("Could not start recording.");
        } catch (Throwable e) { if (status != null) status.setText("Record failed: " + e.getMessage()); }
    }

    private void stopRecording() {
        try {
            if (engine != null) engine.stopVideo();
        } catch (Throwable e) { if (status != null) status.setText("Stop failed: " + e.getMessage()); return; }
        handler.removeCallbacks(timerRunnable);
        recordButton.setText("● Record");
        refreshClipList();
        if (lastLessonFile != null) maybeCloudUpload(lastLessonFile);
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

    // left icon: ☁ if cloud-backed (has cloud link), otherwise phone 📱
    private String leftIconFor(String name) {
        JSONObject link = cloudLink(name);
        if (link == null) return "\uD83D\uDCF1"; // 📱 device-only
        String st = link.optString("state", "");
        if ("uploading".equals(st)) return "\u2601\u2191"; // ☁↑
        if ("processing".equals(st)) return "\u2601\u2026"; // ☁…
        if ("failed".equals(st)) return "\u2601!"; // ☁!
        return "\u2601"; // ☁ ready/other
    }

    private String displayDateFor(String name) {
        try {
            // unwritten_lesson_20261029-064439-473.mp4 -> 20261029-064439
            String base = name;
            int us = base.lastIndexOf('_');
            if (us >= 0) base = base.substring(us + 1);
            int dot = base.lastIndexOf('.');
            if (dot > 0) base = base.substring(0, dot);
            if (base.length() >= 15) base = base.substring(0, 15); // yyyyMMdd-HHmmss
            java.text.SimpleDateFormat src = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US);
            java.util.Date d = src.parse(base);
            java.text.SimpleDateFormat dst = new java.text.SimpleDateFormat("MMM d, yyyy HH:mm", Locale.US);
            return dst.format(d);
        } catch (Throwable e) {
            return name;
        }
    }

    private final Map<String,String> durationCache = new java.util.HashMap<String,String>();
    private String durationFor(String name) {
        if (durationCache.containsKey(name)) return durationCache.get(name);
        String out = "";
        try {
            File f = new File(clipsDir, name);
            android.media.MediaMetadataRetriever mmr = new android.media.MediaMetadataRetriever();
            mmr.setDataSource(f.getAbsolutePath());
            String dur = mmr.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_DURATION);
            mmr.release();
            if (dur != null) {
                long ms = Long.parseLong(dur);
                long s = ms / 1000;
                long m = s / 60;
                long h = m / 60;
                s = s % 60; m = m % 60;
                if (h > 0) out = String.format(Locale.US, "%d:%02d:%02d", h, m, s);
                else out = String.format(Locale.US, "%d:%02d", m, s);
            }
        } catch (Throwable ignored) {}
        durationCache.put(name, out);
        return out;
    }

    private void downloadSingle(String name) {
        File f = new File(clipsDir, name);
        if (!f.exists()) { Toast.makeText(this, "File missing.", Toast.LENGTH_SHORT).show(); return; }
        try {
            ContentResolver cr = getContentResolver();
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.Downloads.DISPLAY_NAME, f.getName());
            cv.put(MediaStore.Downloads.MIME_TYPE, mimeFor(f.getName()));
            cv.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Unwritten");
            cv.put(MediaStore.Downloads.IS_PENDING, 1);
            Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new Exception("MediaStore insert failed");
            OutputStream out = cr.openOutputStream(uri);
            if (out == null) throw new Exception("Could not open output");
            FileInputStream in = new FileInputStream(f);
            copyStream(in, out); in.close(); out.close();
            ContentValues done = new ContentValues(); done.put(MediaStore.Downloads.IS_PENDING, 0);
            cr.update(uri, done, null, null);
            Toast.makeText(this, "Saved " + f.getName() + " to Downloads/Unwritten", Toast.LENGTH_LONG).show();
        } catch (Throwable e) {
            Toast.makeText(this, "Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void refreshClipList() {
        clipNames.clear();
        for (File f : clipFiles()) clipNames.add(f.getName());
        if (lessonContainer == null) return;
        lessonContainer.removeAllViews();
        for (final String name : clipNames) {
            File file = new File(clipsDir, name);
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setBackgroundColor(BG);
            row.setPadding(dp(8), dp(6), dp(8), dp(6));

            // left: cloud/device icon
            TextView left = label(leftIconFor(name), 16, TEXT);
            left.setMinWidth(dp(32)); left.setGravity(Gravity.CENTER);
            row.addView(left);

            // middle: date + duration (click to play in viewfinder)
            String date = displayDateFor(name);
            String dur = durationFor(name);
            String middleText = dur.isEmpty() ? date : date + "  \u2022  " + dur;
            TextView mid = new TextView(this);
            mid.setText(middleText);
            mid.setTextColor(TEXT); mid.setTextSize(15); mid.setSingleLine(true);
            mid.setPadding(dp(8), 0, dp(8), 0);
            LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            mid.setLayoutParams(mp);
            mid.setClickable(true);
            row.addView(mid);
            // whole row (including left icon) plays in viewfinder; right button is separate
            row.setClickable(true);
            View.OnClickListener playClick = new View.OnClickListener() { @Override public void onClick(View v) { playInViewfinder(name); } };
            row.setOnClickListener(playClick);
            mid.setOnClickListener(playClick);
            left.setOnClickListener(playClick);

            // right: share icon if cloud ready, download icon if device-only, otherwise status
            JSONObject link = cloudLink(name);
            String st = link == null ? "" : link.optString("state", "");
            boolean isReady = "ready".equals(st);
            if (link == null) {
                // device-only: simple down arrow, no background
                TextView dl = new TextView(this);
                dl.setText("\u2193"); // ↓ simple down arrow
                dl.setTextSize(20);
                dl.setTextColor(DIM);
                dl.setGravity(Gravity.CENTER);
                dl.setPadding(dp(6), dp(4), dp(6), dp(4));
                LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                bp.setMargins(dp(8), 0, 0, 0);
                dl.setLayoutParams(bp);
                dl.setClickable(true);
                dl.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
                row.addView(dl);
            } else if (isReady) {
                TextView sh = new TextView(this);
                sh.setText("\u2197"); // ↗ cloud ready
                sh.setTextSize(20);
                sh.setTextColor(TEXT);
                sh.setBackgroundColor(PANEL);
                try { sh.setBackgroundTintList(null); } catch (Throwable ignored) {}
                sh.setGravity(Gravity.CENTER);
                sh.setPadding(dp(6), dp(4), dp(6), dp(4));
                LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                bp.setMargins(dp(8), 0, 0, 0);
                sh.setLayoutParams(bp);
                sh.setClickable(true);
                sh.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLinkFor(name); } });
                row.addView(sh);
            } else {
                // uploading: show progress %; processing: show share; failed: !
                if ("uploading".equals(st)) {
                    String badge = link.optInt("progress", 0) + "%";
                    TextView stv = label(badge, 13, DIM);
                    stv.setPadding(dp(8), 0, 0, 0);
                    LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                    bp.setMargins(dp(8), 0, 0, 0);
                    stv.setGravity(Gravity.CENTER);
                    stv.setLayoutParams(bp);
                    row.addView(stv);
                } else if ("processing".equals(st)) {
                    String vid = link.optString("videoId", "");
                    if (!vid.isEmpty()) {
                        TextView sh = new TextView(this);
                        sh.setText("\u2197");
                        sh.setTextSize(20);
                        sh.setTextColor(DIM);
                        sh.setBackgroundColor(PANEL);
                        try { sh.setBackgroundTintList(null); } catch (Throwable ignored) {}
                        sh.setGravity(Gravity.CENTER);
                        sh.setPadding(dp(6), dp(4), dp(6), dp(4));
                        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                        bp.setMargins(dp(8), 0, 0, 0);
                        sh.setLayoutParams(bp);
                        sh.setClickable(true);
                        sh.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLinkFor(name); } });
                        row.addView(sh);
                    } else {
                        TextView stv = label("\u2026", 13, DIM);
                        stv.setPadding(dp(8), 0, 0, 0);
                        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                        bp.setMargins(dp(8), 0, 0, 0);
                        stv.setGravity(Gravity.CENTER);
                        stv.setLayoutParams(bp);
                        row.addView(stv);
                    }
                } else if ("failed".equals(st)) {
                    TextView stv = label("!", 13, DIM);
                    stv.setPadding(dp(8), 0, 0, 0);
                    LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
                    bp.setMargins(dp(8), 0, 0, 0);
                    stv.setGravity(Gravity.CENTER);
                    stv.setLayoutParams(bp);
                    row.addView(stv);
                }
            }

            // long-press row to delete — also on children so anywhere on row triggers it
            View.OnLongClickListener longDelete = new View.OnLongClickListener() {
                @Override public boolean onLongClick(View v) { confirmDeleteLesson(name); return true; }
            };
            row.setOnLongClickListener(longDelete);
            mid.setOnLongClickListener(longDelete);
            left.setOnLongClickListener(longDelete);

            lessonContainer.addView(row);
            View divider = new View(this);
            divider.setBackgroundColor(Color.parseColor("#2E2213"));
            lessonContainer.addView(divider, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1));
        }
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
        if (files.isEmpty()) { Toast.makeText(this, "Exported 0 sessions to Downloads/Unwritten", Toast.LENGTH_LONG).show(); return; }
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
            Toast.makeText(this, "Exported " + count + " sessions to Downloads/Unwritten", Toast.LENGTH_LONG).show();
        } catch (Throwable e) {
            Toast.makeText(this, "Export failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
        refreshClipList();
    }

    // ---------- Cloud streaming (optional) ----------

    private SharedPreferences cloudPrefs() { return getSharedPreferences(CLOUD_PREFS, MODE_PRIVATE); }
    private void migrateCloudPrefs() {
        // One-time move from the pre-rename store: the legacy release's
        // keys are adopted, then the legacy store is cleared.
        try {
            SharedPreferences legacy = getSharedPreferences("unwritten_bunny", MODE_PRIVATE); // legacy store name
            if (legacy.getAll().isEmpty()) return;
            SharedPreferences.Editor e = cloudPrefs().edit();
            for (Map.Entry<String, ?> en : legacy.getAll().entrySet()) {
                Object v = en.getValue();
                if (v instanceof Boolean) e.putBoolean(en.getKey(), (Boolean) v);
                else if (v != null) e.putString(en.getKey(), String.valueOf(v));
            }
            e.apply();
            legacy.edit().clear().apply();
        } catch (Throwable ignored) { }
    }
    private String cloudCfgString(String key) { return cloudPrefs().getString(key, ""); }

    private String cloudEffSignerUrl() {
        String s = cloudCfgString("signerUrl");
        return s.isEmpty() ? CLOUD_SIGNER_DEFAULT : s;
    }
    private String cloudEffSignerToken() {
        String t = cloudCfgString("signerToken");
        return t.isEmpty() ? CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT : t;
    }
    private CloudUploader cloudUploader() {
        CloudUploader up = new CloudUploader(cloudCfgString("libraryId"), cloudCfgString("apiKey"),
                cloudEffSignerUrl(), cloudEffSignerToken());
        return up.configured() ? up : null;
    }
    private boolean cloudEnabledCfg() {
        return cloudPrefs().getBoolean("enabled", true) && cloudUploader() != null;
    }

    private void toggleCloudEnabled() {
        boolean on = !cloudPrefs().getBoolean("enabled", true);
        cloudPrefs().edit().putBoolean("enabled", on).apply();
        paintCloudToggle();
        applyCloudDependentVisibility();
    }

    private void applyCloudDependentVisibility() {
        boolean on = cloudEnabledCfg();
        if (exportBtn != null) exportBtn.setVisibility(on ? View.GONE : View.VISIBLE);
        refreshClipList();
    }

    private void paintCloudToggle() {
        if (cloudToggleButton == null) return;
        cloudToggleButton.setText(cloudEnabledCfg() ? "☁ Cloud: on" : "☁ Cloud: off");
        applyCloudDependentVisibility();
    }

    private void playInViewfinder(String name) {
        File f = new File(clipsDir, name);
        if (!f.exists()) { Toast.makeText(this, "File missing.", Toast.LENGTH_SHORT).show(); return; }
        try {
            if (localPlayer != null && viewfinderBox != null && preview != null) {
                preview.setVisibility(View.INVISIBLE);
                localPlayer.setVisibility(View.VISIBLE);
                if (playerControls != null) playerControls.setVisibility(View.VISIBLE);
                isViewfinderPlaying = true;
                localPlayer.setOnPreparedListener(new android.media.MediaPlayer.OnPreparedListener() {
                    @Override public void onPrepared(android.media.MediaPlayer mp) { localPlayer.start(); }
                });
                localPlayer.setOnErrorListener(new android.media.MediaPlayer.OnErrorListener() {
                    @Override public boolean onError(android.media.MediaPlayer mp, int what, int extra) {
                        Toast.makeText(MainActivity.this, "Playback failed — trying external player…", Toast.LENGTH_SHORT).show();
                        fallbackExternalPlay(f, name);
                        return true;
                    }
                });
                localPlayer.setOnCompletionListener(new android.media.MediaPlayer.OnCompletionListener() {
                    @Override public void onCompletion(android.media.MediaPlayer mp) { stopLocalPlayback(); }
                });
                localPlayer.setVideoPath(f.getAbsolutePath());
                localPlayer.requestFocus();
                return;
            }
        } catch (Throwable ignored) { }
        fallbackExternalPlay(f, name);
    }

    // legacy alias for old call sites
    private void playLocalLesson(String name) { playInViewfinder(name); }

    private void fallbackExternalPlay(File f, String name) {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW);
            Uri uri = Uri.fromFile(f);
            String mime = mimeFor(name);
            if (mime == null) mime = "video/*";
            i.setDataAndType(uri, mime);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(Intent.createChooser(i, "Play session"));
        } catch (Throwable e) {
            Toast.makeText(this, "No player for " + name + " (" + e.getMessage() + ")", Toast.LENGTH_LONG).show();
        }
    }

    private void stopLocalPlayback() {
        try { if (localPlayer != null) { localPlayer.stopPlayback(); localPlayer.setVisibility(View.GONE); } } catch (Throwable ignored) {}
        try { if (preview != null) preview.setVisibility(View.VISIBLE); } catch (Throwable ignored) {}
        if (playerControls != null) playerControls.setVisibility(View.GONE);
        isViewfinderPlaying = false;
    }

    @Override public void onBackPressed() {
        if (isViewfinderPlaying) { stopLocalPlayback(); return; }
        super.onBackPressed();
    }

    private String cloudWatchUrl(String name) {
        JSONObject link = cloudLink(name);
        if (link == null) return null;
        String vid = link.optString("videoId", "");
        if (vid.isEmpty()) return null;
        String lib = link.optString("libraryId", "");
        if (lib == null || lib.isEmpty()) lib = cloudCfgString("libraryId");
        if (lib == null || lib.isEmpty()) {
            CloudUploader up = cloudUploader();
            if (up != null && up.lastLibraryId != null) lib = up.lastLibraryId;
        }
        if (lib == null || lib.isEmpty()) return null;
        return "https://player.mediadelivery.net/embed/" + lib + "/" + vid;
    }

    private void shareCloudLinkFor(String name) {
        String url = cloudWatchUrl(name);
        if (url == null) {
            // fallback to lastLink
            url = cloudPrefs().getString("lastLink", "");
            if (url == null || url.isEmpty()) {
                Toast.makeText(this, "No Cloud link yet for this session.", Toast.LENGTH_LONG).show();
                return;
            }
        }
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("text/plain");
        share.putExtra(Intent.EXTRA_SUBJECT, name);
        share.putExtra(Intent.EXTRA_TEXT, url);
        startActivity(Intent.createChooser(share, "Share session link"));
    }

    private JSONObject cloudLinks() {
        try { return new JSONObject(cloudPrefs().getString("links", "{}")); }
        catch (Throwable e) { return new JSONObject(); }
    }
    private JSONObject cloudLink(String name) {
        JSONObject l = cloudLinks().optJSONObject(name);
        return l;
    }
    private void delCloudLink(String name) {
        try {
            JSONObject links = cloudLinks();
            if (links.optJSONObject(name) != null) {
                links.remove(name);
                cloudPrefs().edit().putString("links", links.toString()).apply();
            }
        } catch (Throwable ignored) { }
    }
    private void confirmDeleteLesson(final String name) {
        new AlertDialog.Builder(this)
                .setTitle("Delete session?")
                .setMessage("Delete '" + name + "' from this phone and the cloud?")
                .setPositiveButton("Delete", new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        deleteLesson(name);
                    }
                })
                .setNegativeButton("Keep", null)
                .show();
    }
    private void deleteLesson(final String name) {
        cloudExec.execute(new Runnable() {
            @Override public void run() {
                final JSONObject link = cloudLink(name);
                final String videoId = link == null ? "" : link.optString("videoId", "");
                final String savedLastName = cloudPrefs().getString("lastName", "");
                if (!videoId.isEmpty()) {
                    try {
                        CloudUploader up = cloudUploader();
                        if (up == null) throw new IOException("Cloud settings incomplete.");
                        android.util.Log.i("UWCloud", "deleteLesson cloud delete videoId=" + videoId + " file=" + name);
                        up.deleteVideo(videoId);
                        android.util.Log.i("UWCloud", "deleteLesson cloud delete ok videoId=" + videoId);
                    } catch (final Exception e) {
                        android.util.Log.e("UWCloud", "deleteLesson cloud delete failed videoId=" + videoId, e);
                        runOnUiThread(new Runnable() { @Override public void run() {
                            if (status != null) status.setText("☁ Couldn't delete the cloud copy (" + e.getMessage() + ")");
                            Toast.makeText(MainActivity.this, "Cloud delete failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                        } });
                        return;
                    }
                } else {
                    android.util.Log.i("UWCloud", "deleteLesson local-only file=" + name);
                }
                boolean deleted = new File(clipsDir, name).delete();
                android.util.Log.i("UWCloud", "deleteLesson local delete file=" + name + " ok=" + deleted);
                delCloudLink(name);
                synchronized (cloudInFlight) { cloudInFlight.remove(name); }
                synchronized (cloudPolling) { cloudPolling.remove(name); }
                if (name.equals(savedLastName))
                    cloudPrefs().edit().remove("lastLink").remove("lastName").apply();
                if (lastLessonFile != null && name.equals(lastLessonFile.getName())) lastLessonFile = null;
                runOnUiThread(new Runnable() { @Override public void run() {
                    refreshClipList();
                    Toast.makeText(MainActivity.this, "Session deleted" + (videoId.isEmpty() ? "" : " from device and cloud"), Toast.LENGTH_SHORT).show();
                } });
            }
        });
    }
    private void setCloudLink(String name, String state, String videoId, String libraryId,
                              String uploadUrl, int progress) {
        try {
            JSONObject links = cloudLinks();
            JSONObject cur = links.optJSONObject(name);
            if (cur == null) cur = new JSONObject();
            if (state != null) cur.put("state", state);
            if (videoId != null) cur.put("videoId", videoId);
            if (libraryId != null) cur.put("libraryId", libraryId);
            if (uploadUrl != null) cur.put("uploadUrl", uploadUrl);
            if (progress >= 0) cur.put("progress", progress);
            links.put(name, cur);
            cloudPrefs().edit().putString("links", links.toString()).apply();
        } catch (Throwable ignored) { }
    }
    private String cloudSuffix(String name) {
        JSONObject link = cloudLink(name);
        if (link == null) return "";
        String st = link.optString("state", "");
        if ("ready".equals(st)) return "  ☁▶";
        if ("uploading".equals(st)) return "  ☁ " + link.optInt("progress", 0) + "%";
        if ("processing".equals(st)) return "  ☁ …";
        if ("failed".equals(st)) return "  ☁ !";
        return "";
    }

    private void maybeCloudUpload(File f) {
        if (f == null || !f.exists() || !cloudEnabledCfg()) return;
        JSONObject link = cloudLink(f.getName());
        String st = link == null ? "" : link.optString("state", "");
        if ("ready".equals(st)) return;
        if ("processing".equals(st)) { pollCloud(f.getName(), link.optString("videoId", "")); return; }
        if ("uploading".equals(st) && cloudInFlight.contains(f.getName())) return;
        startCloudUpload(f);
    }

    private void startCloudUpload(final File f) {
        if (!cloudEnabledCfg()) { Toast.makeText(this, "Turn Cloud on first.", Toast.LENGTH_SHORT).show(); return; }
        final String name = f.getName();
        synchronized (cloudInFlight) { if (!cloudInFlight.add(name)) return; }
        JSONObject link = cloudLink(name);
        final String savedUrl = link == null ? null : link.optString("uploadUrl", null);
        final String savedVid = link == null ? null : link.optString("videoId", null);
        setCloudLink(name, "uploading", savedVid, null, savedUrl, 0);
        refreshClipList();
        cloudExec.execute(new Runnable() {
            @Override public void run() {
                try {
                    final CloudUploader up = cloudUploader();
                    if (up == null) { cloudFailed(name, savedVid, "Cloud settings incomplete."); return; }
                    up.upload(f, savedUrl, savedVid, new CloudUploader.Listener() {
                        @Override public void onSession(String videoId, String uploadUrl) {
                            setCloudLink(name, "uploading", videoId, null, uploadUrl, -1);
                        }
                        @Override public void onProgress(final long sent, final long total) {
                            final int pct = total > 0 ? (int) (sent * 100 / total) : 0;
                            setCloudLink(name, "uploading", null, null, null, pct);
                            runOnUiThread(new Runnable() { @Override public void run() { refreshClipList(); } });
                        }
                        @Override public void onUploaded(String videoId) {
                            setCloudLink(name, "processing", videoId, null, null, 100);
                            runOnUiThread(new Runnable() { @Override public void run() {
                                refreshClipList();
                            } });
                        }
                        @Override public void onFinished(String videoId) { cloudFinished(name, videoId); }
                        @Override public void onFailed(String videoId, String message) { cloudFailed(name, videoId, message); }
                    });
                } finally {
                    synchronized (cloudInFlight) { cloudInFlight.remove(name); }
                }
            }
        });
    }

    private void cloudFinished(final String name, final String videoId) {
        CloudUploader up = cloudUploader();
        String lib = "";
        JSONObject link = cloudLink(name);
        if (link != null) lib = link.optString("libraryId", "");
        if ((lib == null || lib.isEmpty()) && up != null && up.lastLibraryId != null && !up.lastLibraryId.isEmpty()) lib = up.lastLibraryId;
        if (lib == null || lib.isEmpty()) lib = cloudCfgString("libraryId");
        final String url = "https://player.mediadelivery.net/embed/" + lib + "/" + videoId;
        setCloudLink(name, "ready", videoId, lib, null, 100);
        cloudPrefs().edit().putString("lastLink", url).putString("lastName", name).apply();
        runOnUiThread(new Runnable() { @Override public void run() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Cloud session link", url));
            } catch (Throwable ignored) { }
            refreshClipList();
        } });
    }

    private void cloudFailed(final String name, String videoId, final String message) {
        setCloudLink(name, "failed", videoId, null, null, -1);
        runOnUiThread(new Runnable() { @Override public void run() {
            refreshClipList();
        } });
    }

    private final Set<String> cloudPolling = new HashSet<String>();
    private void pollCloud(final String name, final String videoId) {
        if (videoId == null || videoId.isEmpty()) return;
        synchronized (cloudPolling) { if (!cloudPolling.add(name)) return; }
        cloudExec.execute(new Runnable() {
            @Override public void run() {
                try {
                    CloudUploader up = cloudUploader();
                    if (up == null) return;
                    for (int i = 0; i < 120; i++) {
                        try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                        int st;
                        try { st = up.videoStatus(videoId); } catch (Throwable e) { st = -1; }
                        if (st == 4) { cloudFinished(name, videoId); return; }
                        if (st == 5 || st == 6) { cloudFailed(name, videoId, "Cloud encoding failed."); return; }
                    }
                } finally {
                    synchronized (cloudPolling) { cloudPolling.remove(name); }
                }
            }
        });
    }

    private void cloudResumePending() {
        if (!cloudEnabledCfg()) return;
        JSONObject links = cloudLinks();
        java.util.Iterator<String> it = links.keys();
        while (it.hasNext()) {
            String name = it.next();
            JSONObject link = links.optJSONObject(name);
            if (link == null) continue;
            String st = link.optString("state", "");
            if ("processing".equals(st)) pollCloud(name, link.optString("videoId", ""));
            else if ("uploading".equals(st)) {
                File f = new File(clipsDir, name);
                if (f.exists()) startCloudUpload(f);
            }
        }
    }

    // legacy global share removed — per-lesson share via shareCloudLinkFor() / cloudWatchUrl()

    // ---------- Zoom ----------
    private void nudgeZoom(float delta) {
        if (engine == null) return;
        float max = engine.getMaxZoom();
        float cur = engine.getZoom();
        float next = Math.max(1.0f, Math.min(max, cur + delta));
        engine.setZoom(next);
        syncZoomUi(next, max);
    }
    private void applyZoomFromSlider() {
        if (engine == null || zoomSeek == null) return;
        float max = engine.getMaxZoom();
        float ratio = 1.0f + (zoomSeek.getProgress() / 100f) * (max - 1.0f);
        engine.setZoom(ratio);
        syncZoomUi(ratio, max);
    }
    private void syncZoomUi(float ratio, float max) {
        if (zoomLabel != null) zoomLabel.setText(String.format(Locale.US, "%.1f×", ratio));
        if (zoomSeek != null && max > 1.0f) {
            int p = Math.round((ratio - 1.0f) / (max - 1.0f) * 100f);
            if (Math.abs(zoomSeek.getProgress() - p) > 1) zoomSeek.setProgress(p);
        }
    }
    private void refreshZoomUi() {
        if (engine == null || zoomSeek == null) return;
        float max = engine.getMaxZoom();
        float cur = engine.getZoom();
        syncZoomUi(cur, max);
        zoomSeek.setEnabled(max > 1.0f);
    }
}
