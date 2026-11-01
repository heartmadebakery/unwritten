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
import android.widget.EditText;
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

import org.json.JSONArray;
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

/** Unwritten Craft. Home lands on the hub sessions with Record and
 *  Upload above them; recording is one screen of the app, not a
 *  separate app. The pipeline (transcribe -> write-up -> corrections)
 *  works afterwards on each session — a take or an upload alike.
 *  Video + audio go through CameraEngine (Camera2 + MediaRecorder);
 *  clips live in the app's clips folder and export to
 *  Downloads/Unwritten. */
public class MainActivity extends Activity {

    private static final int BG = Color.parseColor("#17130E");
    private static final int PANEL = Color.parseColor("#241C12");
    private static final int TEXT = Color.parseColor("#F5EAD6");
    private static final int DIM = Color.parseColor("#B8A888");
    private static final int AMBER = Color.parseColor("#E8A13A"); // retained for compat, not used
    private static final int RED = Color.parseColor("#C0392B"); // retained for compat, not used
    private static final int PERM_RECORD = 7;
    private static final int REQ_UPLOAD = 8;

    private File clipsDir;
    private final Handler handler = new Handler();

    private TextureView preview;
    private TextView status;
    private Button recordButton;
    private LinearLayout lessonContainer;
    private LinearLayout homeScreen, recordScreen;
    private String currentScreen = "home";
    private final List<String> clipNames = new ArrayList<String>();
    private CameraEngine engine;
    private long recordStartMs;
    private boolean pendingRecord;
    private boolean activityStopped;
    private android.widget.VideoView localPlayer;
    private android.widget.FrameLayout viewfinderBox;
    private LinearLayout playerControls;
    private boolean isViewfinderPlaying = false;

    // Cloud streaming (on by default, prefilled at build time): per-lesson link state.
    private static final String CLOUD_PREFS = "unwritten_cloud";
    private static final String CLOUD_SIGNER_DEFAULT = "https://unwritten-cloud-signer.heartmade.workers.dev";
    private Button cloudToggleButton, exportBtn, camToggle;
    private TextView zoomLabel, micWarn, speechWarn;
    private LinearLayout hubContainer;
    private JSONArray hubRows = new JSONArray();
    private JSONObject hubDetail;
    private String hubNotice = "";
    private SeekBar zoomSeek;
    private long speechQuietSince;
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
        // External playback goes through TinyFileProvider (content://
        // with a read grant) — file:// intents arrive unreadable on
        // Android 7+, so there is no StrictMode bypass here.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        java.io.File extRoot = getExternalFilesDir(null);
        clipsDir = new File(extRoot != null ? extRoot : getFilesDir(), "clips");
        //noinspection ResultOfMethodCallIgnored
        clipsDir.mkdirs();
        buildScreen();
        refreshClipList();
        migrateCloudPrefs();
        paintCloudToggle();
        cloudResumePending();
        showScreen("home");
    }

    @Override protected void onPause() {
        super.onPause();
        // Leaving mid-recording stops and keeps the take.
        try { if (engine != null && engine.isRecording()) stopRecording(); } catch (Throwable ignored) {}
    }

    @Override protected void onStop() {
        super.onStop();
        activityStopped = true;
        // Never hold the camera in the background. A stop still
        // finalizing keeps the engine until its completion callback,
        // which closes it (see stopRecording).
        try {
            if (engine != null && !engine.isRecording()) {
                engine.close();
                engine = null;
            }
        } catch (Throwable ignored) {}
    }

    @Override protected void onStart() {
        super.onStart();
        activityStopped = false;
        // The record screen owns the camera: returning to home must
        // not reopen it behind the hub.
        if ("record".equals(currentScreen) && engine == null && hasPermissions()) openPreview();
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
        l.addView(label("Record, upload, and revisit craft lessons.", 16, DIM));

        // One app, two screens. Home (record/upload actions with the
        // hub last) is the landing; record owns the viewfinder and
        // opens it only on entry, so landing never prompts for the
        // camera, with cloud and device sessions below. Upload is the
        // system picker — the picked video rides the exact session
        // path of a take.
        homeScreen = new LinearLayout(this);
        homeScreen.setOrientation(LinearLayout.VERTICAL);
        l.addView(homeScreen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        recordScreen = new LinearLayout(this);
        recordScreen.setOrientation(LinearLayout.VERTICAL);
        recordScreen.setVisibility(View.GONE);
        l.addView(recordScreen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        buildHomeScreen();
        buildRecordScreen();

        status = label("", 16, TEXT); // hidden - status conveyed via list icons + toasts

        ScrollView sv = new ScrollView(MainActivity.this); sv.setBackgroundColor(BG); sv.addView(l);
        setContentView(sv);
    }

    private void buildHomeScreen() {
        Button goRecord = button("● Record");
        try { goRecord.setBackgroundTintList(null); } catch (Throwable ignored) {}
        goRecord.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showScreen("record"); } });
        homeScreen.addView(goRecord);

        Button upload = button("⬆ Upload video");
        try { upload.setBackgroundTintList(null); } catch (Throwable ignored) {}
        upload.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { pickUpload(); } });
        homeScreen.addView(upload);

        // Or paste a link: YouTube/watch pages queue to the pipeline
        // fetcher, which downloads and processes them like a take.
        final EditText urlInput = new EditText(this);
        urlInput.setHint("Paste a video link…");
        urlInput.setTextSize(16);
        urlInput.setTextColor(TEXT);
        urlInput.setHintTextColor(DIM);
        urlInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        homeScreen.addView(urlInput);
        Button urlFetch = button("⬇ Fetch from link");
        try { urlFetch.setBackgroundTintList(null); } catch (Throwable ignored) {}
        urlFetch.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { queueFetchUrl(urlInput.getText().toString().trim()); } });
        homeScreen.addView(urlFetch);

        // Hub: published lessons, same stories as the web hub. The hub
        // lives on the signer, so this section only fills when a signer
        // URL and token are configured and Cloud is on.
        homeScreen.addView(label("Hub sessions", 17, DIM));
        hubContainer = new LinearLayout(MainActivity.this);
        hubContainer.setOrientation(LinearLayout.VERTICAL);
        hubContainer.setBackgroundColor(BG);
        homeScreen.addView(hubContainer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    private void buildRecordScreen() {
        Button backHome = button("‹ Home");
        try { backHome.setBackgroundTintList(null); } catch (Throwable ignored) {}
        backHome.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showScreen("home"); } });
        recordScreen.addView(backHome);

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
        recordScreen.addView(viewfinderBox, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        // Warning banners directly below the stage, like the web app.
        micWarn = label("🎤 No microphone. The mentor's words won't be recorded — and the mentor's words are the whole point. Check Settings to re-enable it.", 15, 0xFFFFFFFF);
        micWarn.setBackgroundColor(RED);
        micWarn.setVisibility(View.GONE);
        recordScreen.addView(micWarn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        speechWarn = label("🔇 Quiet for a while. No speech in the last minute — and the mentor's words are the whole point. Check the mic is close enough.", 15, TEXT);
        speechWarn.setBackgroundColor(PANEL);
        speechWarn.setVisibility(View.GONE);
        recordScreen.addView(speechWarn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

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
        recordScreen.addView(zoomRow);
        zoomOut.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(-0.2f); } });
        zoomIn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(+0.2f); } });
        zoomSeek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean fromUser) { if (fromUser) applyZoomFromSlider(); }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });

        recordButton = button("● Record");
        recordButton.setBackgroundColor(PANEL); recordButton.setTextColor(TEXT);
        try { recordButton.setBackgroundTintList(null); } catch (Throwable ignored) {}
        recordButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleRecord(); } });
        recordScreen.addView(recordButton);

        camToggle = button(engine != null && engine.isFront() ? "🤳 Front camera" : "📷 Back camera");
        try { camToggle.setBackgroundTintList(null); } catch (Throwable ignored) {}
        camToggle.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) {
            if (engine == null || engine.isRecording()) return;
            engine.switchCamera();
            handler.postDelayed(new Runnable() { @Override public void run() { paintCamToggle(); refreshZoomUi(); } }, 1200);
            handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); } }, 2500);
        } });
        recordScreen.addView(camToggle);

        cloudToggleButton = button("☁ Cloud: on");
        try { cloudToggleButton.setBackgroundTintList(null); } catch (Throwable ignored) {}
        cloudToggleButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleCloudEnabled(); } });
        recordScreen.addView(cloudToggleButton);

        // This device: left icon (☁/device), middle date+duration, right share/download
        recordScreen.addView(label("This device", 17, DIM));
        lessonContainer = new LinearLayout(MainActivity.this);
        lessonContainer.setOrientation(LinearLayout.VERTICAL);
        lessonContainer.setBackgroundColor(BG);
        recordScreen.addView(lessonContainer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        exportBtn = button("Export sessions to Downloads");
        exportBtn.setBackgroundColor(PANEL); exportBtn.setTextColor(TEXT);
        try { exportBtn.setBackgroundTintList(null); } catch (Throwable ignored) {}
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        recordScreen.addView(exportBtn);

        // Debug overrides hide behind a small link at the bottom.
        Button advancedLink = new Button(this);
        advancedLink.setText("Advanced settings");
        advancedLink.setTextSize(14); advancedLink.setTextColor(DIM); advancedLink.setAllCaps(false);
        advancedLink.setBackgroundColor(Color.TRANSPARENT);
        try { advancedLink.setBackgroundTintList(null); } catch (Throwable ignored) {}
        advancedLink.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showCloudSettings(); } });
        recordScreen.addView(advancedLink);
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
            else { pendingRecord = false; showError("Camera and microphone permission denied."); }
        }
    }

    // ---------- screens & upload ----------

    private void showScreen(String name) {
        currentScreen = name;
        boolean home = "home".equals(name);
        if (homeScreen != null) homeScreen.setVisibility(home ? View.VISIBLE : View.GONE);
        if (recordScreen != null) recordScreen.setVisibility(home ? View.GONE : View.VISIBLE);
        if (!home) {
            if (hasPermissions()) openPreview();
            // Device sessions live on the record screen now: refresh
            // them on entry so a just-finished take shows immediately.
            refreshClipList();
        } else {
            // Leaving the record screen stops a live take (kept, like
            // backgrounding) and releases the camera; home refreshes
            // the hub on return.
            try { if (engine != null && engine.isRecording()) stopRecording(); } catch (Throwable ignored) {}
            stopLocalPlayback();
            try { if (engine != null && !engine.isRecording()) { engine.close(); engine = null; } } catch (Throwable ignored) {}
            loadHub();
        }
    }

    private void pickUpload() {
        try {
            Intent i = new Intent(Intent.ACTION_GET_CONTENT);
            i.setType("video/*");
            i.addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(Intent.createChooser(i, "Upload lesson video"), REQ_UPLOAD);
        } catch (Throwable e) {
            Toast.makeText(this, "No file picker on this device.", Toast.LENGTH_LONG).show();
        }
    }

    private void queueFetchUrl(final String url) {
        if (url.isEmpty()) {
            Toast.makeText(this, "Paste a link first.", Toast.LENGTH_SHORT).show();
            return;
        }
        if (!HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) {
            Toast.makeText(this, "Queuing needs the signer token — add it in Cloud settings.", Toast.LENGTH_LONG).show();
            return;
        }
        Toast.makeText(this, "⬇ Queuing…", Toast.LENGTH_SHORT).show();
        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                new HubClient(surl, stok).queueFetchJob(url);
            } catch (final Exception e) {
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Couldn't queue that link (" + e.getMessage() + ")", Toast.LENGTH_LONG).show();
                } });
                return;
            }
            runOnUiThread(new Runnable() { @Override public void run() {
                Toast.makeText(MainActivity.this, "✅ Queued — the pipeline will fetch the video.", Toast.LENGTH_LONG).show();
            } });
        } });
    }

    @Override protected void onActivityResult(int req, int result, Intent data) {
        super.onActivityResult(req, result, data);
        if (req != REQ_UPLOAD || result != RESULT_OK || data == null || data.getData() == null) return;
        savePickedVideo(data.getData());
    }

    private void savePickedVideo(final Uri uri) {
        // An upload rides the exact session path of a take: copied
        // into the clips folder under an upload_ name, then listed
        // and cloud-uploaded, so the pipeline picks it up the same
        // way a recording is picked up.
        String mime = null;
        try { mime = getContentResolver().getType(uri); } catch (Throwable ignored) {}
        if (mime != null && !mime.startsWith("video/")) {
            Toast.makeText(this, "That file isn't a video — pick a video file.", Toast.LENGTH_LONG).show();
            return;
        }
        String ext = "mp4";
        if ("video/quicktime".equals(mime)) ext = "mov";
        else if ("video/webm".equals(mime)) ext = "webm";
        else if ("video/x-matroska".equals(mime)) ext = "mkv";
        final File dest = new File(clipsDir, Names.uploadName(ext));
        Toast.makeText(this, "Copying upload…", Toast.LENGTH_SHORT).show();
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                InputStream in = getContentResolver().openInputStream(uri);
                if (in == null) throw new IOException("Could not open the picked file.");
                OutputStream out = new java.io.FileOutputStream(dest);
                try {
                    copyStream(in, out);
                } finally {
                    try { in.close(); } catch (Throwable ignored) {}
                    try { out.close(); } catch (Throwable ignored) {}
                }
            } catch (final Exception e) {
                try { dest.delete(); } catch (Throwable ignored) {}
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Upload failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                } });
                return;
            }
            runOnUiThread(new Runnable() { @Override public void run() {
                refreshClipList();
                maybeCloudUpload(dest);
                Toast.makeText(MainActivity.this, "Upload saved — on this device and uploading to Cloud.", Toast.LENGTH_LONG).show();
            } });
        } });
    }

    // ---------- recording ----------

    private void openPreview() {
        try {
            if (engine == null) engine = new CameraEngine(this, new CameraEngine.ErrorListener() {
                @Override public void onError(final String message) {
                    showError("Camera error: " + message);
                    // A failed start posted true and painted recording
                    // before the camera thread refused it: put the
                    // button and timer back so the next tap starts
                    // cleanly. A live take keeps its UI.
                    if (engine == null || !engine.isRecording()) {
                        handler.removeCallbacks(timerRunnable);
                        handler.removeCallbacks(speechRunnable);
                        hideSpeechWarn();
                        recordButton.setText("● Record");
                    }
                }
                @Override public void onMicUnavailable() {
                    // Video-only take: say so out loud, like the web
                    // app's red banner — never silent about silence.
                    runOnUiThread(new Runnable() { @Override public void run() { showMicWarn(); } });
                }
            });
            engine.openPreview(preview);
            handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); }}, 1200);
            handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); }}, 2500);
        } catch (Throwable e) { showError("Camera error: " + e.getMessage()); }
    }

    private void showMicWarn() { if (micWarn != null) micWarn.setVisibility(View.VISIBLE); }
    private void hideMicWarn() { if (micWarn != null) micWarn.setVisibility(View.GONE); }
    private void showSpeechWarn() { if (speechWarn != null) speechWarn.setVisibility(View.VISIBLE); }
    private void hideSpeechWarn() { if (speechWarn != null) speechWarn.setVisibility(View.GONE); }
    private void paintCamToggle() { if (camToggle != null) camToggle.setText(engine != null && engine.isFront() ? "🤳 Front camera" : "📷 Back camera"); }

    // The status TextView is intentionally hidden (list icons carry
    // state); errors must surface as a Toast instead of dying in it.
    private void showError(final String message) {
        if (status != null) status.setText(message);
        runOnUiThread(new Runnable() { @Override public void run() {
            Toast.makeText(MainActivity.this, message, Toast.LENGTH_LONG).show();
        } });
    }

    // Quiet-minute check, mirroring the web app: MediaRecorder's
    // peak amplitude is polled while recording, and a full quiet minute
    // raises the speech banner. Never touches the take itself.
    private final Runnable speechRunnable = new Runnable() {
        @Override public void run() {
            if (engine == null || !engine.isRecording()) { hideSpeechWarn(); return; }
            int amp = 0;
            try { amp = engine.getMaxAmplitude(); } catch (Throwable ignored) { }
            if (amp > 400) {
                speechQuietSince = SystemClock.elapsedRealtime();
                hideSpeechWarn();
            } else if (SystemClock.elapsedRealtime() - speechQuietSince > 60000) {
                showSpeechWarn();
            }
            handler.postDelayed(this, 2000);
        }
    };

    private void toggleRecord() {
        if (!hasPermissions()) {
            pendingRecord = true;
            requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}, PERM_RECORD);
            return;
        }
        if (engine == null) { openPreview(); showError("Camera not ready yet — try again in a moment."); return; }
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
                // Fresh mic state, then watch the level.
                hideMicWarn();
                speechQuietSince = SystemClock.elapsedRealtime();
                hideSpeechWarn();
                handler.postDelayed(speechRunnable, 2000);
            } else showError("Could not start recording.");
        } catch (Throwable e) { showError("Record failed: " + e.getMessage()); }
    }

    private void stopRecording() {
        try {
            if (engine != null) engine.stopVideo(new Runnable() { @Override public void run() {
                // The take finalizes on the camera thread first: only
                // now is the file complete and safe to list and upload.
                refreshClipList();
                if (lastLessonFile != null) maybeCloudUpload(lastLessonFile);
                // A stop that finishes off the record screen (‹ Home
                // mid-take, or backgrounded) releases the camera with
                // it; a plain stop on the record screen keeps it.
                if ((activityStopped || !"record".equals(currentScreen)) && engine != null) {
                    try { engine.close(); } catch (Throwable ignored) {}
                    engine = null;
                }
            } });
        } catch (Throwable e) { showError("Stop failed: " + e.getMessage()); return; }
        handler.removeCallbacks(timerRunnable);
        handler.removeCallbacks(speechRunnable);
        hideSpeechWarn();
        recordButton.setText("● Record");
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

    private void addRowButton(LinearLayout row, String text, int sp, int color,
                              Integer bg, View.OnClickListener onClick) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextSize(sp);
        tv.setTextColor(color);
        if (bg != null) {
            tv.setBackgroundColor(bg);
            try { tv.setBackgroundTintList(null); } catch (Throwable ignored) {}
        }
        tv.setGravity(Gravity.CENTER);
        tv.setPadding(dp(6), dp(4), dp(6), dp(4));
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(36));
        bp.setMargins(dp(8), 0, 0, 0);
        tv.setLayoutParams(bp);
        tv.setClickable(true);
        tv.setOnClickListener(onClick);
        row.addView(tv);
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
                addRowButton(row, "\u2193", 20, DIM, null, new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
            } else if (isReady) {
                // Cloud-linking never removes the on-device download:
                // ready rows keep ↓ next to ↗.
                addRowButton(row, "\u2193", 20, DIM, null, new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
                addRowButton(row, "\u2197", 20, TEXT, PANEL, new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLinkFor(name); } });
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
                    stv.setClickable(true);
                    stv.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { retryCloud(name); } });
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
        int count = 0, failed = 0;
        ContentResolver cr = getContentResolver();
        for (File f : files) {
            Uri uri = null;
            try {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, f.getName());
                cv.put(MediaStore.Downloads.MIME_TYPE, mimeFor(f.getName()));
                cv.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Unwritten");
                cv.put(MediaStore.Downloads.IS_PENDING, 1);
                uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (uri == null) throw new Exception("MediaStore insert failed for " + f.getName());
                OutputStream out = cr.openOutputStream(uri);
                if (out == null) throw new Exception("Could not open output for " + f.getName());
                FileInputStream in = new FileInputStream(f);
                try {
                    copyStream(in, out);
                } finally {
                    try { in.close(); } catch (Throwable ignored) {}
                    try { out.close(); } catch (Throwable ignored) {}
                }
                ContentValues done = new ContentValues(); done.put(MediaStore.Downloads.IS_PENDING, 0);
                cr.update(uri, done, null, null);
                count++;
            } catch (Throwable e) {
                failed++;
                // Never orphan the IS_PENDING row: it would sit in
                // Downloads invisible and unopenable.
                if (uri != null) { try { cr.delete(uri, null, null); } catch (Throwable ignored) {} }
            }
        }
        String msg = "Exported " + count + " sessions to Downloads/Unwritten";
        if (failed > 0) msg += " (" + failed + " failed)";
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
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

    // True when an upload could possibly succeed. Signer mode needs
    // its token — the URL always has a compiled default, so URL-alone
    // must not count — and direct mode needs library ID + API key.
    // Without this, fresh installs (Cloud on by default, no
    // credentials yet) fire doomed uploads that can only 401.
    private boolean canUpload() {
        if (HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) return true;
        return !cloudCfgString("libraryId").trim().isEmpty()
                && !cloudCfgString("apiKey").trim().isEmpty();
    }

    private void toggleCloudEnabled() {
        boolean on = !cloudPrefs().getBoolean("enabled", true);
        cloudPrefs().edit().putBoolean("enabled", on).apply();
        paintCloudToggle();
        applyCloudDependentVisibility();
        if (on) sweepBacklog();
    }

    // Sessions recorded while Cloud was off (or failed) still need
    // their copy when Cloud comes back on — without this sweep they
    // would stay local-only forever, silently.
    private void sweepBacklog() {
        if (!canUpload() || clipsDir == null) return;
        File[] files = clipsDir.listFiles();
        if (files == null) return;
        for (File f : files) maybeCloudUpload(f);
    }

    // Cloud credentials, like the iOS and web settings panels. Fields
    // prefill with STORED overrides only — never effective values, so
    // opening this can never persist the build defaults as overrides
    // and shadow a later stamp rotation. Hints name the defaults.
    private void showCloudSettings() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(4);
        form.setPadding(pad, pad, pad, pad);
        final EditText urlEt = settingsField(form, "Signer URL (build default unless overridden)",
                cloudCfgString("signerUrl"), CLOUD_SIGNER_DEFAULT, false);
        final EditText tokEt = settingsField(form, "Signer token (build default unless overridden)",
                cloudCfgString("signerToken"), "baked into this build", true);
        final EditText libEt = settingsField(form, "Stream library ID (no signer)",
                cloudCfgString("libraryId"), "e.g. 402315", false);
        final EditText keyEt = settingsField(form, "Library API key (lives on this device)",
                cloudCfgString("apiKey"), "AccessKey from the library's API page", true);
        new AlertDialog.Builder(this)
                .setTitle("Cloud settings")
                .setView(form)
                .setPositiveButton("Save", new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        cloudPrefs().edit()
                                .putString("signerUrl", urlEt.getText().toString().trim())
                                .putString("signerToken", tokEt.getText().toString().trim())
                                .putString("libraryId", libEt.getText().toString().trim())
                                .putString("apiKey", keyEt.getText().toString().trim())
                                .apply();
                        paintCloudToggle();
                        applyCloudDependentVisibility();
                        if (cloudPrefs().getBoolean("enabled", true)) sweepBacklog();
                    }
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private EditText settingsField(LinearLayout form, String labelText,
                                   String value, String hint, boolean secret) {
        form.addView(label(labelText, 14, DIM));
        EditText et = new EditText(this);
        et.setText(value);
        et.setHint(hint);
        et.setTextSize(16);
        et.setTextColor(TEXT);
        et.setHintTextColor(DIM);
        if (secret) et.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        else et.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        form.addView(et);
        return et;
    }

    private void applyCloudDependentVisibility() {
        boolean on = cloudEnabledCfg();
        if (exportBtn != null) exportBtn.setVisibility(on ? View.GONE : View.VISIBLE);
        refreshClipList();
        loadHub();
    }

    private void paintCloudToggle() {
        if (cloudToggleButton == null) return;
        cloudToggleButton.setText(cloudEnabledCfg() ? "☁ Cloud: on" : "☁ Cloud: off");
        applyCloudDependentVisibility();
    }

    private void playInViewfinder(String name) {
        File f = new File(clipsDir, name);
        if (!f.exists()) { Toast.makeText(this, "File missing.", Toast.LENGTH_SHORT).show(); return; }
        // Sessions live on home; playback happens on the record screen.
        showScreen("record");
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
            Uri uri = TinyFileProvider.uriForFile(this, f);
            if (uri == null) {
                Toast.makeText(this, "That session file is missing from this device.", Toast.LENGTH_LONG).show();
                return;
            }
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
        if (!"home".equals(currentScreen)) { showScreen("home"); return; }
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
            // Same lesson only: a stale lastLink from another lesson must
            // never be shared under this lesson's name.
            String lastName = cloudPrefs().getString("lastName", "");
            url = name.equals(lastName) ? cloudPrefs().getString("lastLink", "") : "";
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

    // ---------- hub: published lessons, same stories as the web hub ----------

    private boolean hubAvailable() {
        return cloudEnabledCfg() && HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken());
    }

    // Always-visible Hub section text: the reason when the hub cannot
    // show rows. The "Hub sessions" header renders regardless; this
    // keeps a missing token or a dead server visible instead of
    // looking like a missing feature.
    private String hubStatusText() {
        if (!cloudPrefs().getBoolean("enabled", true)) return "Hub lives on the signer — turn Cloud on to see published lessons.";
        if (!HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) return "Hub lives on the signer — add the signer URL and token in Cloud settings.";
        if (hubNotice != null && !hubNotice.isEmpty()) return hubNotice;
        return "No published sessions yet — run the pipeline's publish step.";
    }

    private void loadHub() {
        if (!hubAvailable()) {
            hubRows = new JSONArray();
            hubDetail = null;
            hubNotice = "";
            runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); } });
            return;
        }
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                HubClient hub = new HubClient(cloudEffSignerUrl(), cloudEffSignerToken());
                hubRows = hub.list();
                hubNotice = "";
                if (hubDetail != null) {
                    boolean stillThere = false;
                    String cur = hubDetail.optString("videoId", "");
                    for (int i = 0; i < hubRows.length(); i++) {
                        if (cur.equals(hubRows.optJSONObject(i).optString("videoId", ""))) { stillThere = true; break; }
                    }
                    if (!stillThere) hubDetail = null;
                }
                runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); } });
            } catch (final Exception e) {
                android.util.Log.e("UnwrittenHub", "hub list failed", e);
                final String msg = String.valueOf(e.getMessage());
                if (msg.contains("(401)") || msg.contains("(403)")) {
                    hubNotice = "Signer refused the token — check it in Cloud settings.";
                } else if (msg.contains("(503)")) {
                    hubNotice = "Hub isn't switched on at the server yet.";
                } else {
                    // Surface cause for debugging — keep generic prefix
                    String cause = msg.length() > 180 ? msg.substring(0, 180) : msg;
                    hubNotice = "Hub couldn't load — check the connection and Cloud settings. (" + cause + ")";
                }
                runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); } });
            }
        } });
    }

    private void refreshHubRows() {
        if (hubContainer == null) return;
        hubContainer.removeAllViews();
        if (hubDetail != null) hubContainer.addView(hubDetailView(hubDetail));
        if (hubRows == null || hubRows.length() == 0) {
            TextView empty = label(hubStatusText(), 15, DIM);
            empty.setPadding(dp(6), dp(7), dp(6), dp(7));
            hubContainer.addView(empty);
            return;
        }
        for (int i = 0; i < hubRows.length(); i++) {
            final JSONObject row = hubRows.optJSONObject(i);
            if (row == null) continue;
            LinearLayout r = new LinearLayout(this);
            r.setOrientation(LinearLayout.HORIZONTAL);
            r.setPadding(dp(6), dp(8), dp(6), dp(8));
            TextView left = label("☁", 16, TEXT);
            left.setMinWidth(dp(32));
            r.addView(left);
            String title = row.optString("title", row.optString("videoId", ""));
            String date = row.optString("lessonDate", "");
            TextView mid = label(title + (date.isEmpty() ? "" : "  •  " + date), 15, TEXT);
            LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            mid.setLayoutParams(mp);
            mid.setPadding(dp(8), 0, dp(8), 0);
            mid.setSingleLine(true);
            mid.setEllipsize(android.text.TextUtils.TruncateAt.END);
            r.addView(mid);
            TextView go = label("›", 20, DIM);
            go.setMinWidth(dp(40));
            go.setGravity(Gravity.CENTER);
            r.addView(go);
            r.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { openHubSession(row.optString("videoId", "")); } });
            hubContainer.addView(r);
        }
    }

    private void openHubSession(final String videoId) {
        if (videoId == null || videoId.isEmpty() || !hubAvailable()) return;
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                HubClient hub = new HubClient(cloudEffSignerUrl(), cloudEffSignerToken());
                hubDetail = hub.get(videoId);
                runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); } });
            } catch (final Exception e) {
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Couldn't open that hub session — check the connection.", Toast.LENGTH_LONG).show();
                } });
            }
        } });
    }

    private Button smallHubButton(String text) {
        Button b = button(text);
        try { b.setTextSize(14); } catch (Throwable ignored) {}
        b.setTextColor(TEXT);
        b.setBackgroundColor(PANEL);
        try { b.setBackgroundTintList(null); } catch (Throwable ignored) {}
        return b;
    }

    private View hubDetailView(final JSONObject obj) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundColor(PANEL);
        card.setPadding(dp(14), dp(14), dp(14), dp(14));
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        TextView t = label(obj.optString("title", obj.optString("videoId", "")), 17, TEXT);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        t.setLayoutParams(tp);
        top.addView(t);
        Button close = smallHubButton("✕");
        close.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) {
            hubDetail = null;
            if (isViewfinderPlaying) stopLocalPlayback();
            refreshHubRows();
        } });
        top.addView(close);
        card.addView(top);
        card.addView(label(obj.optString("lessonDate", ""), 14, DIM));
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        Button play = smallHubButton("▶ Play");
        play.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { playHubRemote(obj); } });
        Button share = smallHubButton("↗");
        share.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { shareHubSession(obj); } });
        Button del = smallHubButton("🗑");
        del.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) {
            confirmDeleteHub(obj.optString("title", obj.optString("videoId", "")), obj.optString("videoId", ""));
        } });
        actions.addView(play);
        actions.addView(share);
        actions.addView(del);
        card.addView(actions);
        String writeup = obj.optString("writeupMd", "");
        if (!writeup.isEmpty()) card.addView(label(writeup, 15, TEXT));
        JSONArray corrections = obj.optJSONArray("corrections");
        if (corrections != null) {
            for (int i = 0; i < corrections.length(); i++) {
                JSONObject c = corrections.optJSONObject(i);
                if (c == null) continue;
                card.addView(label("• " + c.optString("start", "") + "  " + c.optString("quote", ""), 15, TEXT));
                if (!c.optString("correcting", "").isEmpty()) {
                    card.addView(label("  → " + c.optString("correcting", ""), 14, DIM));
                }
            }
        }
        JSONArray chapters = obj.optJSONArray("chapters");
        if (chapters != null) {
            for (int i = 0; i < chapters.length(); i++) {
                JSONObject c = chapters.optJSONObject(i);
                if (c == null) continue;
                card.addView(label("§ " + c.optString("start", "") + "  " + c.optString("label", ""), 14, DIM));
            }
        }
        return card;
    }

    private String hubEmbedUrl(JSONObject obj) {
        if (obj == null) return null;
        String vid = obj.optString("videoId", "");
        if (vid == null || vid.isEmpty()) return null;
        String lib = obj.optString("libraryId", "");
        if (lib == null || lib.isEmpty()) lib = cloudCfgString("libraryId");
        if (lib == null || lib.isEmpty()) return null;
        return "https://player.mediadelivery.net/embed/" + lib + "/" + vid;
    }

    private void shareHubSession(JSONObject obj) {
        String url = hubEmbedUrl(obj);
        if (url == null) {
            Toast.makeText(this, "No Cloud link yet for this session.", Toast.LENGTH_LONG).show();
            return;
        }
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("text/plain");
        share.putExtra(Intent.EXTRA_SUBJECT, obj.optString("title", "hub session"));
        share.putExtra(Intent.EXTRA_TEXT, url);
        startActivity(Intent.createChooser(share, "Share session link"));
    }

    private void playHubRemote(final JSONObject obj) {
        final String mp4 = obj.optString("mp4Url", "");
        final String embed = hubEmbedUrl(obj);
        if ((mp4 == null || mp4.isEmpty()) && (embed == null || embed.isEmpty())) {
            Toast.makeText(this, "No playable stream on this hub session yet.", Toast.LENGTH_LONG).show();
            return;
        }
        if (engine != null && engine.isRecording()) return;
        if (localPlayer == null || viewfinderBox == null || preview == null) {
            openInBrowser(embed);
            return;
        }
        try {
            if (mp4 != null && !mp4.isEmpty()) {
                showScreen("record");
                preview.setVisibility(View.INVISIBLE);
                localPlayer.setVisibility(View.VISIBLE);
                if (playerControls != null) playerControls.setVisibility(View.VISIBLE);
                isViewfinderPlaying = true;
                localPlayer.setOnPreparedListener(new android.media.MediaPlayer.OnPreparedListener() {
                    @Override public void onPrepared(android.media.MediaPlayer mp) { localPlayer.start(); }
                });
                localPlayer.setOnErrorListener(new android.media.MediaPlayer.OnErrorListener() {
                    @Override public boolean onError(android.media.MediaPlayer mp, int what, int extra) {
                        openInBrowser(embed);
                        return true;
                    }
                });
                localPlayer.setOnCompletionListener(new android.media.MediaPlayer.OnCompletionListener() {
                    @Override public void onCompletion(android.media.MediaPlayer mp) { stopLocalPlayback(); }
                });
                localPlayer.setVideoURI(Uri.parse(mp4));
                localPlayer.requestFocus();
            } else {
                openInBrowser(embed);
            }
        } catch (Throwable e) {
            Toast.makeText(this, "Playback failed (" + e.getMessage() + ")", Toast.LENGTH_LONG).show();
        }
    }

    private void openInBrowser(String url) {
        if (url == null || url.isEmpty()) {
            Toast.makeText(this, "No playable stream on this hub session yet.", Toast.LENGTH_LONG).show();
            return;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Throwable e) {
            Toast.makeText(this, "No app can open " + url, Toast.LENGTH_LONG).show();
        }
    }

    private void confirmDeleteHub(final String title, final String videoId) {
        new AlertDialog.Builder(this)
                .setTitle("Delete hub session?")
                .setMessage("Delete '" + title + "' from the cloud and the hub?")
                .setPositiveButton("Delete", new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        deleteHubSession(videoId);
                    }
                })
                .setNegativeButton("Keep", null)
                .show();
    }

    private void deleteHubSession(final String videoId) {
        if (videoId == null || videoId.isEmpty()) return;
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                CloudUploader up = cloudUploader();
                if (up == null) throw new IOException("Cloud settings incomplete.");
                // Hub record first, then the Stream copy: a failure
                // between the two leaves the bytes orphaned in Stream
                // (still playable, still re-publishable) instead of a
                // hub row pointing at a dead video.
                new HubClient(cloudEffSignerUrl(), cloudEffSignerToken()).delete(videoId);
                try {
                    up.deleteVideo(videoId);
                } catch (final Exception e2) {
                    runOnUiThread(new Runnable() { @Override public void run() {
                        if (status != null) status.setText("☁ Hub entry removed, but the cloud copy remains (" + e2.getMessage() + ")");
                        Toast.makeText(MainActivity.this, "Hub entry removed, but the cloud copy remains — delete it from the Stream dashboard.", Toast.LENGTH_LONG).show();
                        loadHub();
                    } });
                    return;
                }
            } catch (final Exception e) {
                runOnUiThread(new Runnable() { @Override public void run() {
                    if (status != null) status.setText("☁ Couldn't delete the hub entry (" + e.getMessage() + ")");
                    Toast.makeText(MainActivity.this, "Hub delete failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                } });
                return;
            }
            if (hubDetail != null && videoId.equals(hubDetail.optString("videoId", ""))) hubDetail = null;
            runOnUiThread(new Runnable() { @Override public void run() {
                loadHub();
                Toast.makeText(MainActivity.this, "Session deleted from the hub and the cloud", Toast.LENGTH_SHORT).show();
            } });
        } });
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
                            // A dead cloud delete must not trap local
                            // storage: offer the phone-only delete as a
                            // second confirm.
                            new AlertDialog.Builder(MainActivity.this)
                                .setTitle("Cloud copy couldn't be deleted")
                                .setMessage("The Cloud copy couldn't be deleted (" + e.getMessage() + "). Delete this phone's copy anyway? The Cloud copy stays where it is.")
                                .setPositiveButton("Delete from phone", new android.content.DialogInterface.OnClickListener() {
                                    @Override public void onClick(android.content.DialogInterface d, int which) {
                                        removeLocalSession(name, savedLastName, "Session deleted from this phone. The cloud copy stays where it is.");
                                    }
                                })
                                .setNegativeButton("Keep", null)
                                .show();
                        } });
                        return;
                    }
                } else {
                    android.util.Log.i("UWCloud", "deleteLesson local-only file=" + name);
                }
                final String doneToast = "Session deleted" + (videoId.isEmpty() ? "" : " from device and cloud");
                runOnUiThread(new Runnable() { @Override public void run() {
                    removeLocalSession(name, savedLastName, doneToast);
                } });
            }
        });
    }

    // Deletes this phone's copy: file, cloud link, and any poll or
    // upload state. Runs on the UI thread (file delete is fast;
    // prefs apply asynchronously).
    private void removeLocalSession(String name, String savedLastName, String doneToast) {
        boolean deleted = new File(clipsDir, name).delete();
        android.util.Log.i("UWCloud", "deleteLesson local delete file=" + name + " ok=" + deleted);
        delCloudLink(name);
        synchronized (cloudInFlight) { cloudInFlight.remove(name); }
        synchronized (cloudPolling) { cloudPolling.remove(name); }
        synchronized (cloudPollTasks) {
            java.util.concurrent.Future<?> poll = cloudPollTasks.remove(name);
            if (poll != null) poll.cancel(true);
        }
        if (name.equals(savedLastName))
            cloudPrefs().edit().remove("lastLink").remove("lastName").apply();
        if (lastLessonFile != null && name.equals(lastLessonFile.getName())) lastLessonFile = null;
        refreshClipList();
        Toast.makeText(this, doneToast, Toast.LENGTH_SHORT).show();
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

    private void retryCloud(final String name) {
        File f = new File(clipsDir, name);
        if (!f.exists()) {
            Toast.makeText(this, "That session file is missing from this device.", Toast.LENGTH_LONG).show();
            return;
        }
        startCloudUpload(f);
    }

    private void startCloudUpload(final File f) {
        if (!cloudEnabledCfg()) { Toast.makeText(this, "Turn Cloud on first.", Toast.LENGTH_SHORT).show(); return; }
        final String name = f.getName();
        if (!canUpload()) {
            cloudFailed(name, null, "Cloud credentials missing — add the signer token in Cloud settings.");
            Toast.makeText(this, "Signer token missing — add it in Cloud settings.", Toast.LENGTH_LONG).show();
            return;
        }
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
        if (!new File(clipsDir, name).exists()) return;  // deleted mid-flight: no zombie row
        CloudUploader up = cloudUploader();
        String lib = "";
        JSONObject link = cloudLink(name);
        if (link != null) lib = link.optString("libraryId", "");
        if ((lib == null || lib.isEmpty()) && up != null && up.lastLibraryId != null && !up.lastLibraryId.isEmpty()) lib = up.lastLibraryId;
        if (lib == null || lib.isEmpty()) lib = cloudCfgString("libraryId");
        setCloudLink(name, "ready", videoId, lib, null, 100);
        // A link is only published when the library id is known — an
        // embed//videoId URL helps nobody and poisons the fallback.
        if (lib == null) lib = "";
        final boolean linkable = !lib.isEmpty();
        final String url = linkable ? "https://player.mediadelivery.net/embed/" + lib + "/" + videoId : "";
        if (linkable) cloudPrefs().edit().putString("lastLink", url).putString("lastName", name).apply();
        runOnUiThread(new Runnable() { @Override public void run() {
            try {
                if (linkable) {
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Cloud session link", url));
                }
            } catch (Throwable ignored) { }
            refreshClipList();
        } });
    }

    private void cloudFailed(final String name, String videoId, final String message) {
        if (!new File(clipsDir, name).exists()) return;  // deleted mid-flight: no zombie row
        setCloudLink(name, "failed", videoId, null, null, -1);
        final boolean auth = message != null
                && (message.contains("(401)") || message.contains("(403)")
                    || message.contains("credentials missing"));
        runOnUiThread(new Runnable() { @Override public void run() {
            if (auth) Toast.makeText(MainActivity.this, "Signer refused — check the token in Cloud settings.", Toast.LENGTH_LONG).show();
            refreshClipList();
        } });
    }

    private final Set<String> cloudPolling = new HashSet<String>();
    private final java.util.Map<String, java.util.concurrent.Future<?>> cloudPollTasks =
            new java.util.HashMap<String, java.util.concurrent.Future<?>>();
    private void pollCloud(final String name, final String videoId) {
        if (videoId == null || videoId.isEmpty()) return;
        synchronized (cloudPolling) { if (!cloudPolling.add(name)) return; }
        java.util.concurrent.Future<?> task = cloudExec.submit(new Runnable() {
            @Override public void run() {
                try {
                    CloudUploader up = cloudUploader();
                    if (up == null) return;
                    int errors = 0;
                    for (int i = 0; i < 120; i++) {
                        try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                        int st;
                        try { st = up.videoStatus(videoId); } catch (Throwable e) { st = -1; }
                        if (st < 0) {
                            if (++errors > 6) { cloudFailed(name, videoId, "Cloud status checks kept failing — tap ! on the session to try again."); return; }
                            continue;
                        }
                        errors = 0;
                        if (st == 4) { cloudFinished(name, videoId); return; }
                        if (st == 5 || st == 6) { cloudFailed(name, videoId, "Cloud encoding failed."); return; }
                    }
                    // Ten minutes with no finished stream: offer a retry
                    // instead of leaving the session on "…" forever.
                    cloudFailed(name, videoId, "Cloud is taking too long to prepare the stream — tap ! on the session to try again.");
                } finally {
                    synchronized (cloudPolling) { cloudPolling.remove(name); }
                    synchronized (cloudPollTasks) { cloudPollTasks.remove(name); }
                }
            }
        });
        synchronized (cloudPollTasks) { cloudPollTasks.put(name, task); }
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
