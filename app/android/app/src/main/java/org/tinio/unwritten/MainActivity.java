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
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.text.InputType;
import android.view.View;
import android.widget.CheckBox;
import android.widget.EditText;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
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

    // Bunny streaming (optional): settings + per-lesson link state.
    private static final String BUNNY_PREFS = "unwritten_bunny";
    private LinearLayout bunnyPanel;
    private EditText bunnySignerEdit, bunnySignerTokenEdit, bunnyLibEdit, bunnyKeyEdit;
    private Button bunnyToggleButton, bunnyShareButton;
    private File lastLessonFile;
    private final ExecutorService bunnyExec = Executors.newSingleThreadExecutor();
    private final Set<String> bunnyInFlight = new HashSet<String>();

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
        paintBunnyToggle();
        updateShareButton();
        bunnyResumePending();
        if (hasPermissions()) openPreview();
    }

    @Override protected void onPause() {
        super.onPause();
        // Leaving mid-recording stops and keeps the take.
        try { if (engine != null && engine.isRecording()) stopRecording(); } catch (Throwable ignored) {}
    }

    @Override protected void onDestroy() {
        try { bunnyExec.shutdownNow(); } catch (Throwable ignored) { }
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
                String item = getItem(pos);
                if (item != null) t.setText(item + bunnySuffix(item));
                return t;
            }
        };
        clipList = new ListView(this); clipList.setAdapter(clipAdapter); clipList.setBackgroundColor(BG);
        l.addView(clipList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(150)));

        Button exportBtn = button("Export lessons to Downloads");
        exportBtn.setBackgroundColor(AMBER); exportBtn.setTextColor(BG);
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        l.addView(exportBtn);

        l.addView(label("Bunny streaming (optional)", 17, DIM));
        bunnyToggleButton = button("☁ Bunny: off");
        bunnyToggleButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleBunnyPanel(); } });
        l.addView(bunnyToggleButton);

        bunnyPanel = new LinearLayout(this);
        bunnyPanel.setOrientation(LinearLayout.VERTICAL);
        bunnyPanel.setVisibility(View.GONE);
        bunnySignerEdit = bunnyEdit("Signer URL — recommended (app/bunny-signer)", false);
        bunnySignerTokenEdit = bunnyEdit("Signer token (only if you set one)", true);
        bunnyLibEdit = bunnyEdit("— or without a signer: Bunny library ID", false);
        bunnyKeyEdit = bunnyEdit("Library API key (then lives on this phone)", true);
        bunnyPanel.addView(bunnyFieldLabel("Signer URL")); bunnyPanel.addView(bunnySignerEdit);
        bunnyPanel.addView(bunnyFieldLabel("Signer token")); bunnyPanel.addView(bunnySignerTokenEdit);
        bunnyPanel.addView(bunnyFieldLabel("Bunny library ID")); bunnyPanel.addView(bunnyLibEdit);
        bunnyPanel.addView(bunnyFieldLabel("Library API key")); bunnyPanel.addView(bunnyKeyEdit);
        bunnyPanel.addView(label("Purely additive: lessons are saved on this phone first. With Bunny on, a copy uploads for streamed playback and the lesson gets a ▶ link. A signer holds the API key so no key lives in this app; without one, the key stays on this phone and is only sent to Bunny.", 14, DIM));
        l.addView(bunnyPanel);

        bunnyShareButton = button("Share Bunny link");
        bunnyShareButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { shareBunnyLink(); } });
        l.addView(bunnyShareButton);

        clipList.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            @Override public void onItemClick(android.widget.AdapterView<?> parent, View view, int pos, long id) {
                String name = clipNames.get(pos);
                JSONObject link = bunnyLink(name);
                if (link == null) return;
                String st = link.optString("state", "");
                if ("ready".equals(st)) {
                    String lib = link.optString("libraryId", bunnyCfgString("libraryId"));
                    String url = "https://player.mediadelivery.net/embed/" + lib + "/" + link.optString("videoId", "");
                    try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
                    catch (Throwable e) { Toast.makeText(MainActivity.this, url, Toast.LENGTH_LONG).show(); }
                } else if ("failed".equals(st)) {
                    File f = new File(clipsDir, name);
                    if (f.exists()) startBunnyUpload(f);
                } else if ("processing".equals(st)) {
                    pollBunny(name, link.optString("videoId", ""));
                    Toast.makeText(MainActivity.this, "Still preparing on Bunny…", Toast.LENGTH_SHORT).show();
                }
            }
        });

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
                lastLessonFile = f;
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
        if (lastLessonFile != null) maybeBunnyUpload(lastLessonFile);
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

    // ---------- Bunny streaming (optional) ----------

    private SharedPreferences bunnyPrefs() { return getSharedPreferences(BUNNY_PREFS, MODE_PRIVATE); }
    private String bunnyCfgString(String key) { return bunnyPrefs().getString(key, ""); }

    private EditText bunnyEdit(String hint, boolean password) {
        EditText e = new EditText(this);
        e.setHint(hint); e.setTextSize(15); e.setTextColor(TEXT); e.setHintTextColor(DIM);
        e.setBackgroundColor(PANEL); e.setSingleLine(true);
        if (password) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setPadding(dp(10), dp(8), dp(10), dp(8));
        return e;
    }
    private TextView bunnyFieldLabel(String s) { return label(s, 14, DIM); }

    private BunnyUploader bunnyUploader() {
        BunnyUploader up = new BunnyUploader(bunnyCfgString("libraryId"), bunnyCfgString("apiKey"),
                bunnyCfgString("signerUrl"), bunnyCfgString("signerToken"));
        return up.configured() ? up : null;
    }
    private boolean bunnyEnabledCfg() {
        return bunnyPrefs().getBoolean("enabled", false) && bunnyUploader() != null;
    }

    private void toggleBunnyPanel() {
        if (bunnyPrefs().getBoolean("enabled", false)) {
            bunnyPrefs().edit().putBoolean("enabled", false).apply();
            bunnyPanel.setVisibility(View.GONE);
            paintBunnyToggle();
            status.setText("☁ Bunny off. Lessons stay on this phone only, as before.");
            return;
        }
        if (bunnyPanel.getVisibility() != View.VISIBLE) {
            bunnySignerEdit.setText(bunnyCfgString("signerUrl"));
            bunnySignerTokenEdit.setText(bunnyCfgString("signerToken"));
            bunnyLibEdit.setText(bunnyCfgString("libraryId"));
            bunnyKeyEdit.setText(bunnyCfgString("apiKey"));
            bunnyPanel.setVisibility(View.VISIBLE);
            return;
        }
        String signer = bunnySignerEdit.getText().toString().trim();
        String lib = bunnyLibEdit.getText().toString().trim();
        String key = bunnyKeyEdit.getText().toString().trim();
        if (signer.isEmpty() && (lib.isEmpty() || key.isEmpty())) {
            status.setText("☁ Fill in either the signer URL, or the library ID and API key (Bunny dashboard → Stream → your library → API).");
            return;
        }
        bunnyPrefs().edit()
                .putString("signerUrl", signer)
                .putString("signerToken", bunnySignerTokenEdit.getText().toString().trim())
                .putString("libraryId", lib)
                .putString("apiKey", key)
                .putBoolean("enabled", true)
                .apply();
        bunnyPanel.setVisibility(View.GONE);
        paintBunnyToggle();
        status.setText("☁ Bunny on. New lessons will also upload for streamed playback; tap a lesson with ☁▶ to open its Watch link.");
    }

    private void paintBunnyToggle() {
        if (bunnyToggleButton == null) return;
        bunnyToggleButton.setText(bunnyEnabledCfg() ? "☁ Bunny: on" : "☁ Bunny: off");
    }

    private JSONObject bunnyLinks() {
        try { return new JSONObject(bunnyPrefs().getString("links", "{}")); }
        catch (Throwable e) { return new JSONObject(); }
    }
    private JSONObject bunnyLink(String name) {
        JSONObject l = bunnyLinks().optJSONObject(name);
        return l;
    }
    private void setBunnyLink(String name, String state, String videoId, String libraryId,
                              String uploadUrl, int progress) {
        try {
            JSONObject links = bunnyLinks();
            JSONObject cur = links.optJSONObject(name);
            if (cur == null) cur = new JSONObject();
            if (state != null) cur.put("state", state);
            if (videoId != null) cur.put("videoId", videoId);
            if (libraryId != null) cur.put("libraryId", libraryId);
            if (uploadUrl != null) cur.put("uploadUrl", uploadUrl);
            if (progress >= 0) cur.put("progress", progress);
            links.put(name, cur);
            bunnyPrefs().edit().putString("links", links.toString()).apply();
        } catch (Throwable ignored) { }
    }
    private String bunnySuffix(String name) {
        JSONObject link = bunnyLink(name);
        if (link == null) return "";
        String st = link.optString("state", "");
        if ("ready".equals(st)) return "  ☁▶";
        if ("uploading".equals(st)) return "  ☁ " + link.optInt("progress", 0) + "%";
        if ("processing".equals(st)) return "  ☁ …";
        if ("failed".equals(st)) return "  ☁ !";
        return "";
    }

    private void maybeBunnyUpload(File f) {
        if (f == null || !f.exists() || !bunnyEnabledCfg()) return;
        JSONObject link = bunnyLink(f.getName());
        String st = link == null ? "" : link.optString("state", "");
        if ("ready".equals(st)) { updateShareButton(); return; }
        if ("processing".equals(st)) { pollBunny(f.getName(), link.optString("videoId", "")); return; }
        if ("uploading".equals(st) && bunnyInFlight.contains(f.getName())) return;
        startBunnyUpload(f);
    }

    private void startBunnyUpload(final File f) {
        if (!bunnyEnabledCfg()) { Toast.makeText(this, "Turn Bunny on first.", Toast.LENGTH_SHORT).show(); return; }
        final String name = f.getName();
        synchronized (bunnyInFlight) { if (!bunnyInFlight.add(name)) return; }
        JSONObject link = bunnyLink(name);
        final String savedUrl = link == null ? null : link.optString("uploadUrl", null);
        final String savedVid = link == null ? null : link.optString("videoId", null);
        setBunnyLink(name, "uploading", savedVid, null, savedUrl, 0);
        refreshClipList();
        status.setText("☁ Uploading " + name + " to Bunny… The lesson is already saved on this phone.");
        bunnyExec.execute(new Runnable() {
            @Override public void run() {
                try {
                    final BunnyUploader up = bunnyUploader();
                    if (up == null) { bunnyFailed(name, savedVid, "Bunny settings incomplete."); return; }
                    up.upload(f, savedUrl, savedVid, new BunnyUploader.Listener() {
                        @Override public void onSession(String videoId, String uploadUrl) {
                            setBunnyLink(name, "uploading", videoId, null, uploadUrl, -1);
                        }
                        @Override public void onProgress(final long sent, final long total) {
                            final int pct = total > 0 ? (int) (sent * 100 / total) : 0;
                            setBunnyLink(name, "uploading", null, null, null, pct);
                            runOnUiThread(new Runnable() { @Override public void run() { refreshClipList(); } });
                        }
                        @Override public void onUploaded(String videoId) {
                            setBunnyLink(name, "processing", videoId, null, null, 100);
                            runOnUiThread(new Runnable() { @Override public void run() {
                                status.setText("☁ Uploaded. Bunny is preparing the streaming version…");
                                refreshClipList();
                            } });
                        }
                        @Override public void onFinished(String videoId) { bunnyFinished(name, videoId); }
                        @Override public void onFailed(String videoId, String message) { bunnyFailed(name, videoId, message); }
                    });
                } finally {
                    synchronized (bunnyInFlight) { bunnyInFlight.remove(name); }
                }
            }
        });
    }

    private void bunnyFinished(final String name, final String videoId) {
        BunnyUploader up = bunnyUploader();
        String lib = "";
        JSONObject link = bunnyLink(name);
        if (link != null) lib = link.optString("libraryId", "");
        if ((lib == null || lib.isEmpty()) && up != null && up.lastLibraryId != null && !up.lastLibraryId.isEmpty()) lib = up.lastLibraryId;
        if (lib == null || lib.isEmpty()) lib = bunnyCfgString("libraryId");
        final String url = "https://player.mediadelivery.net/embed/" + lib + "/" + videoId;
        setBunnyLink(name, "ready", videoId, lib, null, 100);
        bunnyPrefs().edit().putString("lastLink", url).putString("lastName", name).apply();
        runOnUiThread(new Runnable() { @Override public void run() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Bunny lesson link", url));
            } catch (Throwable ignored) { }
            status.setText("☁ Ready: " + name + " — ▶ Watch link copied. Tap the lesson or Share Bunny link to send it.");
            updateShareButton();
            refreshClipList();
        } });
    }

    private void bunnyFailed(final String name, String videoId, final String message) {
        setBunnyLink(name, "failed", videoId, null, null, -1);
        runOnUiThread(new Runnable() { @Override public void run() {
            status.setText("☁ Bunny didn't finish for " + name + " (" + message + ") The lesson is safe on this phone — tap it in the list to retry.");
            refreshClipList();
        } });
    }

    private final Set<String> bunnyPolling = new HashSet<String>();
    private void pollBunny(final String name, final String videoId) {
        if (videoId == null || videoId.isEmpty()) return;
        synchronized (bunnyPolling) { if (!bunnyPolling.add(name)) return; }
        bunnyExec.execute(new Runnable() {
            @Override public void run() {
                try {
                    BunnyUploader up = bunnyUploader();
                    if (up == null) return;
                    for (int i = 0; i < 120; i++) {
                        try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                        int st;
                        try { st = up.videoStatus(videoId); } catch (Throwable e) { st = -1; }
                        if (st == 4) { bunnyFinished(name, videoId); return; }
                        if (st == 5 || st == 6) { bunnyFailed(name, videoId, "Bunny encoding failed."); return; }
                    }
                } finally {
                    synchronized (bunnyPolling) { bunnyPolling.remove(name); }
                }
            }
        });
    }

    private void bunnyResumePending() {
        if (!bunnyEnabledCfg()) return;
        JSONObject links = bunnyLinks();
        java.util.Iterator<String> it = links.keys();
        while (it.hasNext()) {
            String name = it.next();
            JSONObject link = links.optJSONObject(name);
            if (link == null) continue;
            String st = link.optString("state", "");
            if ("processing".equals(st)) pollBunny(name, link.optString("videoId", ""));
            else if ("uploading".equals(st)) {
                File f = new File(clipsDir, name);
                if (f.exists()) startBunnyUpload(f);
            }
        }
    }

    private void updateShareButton() {
        if (bunnyShareButton == null) return;
        String last = bunnyPrefs().getString("lastLink", "");
        bunnyShareButton.setEnabled(last != null && !last.isEmpty());
    }

    private void shareBunnyLink() {
        String url = bunnyPrefs().getString("lastLink", "");
        String name = bunnyPrefs().getString("lastName", "lesson");
        if (url == null || url.isEmpty()) {
            Toast.makeText(this, "No Bunny link yet — record a lesson with Bunny on.", Toast.LENGTH_LONG).show();
            return;
        }
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("text/plain");
        share.putExtra(Intent.EXTRA_SUBJECT, name);
        share.putExtra(Intent.EXTRA_TEXT, url);
        startActivity(Intent.createChooser(share, "Share lesson link"));
    }
}
