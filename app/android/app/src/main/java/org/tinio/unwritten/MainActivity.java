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
import android.text.InputType;
import android.view.View;
import android.widget.CheckBox;
import android.widget.EditText;

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

    // Cloud streaming (optional): settings + per-lesson link state.
    private static final String CLOUD_PREFS = "unwritten_cloud";
    private static final String CLOUD_SIGNER_DEFAULT = "https://unwritten-cloud-signer.heartmade.workers.dev";
    private LinearLayout cloudPanel;
    private EditText cloudSignerEdit, cloudSignerTokenEdit, cloudLibEdit, cloudKeyEdit;
    private Button cloudToggleButton, cloudShareButton;
    private File lastLessonFile;
    private final ExecutorService cloudExec = Executors.newSingleThreadExecutor();
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
        migrateCloudPrefs();
        paintCloudToggle();
        updateShareButton();
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

        TextView title = label("Unwritten Craft — Recorder", 24, TEXT); title.setGravity(Gravity.CENTER);
        l.addView(title);
        l.addView(label("Film one lesson, the way the mentor would teach it anyway. Press Record, let it happen, press Stop at the end.", 16, DIM));

        preview = new TextureView(this);
        l.addView(preview, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(300)));

        status = label("Point the camera at the mentor's hands and the work.", 16, TEXT);
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
                if (item != null) t.setText(item + cloudSuffix(item));
                return t;
            }
        };
        clipList = new ListView(this); clipList.setAdapter(clipAdapter); clipList.setBackgroundColor(BG);
        l.addView(clipList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(150)));

        Button exportBtn = button("Export lessons to Downloads");
        exportBtn.setBackgroundColor(AMBER); exportBtn.setTextColor(BG);
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        l.addView(exportBtn);

        l.addView(label("Cloud streaming", 17, DIM));
        cloudToggleButton = button("☁ Cloud: on");
        cloudToggleButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleCloudEnabled(); } });
        l.addView(cloudToggleButton);
        Button cloudSettingsButton = button("⚙ Cloud settings");
        cloudSettingsButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleCloudPanel(); } });
        l.addView(cloudSettingsButton);

        cloudPanel = new LinearLayout(this);
        cloudPanel.setOrientation(LinearLayout.VERTICAL);
        cloudPanel.setVisibility(View.GONE);
        cloudSignerEdit = cloudEdit("Signer URL (prefilled by the build)", false);
        cloudSignerTokenEdit = cloudEdit("Signer token (prefilled by the build)", true);
        cloudLibEdit = cloudEdit("— or without a signer: Cloud library ID", false);
        cloudKeyEdit = cloudEdit("Library API key (then lives on this phone)", true);
        cloudPanel.addView(cloudFieldLabel("Signer URL")); cloudPanel.addView(cloudSignerEdit);
        cloudPanel.addView(cloudFieldLabel("Signer token")); cloudPanel.addView(cloudSignerTokenEdit);
        cloudPanel.addView(cloudFieldLabel("Cloud library ID")); cloudPanel.addView(cloudLibEdit);
        cloudPanel.addView(cloudFieldLabel("Library API key")); cloudPanel.addView(cloudKeyEdit);
        cloudPanel.addView(label("On by default and purely additive: lessons are saved on this phone first, then a copy uploads for streamed playback. The signer URL and token arrive baked into this build; these fields are only overrides. A library key pasted below talks to the library directly instead of the signer.", 14, DIM));
        l.addView(cloudPanel);

        cloudShareButton = button("Share Cloud link");
        cloudShareButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLink(); } });
        l.addView(cloudShareButton);

        clipList.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            @Override public void onItemClick(android.widget.AdapterView<?> parent, View view, int pos, long id) {
                String name = clipNames.get(pos);
                JSONObject link = cloudLink(name);
                if (link == null) return;
                String st = link.optString("state", "");
                if ("ready".equals(st)) {
                    String lib = link.optString("libraryId", cloudCfgString("libraryId"));
                    String url = "https://player.mediadelivery.net/embed/" + lib + "/" + link.optString("videoId", "");
                    try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
                    catch (Throwable e) { Toast.makeText(MainActivity.this, url, Toast.LENGTH_LONG).show(); }
                } else if ("failed".equals(st)) {
                    File f = new File(clipsDir, name);
                    if (f.exists()) startCloudUpload(f);
                } else if ("processing".equals(st)) {
                    pollCloud(name, link.optString("videoId", ""));
                    Toast.makeText(MainActivity.this, "Still preparing on Cloud…", Toast.LENGTH_SHORT).show();
                }
            }
        });
        clipList.setOnItemLongClickListener(new android.widget.AdapterView.OnItemLongClickListener() {
            @Override public boolean onItemLongClick(android.widget.AdapterView<?> parent, View view, int pos, long id) {
                confirmDeleteLesson(clipNames.get(pos));
                return true;
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

    private EditText cloudEdit(String hint, boolean password) {
        EditText e = new EditText(this);
        e.setHint(hint); e.setTextSize(15); e.setTextColor(TEXT); e.setHintTextColor(DIM);
        e.setBackgroundColor(PANEL); e.setSingleLine(true);
        if (password) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setPadding(dp(10), dp(8), dp(10), dp(8));
        return e;
    }
    private TextView cloudFieldLabel(String s) { return label(s, 14, DIM); }

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
        status.setText(on
                ? "☁ Cloud on. New lessons will also upload for streamed playback; tap a lesson with ☁▶ to open its Watch link."
                : "☁ Cloud off. Lessons stay on this phone only.");
    }

    private void toggleCloudPanel() {
        if (cloudPanel.getVisibility() != View.VISIBLE) {
            cloudSignerEdit.setText(cloudEffSignerUrl());
            cloudSignerTokenEdit.setText(cloudEffSignerToken());
            cloudLibEdit.setText(cloudCfgString("libraryId"));
            cloudKeyEdit.setText(cloudCfgString("apiKey"));
            cloudPanel.setVisibility(View.VISIBLE);
        } else {
            cloudPrefs().edit()
                    .putString("signerUrl", cloudSignerEdit.getText().toString().trim())
                    .putString("signerToken", cloudSignerTokenEdit.getText().toString().trim())
                    .putString("libraryId", cloudLibEdit.getText().toString().trim())
                    .putString("apiKey", cloudKeyEdit.getText().toString().trim())
                    .apply();
            cloudPanel.setVisibility(View.GONE);
            paintCloudToggle();
        }
    }

    private void paintCloudToggle() {
        if (cloudToggleButton == null) return;
        cloudToggleButton.setText(cloudEnabledCfg() ? "☁ Cloud: on" : "☁ Cloud: off");
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
                .setTitle("Delete lesson?")
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
                if (!videoId.isEmpty()) {
                    try {
                        CloudUploader up = cloudUploader();
                        if (up == null) throw new IOException("Cloud settings incomplete.");
                        up.deleteVideo(videoId);
                    } catch (final Exception e) {
                        runOnUiThread(new Runnable() { @Override public void run() {
                            status.setText("☁ Couldn't delete the cloud copy (" + e.getMessage() + ") Keeping the local lesson so nothing is lost.");
                        } });
                        return;
                    }
                }
                new File(clipsDir, name).delete();
                delCloudLink(name);
                if (name.equals(cloudPrefs().getString("lastName", "")))
                    cloudPrefs().edit().remove("lastLink").remove("lastName").apply();
                if (lastLessonFile != null && name.equals(lastLessonFile.getName())) lastLessonFile = null;
                runOnUiThread(new Runnable() { @Override public void run() {
                    refreshClipList();
                    updateShareButton();
                    status.setText("🗑 Lesson deleted from this phone" + (videoId.isEmpty() ? "." : " and the cloud."));
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
        if ("ready".equals(st)) { updateShareButton(); return; }
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
        status.setText("☁ Uploading " + name + " to Cloud… The lesson is already saved on this phone.");
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
                                status.setText("☁ Uploaded. Cloud is preparing the streaming version…");
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
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Cloud lesson link", url));
            } catch (Throwable ignored) { }
            status.setText("☁ Ready: " + name + " — ▶ Watch link copied. Tap the lesson or Share Cloud link to send it.");
            updateShareButton();
            refreshClipList();
        } });
    }

    private void cloudFailed(final String name, String videoId, final String message) {
        setCloudLink(name, "failed", videoId, null, null, -1);
        runOnUiThread(new Runnable() { @Override public void run() {
            status.setText("☁ Cloud didn't finish for " + name + " (" + message + ") The lesson is safe on this phone — tap it in the list to retry.");
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

    private void updateShareButton() {
        if (cloudShareButton == null) return;
        String last = cloudPrefs().getString("lastLink", "");
        cloudShareButton.setEnabled(last != null && !last.isEmpty());
    }

    private void shareCloudLink() {
        String url = cloudPrefs().getString("lastLink", "");
        String name = cloudPrefs().getString("lastName", "lesson");
        if (url == null || url.isEmpty()) {
            Toast.makeText(this, "No Cloud link yet — record a lesson with Cloud on.", Toast.LENGTH_LONG).show();
            return;
        }
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("text/plain");
        share.putExtra(Intent.EXTRA_SUBJECT, name);
        share.putExtra(Intent.EXTRA_TEXT, url);
        startActivity(Intent.createChooser(share, "Share lesson link"));
    }
}
