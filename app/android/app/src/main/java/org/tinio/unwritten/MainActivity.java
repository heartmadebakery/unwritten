package org.tinio.unwritten;

import android.Manifest;
import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.text.method.ScrollingMovementMethod;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity {

    private static final int BG = Color.parseColor("#17130E");
    private static final int PANEL = Color.parseColor("#241C12");
    private static final int TEXT = Color.parseColor("#F5EAD6");
    private static final int DIM = Color.parseColor("#B8A888");
    private static final int AMBER = Color.parseColor("#E8A13A");
    private static final int RED = Color.parseColor("#C0392B");
    private static final int PERM_SESSION = 7;
    private static final int PERM_EXPORT = 8;

    private static class Step {
        final String key, title, prompt, speak;
        Step(String k, String t, String p, String s) { key = k; title = t; prompt = p; speak = s; }
    }

    private static final Step[] STEPS = new Step[]{
        new Step("show", "1 · Show me",
            "Ask her to do the move once, start to finish, without explaining. Just film it — hands, tool, and the work in frame. This silent pass is the 'before' picture.",
            "Show me once, start to finish. No need to explain yet."),
        new Step("teach", "2 · Teach me",
            "Now she teaches it, out loud, step by step, as if for a written index card. Near the end, ask about her most worn tool: 'What's different about yours?' Keep the camera on her hands. Steps only for now — the judgment questions come after her reaction.",
            "Now teach me. Say each step out loud, like you're writing it on an index card."),
        new Step("react", "3 · I try",
            "Read this line out loud — it is what the card alone would make an apprentice do. Then film her face and hands as she reacts. Don't defend the card; her corrections are the gold.",
            ""),
        new Step("attempt", "4 · Your try",
            "First, on camera, ask the wisdom questions: How do you know when it's right? What goes wrong if you do it the other way? What do you do differently now than when you learned? Who taught you this? Then the learner tries from the card only — she coaches, she doesn't teach. Finish with a photo of both results side by side.",
            "Now ask her the wisdom questions, then try it yourself from the card alone.")
    };

    private Prefs prefs;
    private String role = "interviewer";
    private String code = "";
    private File clipsDir;
    private final Handler handler = new Handler();

    private FrameLayout root;
    private View homeScreen, sessionScreen, companionScreen, flashOverlay;

    // Home
    private TextView roleLine, codeLabel, homeStatus;
    private Button[] roleButtons;
    private String[] roleKeys = new String[]{"interviewer", "recorder", "companion"};
    private LinearLayout apprenticeWrap;
    private EditText apprenticeEdit;
    private Button startButton;
    private boolean pendingStart;

    // Session
    private TextureView preview;
    private TextView stepHeader, stepDots, promptView, reactLine, sessionStatus, doneCard;
    private View reactCard, doneView;
    private Button recordButton, photoButton;
    private ListView sessionList;
    private ArrayAdapter<String> sessionAdapter;
    private final List<String> sessionNames = new ArrayList<String>();
    private CameraEngine engine;
    private int stepIndex;
    private long recordStartMs;
    private TextToSpeech tts;
    private boolean ttsReady;
    private String pendingSpeak;

    private final Runnable timerRunnable = new Runnable() {
        @Override public void run() {
            if (engine != null && engine.isRecording()) {
                long s = (SystemClock.elapsedRealtime() - recordStartMs) / 1000;
                recordButton.setText("■ Stop  " + (s / 60) + ":" + String.format(Locale.US, "%02d", s % 60));
                handler.postDelayed(this, 500);
            }
        }
    };

    // Companion
    private TextureView compPreview;
    private EditText compCodeEdit;
    private Button brollButton, dialogueButton, syncButton, compStopButton;
    private TextView compStatus;
    private ListView compList;
    private ArrayAdapter<String> compAdapter;
    private final List<String> compNames = new ArrayList<String>();
    private boolean compVideoMode = true;
    private boolean compRecording;
    private CameraEngine compEngine;
    private long flashHandle;
    private long wavHandle;
    private long compRecordStartMs;
    private final List<Long> marks = new ArrayList<Long>();
    private ToneGenerator toneGen;
    private int countdownLeft;
    private String exportCode = "";

    private final Runnable rmsRunnable = new Runnable() {
        @Override public void run() {
            if (compRecording && !compVideoMode && wavHandle != 0) {
                try {
                    double rms = NativeCore.nativeWavRms(wavHandle);
                    double norm = rms > 1.0 ? rms / 32768.0 : rms;
                    if (norm < 0) norm = 0; if (norm > 1) norm = 1;
                    int n = (int) Math.round(norm * 20);
                    StringBuilder bar = new StringBuilder();
                    for (int i = 0; i < 20; i++) bar.append(i < n ? '█' : '░');
                    compStatus.setText("Recording audio — session " + compCode() + "\n" + bar.toString());
                } catch (Throwable ignored) {}
                handler.postDelayed(this, 200);
            }
        }
    };

    private final Runnable countdownRunnable = new Runnable() {
        @Override public void run() {
            if (!compRecording) return;
            if (countdownLeft > 0) {
                setCompStatus("Recording — sync flash in " + countdownLeft + "…");
                beep(false);
                countdownLeft--;
                handler.postDelayed(this, 1000);
            } else {
                beep(true);
                flashOverlay.setVisibility(View.VISIBLE);
                flashOverlay.bringToFront();
                handler.postDelayed(new Runnable() {
                    @Override public void run() { flashOverlay.setVisibility(View.INVISIBLE); }
                }, 450);
                if (compVideoMode) {
                    setCompStatus("Recording video — session " + compCode() + ". The flash + beep marked time zero.");
                } else {
                    setCompStatus("Recording audio — session " + compCode() + ". The flash + beep marked time zero.");
                    handler.post(rmsRunnable);
                }
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

    private void styleSelected(Button b, boolean selected) {
        b.setBackgroundColor(selected ? AMBER : PANEL);
        b.setTextColor(selected ? BG : TEXT);
    }

    private LinearLayout column(android.content.Context parent) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setBackgroundColor(BG);
        l.setPadding(dp(14), dp(14), dp(14), dp(14));
        return l;
    }

    private ArrayAdapter<String> makeAdapter(final List<String> data) {
        return new ArrayAdapter<String>(this, android.R.layout.simple_list_item_1, data) {
            @Override public View getView(int pos, View convert, ViewGroup parent) {
                TextView t = (TextView) super.getView(pos, convert, parent);
                t.setTextColor(TEXT); t.setTextSize(15); t.setBackgroundColor(BG);
                return t;
            }
        };
    }

    private String cap(String s) {
        return s == null || s.length() == 0 ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }

    // ---------- lifecycle ----------

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = new Prefs(this);
        boolean wide = getResources().getConfiguration().screenWidthDp >= 600;
        try { role = prefs.getRole(wide); } catch (Throwable ignored) {}
        if (role == null || role.length() == 0) role = "interviewer";
        try { code = prefs.getCode(); } catch (Throwable ignored) {}
        if (code == null) code = "";
        clipsDir = new File(getExternalFilesDir(null), "clips");
        //noinspection ResultOfMethodCallIgnored
        clipsDir.mkdirs();

        root = new FrameLayout(this);
        root.setBackgroundColor(BG);
        buildHome(); buildSession(); buildCompanion();
        flashOverlay = new View(this);
        flashOverlay.setBackgroundColor(Color.WHITE);
        flashOverlay.setVisibility(View.INVISIBLE);
        root.addView(homeScreen); root.addView(sessionScreen); root.addView(companionScreen);
        root.addView(flashOverlay, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        showHome();
        // If permissions are already granted nothing is forced here; entry still happens via Start.
        hasPermissions();
    }

    @Override protected void onPause() {
        super.onPause();
        try {
            if (engine != null && engine.isRecording()) {
                engine.stopVideo();
                handler.removeCallbacks(timerRunnable);
                recordButton.setText("● Record");
                setSessionStatus("Recording stopped — take saved.");
                refreshSessionList();
            }
        } catch (Throwable ignored) {}
        try {
            if (compRecording && compVideoMode) stopCompanionRecording();
        } catch (Throwable ignored) {}
    }

    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        closeSessionEngine();
        closeCompanionEngine(true);
        try { if (wavHandle != 0) { NativeCore.nativeStopWav(wavHandle); wavHandle = 0; } } catch (Throwable ignored) {}
        destroyFlash();
        if (tts != null) { try { tts.stop(); tts.shutdown(); } catch (Throwable ignored) {} tts = null; }
        releaseTone();
        super.onDestroy();
    }

    // ---------- home ----------

    private void buildHome() {
        LinearLayout l = column(this);
        TextView title = label("Unwritten Craft — Recorder", 24, TEXT); title.setGravity(Gravity.CENTER);
        l.addView(title);
        roleLine = label("", 17, DIM); l.addView(roleLine);
        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        String[] names = new String[]{"Interviewer", "Recorder", "Companion"};
        roleButtons = new Button[3];
        for (int i = 0; i < 3; i++) {
            final int idx = i;
            Button b = button(names[i]);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            lp.setMargins(dp(2), dp(4), dp(2), dp(4)); b.setLayoutParams(lp);
            b.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    role = roleKeys[idx];
                    try { prefs.setRole(role); } catch (Throwable ignored) {}
                    updateHome();
                }
            });
            roleButtons[i] = b; row.addView(b);
        }
        l.addView(row);
        codeLabel = label("", 19, TEXT); l.addView(codeLabel);
        Button newCode = button("New session (new code)");
        newCode.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                try { code = prefs.rotateCode(); prefs.setStep("show"); } catch (Throwable e) { homeStatus.setText("Could not rotate code: " + e.getMessage()); }
                stepIndex = 0; updateHome();
            }
        });
        l.addView(newCode);

        apprenticeWrap = new LinearLayout(this); apprenticeWrap.setOrientation(LinearLayout.VERTICAL);
        apprenticeWrap.addView(label("Apprentice line (read aloud on step 3)", 17, DIM));
        apprenticeEdit = new EditText(this);
        apprenticeEdit.setTextSize(17); apprenticeEdit.setTextColor(TEXT); apprenticeEdit.setHintTextColor(DIM);
        apprenticeEdit.setBackgroundColor(PANEL); apprenticeEdit.setPadding(dp(10), dp(8), dp(10), dp(8));
        apprenticeEdit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        apprenticeEdit.setMinLines(2); apprenticeEdit.setGravity(Gravity.TOP);
        try { apprenticeEdit.setText(prefs.getApprenticeLine()); } catch (Throwable ignored) {}
        apprenticeWrap.addView(apprenticeEdit);
        l.addView(apprenticeWrap);

        startButton = button("Start");
        startButton.setBackgroundColor(AMBER); startButton.setTextColor(BG);
        startButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { onStartPressed(); }
        });
        l.addView(startButton);
        homeStatus = label("", 16, RED); l.addView(homeStatus);
        ScrollView sv = new ScrollView(this); sv.setBackgroundColor(BG); sv.addView(l);
        homeScreen = sv;
    }

    private void updateHome() {
        String desc;
        if ("recorder".equals(role)) desc = "This device will film the session while an interviewer guides and asks.";
        else if ("companion".equals(role)) desc = "This device will record synced B-roll video or dialogue audio for a session led elsewhere.";
        else desc = "This device will guide the session, speak the prompts, and film.";
        roleLine.setText(desc);
        for (int i = 0; i < roleButtons.length; i++) styleSelected(roleButtons[i], roleKeys[i].equals(role));
        codeLabel.setText("Session code: " + code);
        apprenticeWrap.setVisibility("companion".equals(role) ? View.GONE : View.VISIBLE);
        startButton.setText("Start as " + cap(role));
    }

    private void showHome() {
        homeScreen.setVisibility(View.VISIBLE);
        sessionScreen.setVisibility(View.GONE);
        companionScreen.setVisibility(View.GONE);
        try { code = prefs.getCode(); } catch (Throwable ignored) {}
        try { apprenticeEdit.setText(prefs.getApprenticeLine()); } catch (Throwable ignored) {}
        updateHome();
    }

    // ---------- permissions ----------

    private boolean hasPermissions() {
        return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
            && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    private void onStartPressed() {
        homeStatus.setText("");
        if (!"companion".equals(role)) {
            try { prefs.setApprenticeLine(apprenticeEdit.getText().toString().trim()); } catch (Throwable ignored) {}
        }
        if (hasPermissions()) { enterRole(); }
        else { pendingStart = true; requestPermissions(new String[]{Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO}, PERM_SESSION); }
    }

    @Override public void onRequestPermissionsResult(int req, String[] perms, int[] results) {
        super.onRequestPermissionsResult(req, perms, results);
        boolean granted = results.length > 0;
        for (int r : results) if (r != PackageManager.PERMISSION_GRANTED) granted = false;
        if (req == PERM_SESSION) {
            if (granted && pendingStart) { pendingStart = false; enterRole(); }
            else if (!granted) { pendingStart = false; homeStatus.setText("Camera and microphone permission denied — cannot start the session."); }
        } else if (req == PERM_EXPORT) {
            if (granted) doExport(exportCode);
            else Toast.makeText(this, "Export failed: WRITE_EXTERNAL_STORAGE permission denied", Toast.LENGTH_LONG).show();
        }
    }

    private void enterRole() {
        if ("companion".equals(role)) { enterCompanion(); } else { enterSession(); }
    }

    // ---------- session ----------

    private void buildSession() {
        LinearLayout l = column(this); l.setPadding(0, 0, 0, 0);
        preview = new TextureView(this);
        l.addView(preview, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 45f));

        LinearLayout body = column(this);
        ScrollView bodyScroll = new ScrollView(this); bodyScroll.setBackgroundColor(BG);
        bodyScroll.addView(body);
        l.addView(bodyScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 55f));

        stepHeader = label("", 20, TEXT); body.addView(stepHeader);
        stepDots = label("", 18, AMBER); body.addView(stepDots);
        promptView = label("", 17, TEXT);
        promptView.setMaxHeight(dp(130)); promptView.setMovementMethod(new ScrollingMovementMethod());
        promptView.setVerticalScrollBarEnabled(true);
        body.addView(promptView);

        reactCard = panelCard(body);
        reactLine = label("", 18, TEXT); ((LinearLayout) reactCard).addView(reactLine);
        reactCard.setVisibility(View.GONE);

        sessionStatus = label("", 16, DIM); body.addView(sessionStatus);

        recordButton = button("● Record"); recordButton.setBackgroundColor(RED); recordButton.setTextColor(Color.WHITE);
        recordButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleRecord(); } });
        body.addView(recordButton);

        photoButton = button("Take photo");
        photoButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { takePhoto(); } });
        body.addView(photoButton);

        LinearLayout nav = new LinearLayout(this); nav.setOrientation(LinearLayout.HORIZONTAL);
        Button back = button("Back"); Button next = button("Next");
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        half.setMargins(dp(2), dp(4), dp(2), dp(4)); back.setLayoutParams(half); next.setLayoutParams(half);
        back.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { navigate(-1); } });
        next.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { navigate(1); } });
        nav.addView(back); nav.addView(next); body.addView(nav);

        body.addView(label("Clips for this session", 17, DIM));
        sessionAdapter = makeAdapter(sessionNames);
        sessionList = new ListView(this); sessionList.setAdapter(sessionAdapter); sessionList.setBackgroundColor(BG);
        body.addView(sessionList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(150)));

        doneView = panelCard(body);
        LinearLayout done = (LinearLayout) doneView;
        done.addView(label("Session complete", 20, TEXT));
        Button exportBtn = button("Export clips");
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(code); } });
        done.addView(exportBtn);
        Button homeBtn = button("Home");
        homeBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { leaveSession(); } });
        done.addView(homeBtn);
        doneView.setVisibility(View.GONE);

        sessionScreen = l;
    }

    private View panelCard(LinearLayout parent) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL); c.setBackgroundColor(PANEL);
        c.setPadding(dp(10), dp(8), dp(10), dp(8));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(6), 0, dp(6)); c.setLayoutParams(lp);
        parent.addView(c);
        return c;
    }

    private void enterSession() {
        try { code = prefs.getCode(); } catch (Throwable ignored) {}
        String saved = "show";
        try { saved = prefs.getStep(); } catch (Throwable ignored) {}
        stepIndex = 0;
        for (int i = 0; i < STEPS.length; i++) if (STEPS[i].key.equals(saved)) stepIndex = i;
        homeScreen.setVisibility(View.GONE); companionScreen.setVisibility(View.GONE);
        sessionScreen.setVisibility(View.VISIBLE);
        doneView.setVisibility(View.GONE);
        try {
            if (engine == null) engine = new CameraEngine(this, sessionErrorListener());
            engine.openPreview(preview);
        } catch (Throwable e) { setSessionStatus("Camera error: " + e.getMessage()); }
        updateStep(true);
    }

    private CameraEngine.ErrorListener sessionErrorListener() {
        return new CameraEngine.ErrorListener() {
            @Override public void onError(final String message) {
                runOnUiThread(new Runnable() { @Override public void run() { setSessionStatus("Camera error: " + message); } });
            }
        };
    }

    private void closeSessionEngine() {
        try { if (engine != null) engine.close(); } catch (Throwable ignored) {}
        engine = null;
        handler.removeCallbacks(timerRunnable);
    }

    private void leaveSession() { closeSessionEngine(); showHome(); }

    private void setSessionStatus(String s) { if (sessionStatus != null) sessionStatus.setText(s); }

    private void updateStep(boolean speak) {
        Step s = STEPS[stepIndex];
        stepHeader.setText(s.title);
        StringBuilder dots = new StringBuilder();
        for (int i = 0; i < STEPS.length; i++) dots.append(i == stepIndex ? '●' : '○');
        stepDots.setText(dots.toString());
        promptView.setText(s.prompt); promptView.scrollTo(0, 0);
        if ("react".equals(s.key)) {
            String line = "";
            try { line = prefs.getApprenticeLine(); } catch (Throwable ignored) {}
            reactLine.setText("“" + line + "”");
            reactCard.setVisibility(View.VISIBLE);
        } else reactCard.setVisibility(View.GONE);
        try { prefs.setStep(s.key); } catch (Throwable ignored) {}
        refreshSessionList();
        if (speak && "interviewer".equals(role) && s.speak.length() > 0) speak(s.speak);
    }

    private boolean stopRecordingIfAny() {
        try {
            if (engine != null && engine.isRecording()) {
                engine.stopVideo();
                handler.removeCallbacks(timerRunnable);
                recordButton.setText("● Record");
                setSessionStatus("Recording stopped — take saved.");
                refreshSessionList();
                return true;
            }
        } catch (Throwable e) { setSessionStatus("Stop failed: " + e.getMessage()); return true; }
        return false;
    }

    private void navigate(int dir) {
        if (stopRecordingIfAny()) return; // first press only stops, same rule as the web app
        if (dir < 0) { if (stepIndex > 0) { stepIndex--; updateStep(true); } }
        else {
            if (stepIndex < STEPS.length - 1) { stepIndex++; updateStep(true); }
            else finishSession();
        }
    }

    private void toggleRecord() {
        if (engine == null) { setSessionStatus("Camera not ready."); return; }
        try {
            if (engine.isRecording()) { stopRecordingIfAny(); return; }
            File f = new File(clipsDir, Names.clipName(STEPS[stepIndex].key, code, "mp4"));
            if (engine.startVideo(f)) {
                recordStartMs = SystemClock.elapsedRealtime();
                recordButton.setText("■ Stop  0:00");
                handler.post(timerRunnable);
                setSessionStatus("Recording " + f.getName());
            } else setSessionStatus("Could not start recording.");
        } catch (Throwable e) { setSessionStatus("Record failed: " + e.getMessage()); }
    }

    private void takePhoto() {
        if (engine == null) { setSessionStatus("Camera not ready."); return; }
        try {
            engine.takePhoto(new CameraEngine.PhotoListener() {
                @Override public void onPhoto(final byte[] jpeg) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            try {
                                File f = new File(clipsDir, Names.photoName(STEPS[stepIndex].key, code));
                                FileOutputStream out = new FileOutputStream(f);
                                out.write(jpeg); out.close();
                                setSessionStatus("Photo saved: " + f.getName());
                                refreshSessionList();
                            } catch (Throwable e) { setSessionStatus("Photo save failed: " + e.getMessage()); }
                        }
                    });
                }
            });
        } catch (Throwable e) { setSessionStatus("Photo failed: " + e.getMessage()); }
    }

    private void finishSession() {
        try {
            JSONObject obj = new JSONObject();
            obj.put("session_code", code); obj.put("role", role); obj.put("device", "android");
            JSONArray clips = new JSONArray();
            for (File f : clipFiles(code)) { JSONObject c = new JSONObject(); c.put("name", f.getName()); clips.put(c); }
            obj.put("clips", clips);
            writeText(new File(clipsDir, "unwritten_session_" + code + ".json"), obj.toString(2));
        } catch (Throwable e) { setSessionStatus("Manifest failed: " + e.getMessage()); }
        doneView.setVisibility(View.VISIBLE);
        setSessionStatus("Session complete.");
        refreshSessionList();
    }

    // ---------- TTS ----------

    private void speak(String text) {
        if (text == null || text.length() == 0) return;
        try {
            if (tts == null) {
                pendingSpeak = text;
                ttsReady = false;
                tts = new TextToSpeech(this, new TextToSpeech.OnInitListener() {
                    @Override public void onInit(int status) {
                        ttsReady = status == TextToSpeech.SUCCESS;
                        if (ttsReady && pendingSpeak != null) {
                            try { tts.speak(pendingSpeak, TextToSpeech.QUEUE_FLUSH, null, "step"); } catch (Throwable ignored) {}
                            pendingSpeak = null;
                        }
                    }
                });
            } else if (ttsReady) tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "step");
            else pendingSpeak = text;
        } catch (Throwable ignored) {}
    }

    // ---------- companion ----------

    private void buildCompanion() {
        LinearLayout l = column(this);
        l.addView(label("Companion", 24, TEXT));
        l.addView(label("Session code from the lead device", 17, DIM));
        compCodeEdit = new EditText(this);
        compCodeEdit.setTextSize(19); compCodeEdit.setTextColor(TEXT); compCodeEdit.setHintTextColor(DIM);
        compCodeEdit.setBackgroundColor(PANEL); compCodeEdit.setPadding(dp(10), dp(8), dp(10), dp(8));
        compCodeEdit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        compCodeEdit.setText("");
        try { compCodeEdit.setHint("Code from lead device (e.g. " + prefs.getCode() + ")"); } catch (Throwable ignored) {}
        l.addView(compCodeEdit);

        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        brollButton = button("🎥 B-roll video"); dialogueButton = button("🎙 Dialogue audio");
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        half.setMargins(dp(2), dp(4), dp(2), dp(4)); brollButton.setLayoutParams(half); dialogueButton.setLayoutParams(half);
        brollButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { compVideoMode = true; updateCompMode(); } });
        dialogueButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { compVideoMode = false; updateCompMode(); } });
        row.addView(brollButton); row.addView(dialogueButton); l.addView(row);

        compPreview = new TextureView(this);
        l.addView(compPreview, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(200)));

        compStatus = label("", 17, TEXT); l.addView(compStatus);
        syncButton = button("Sync & start recording"); syncButton.setBackgroundColor(AMBER); syncButton.setTextColor(BG);
        syncButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { startCompanion(); } });
        l.addView(syncButton);
        compStopButton = button("Stop"); compStopButton.setBackgroundColor(RED); compStopButton.setTextColor(Color.WHITE);
        compStopButton.setVisibility(View.GONE);
        compStopButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { stopCompanionRecording(); } });
        l.addView(compStopButton);

        l.addView(label("Clips for this session", 17, DIM));
        compAdapter = makeAdapter(compNames);
        compList = new ListView(this); compList.setAdapter(compAdapter); compList.setBackgroundColor(BG);
        l.addView(compList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(140)));

        Button exportBtn = button("Export clips");
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(compCode()); } });
        l.addView(exportBtn);
        Button homeBtn = button("Home");
        homeBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { leaveCompanion(); } });
        l.addView(homeBtn);

        ScrollView sv = new ScrollView(this); sv.setBackgroundColor(BG); sv.addView(l);
        companionScreen = sv;
        updateCompMode();
    }

    private void updateCompMode() { styleSelected(brollButton, compVideoMode); styleSelected(dialogueButton, !compVideoMode); }

    private String compCode() {
        String c = compCodeEdit == null ? "" : compCodeEdit.getText().toString().trim().toUpperCase(Locale.US);
        return c;
    }

    private void setCompStatus(String s) { if (compStatus != null) compStatus.setText(s); }

    private void enterCompanion() {
        homeScreen.setVisibility(View.GONE); sessionScreen.setVisibility(View.GONE);
        companionScreen.setVisibility(View.VISIBLE);
        compCodeEdit.setText("");
        refreshCompList();
    }

    private void leaveCompanion() {
        try { if (compRecording) stopCompanionRecording(); } catch (Throwable ignored) {}
        closeCompanionEngine(false);
        destroyFlash(); releaseTone();
        handler.removeCallbacks(countdownRunnable); handler.removeCallbacks(rmsRunnable);
        flashOverlay.setVisibility(View.INVISIBLE);
        showHome();
    }

    private void closeCompanionEngine(boolean fromDestroy) {
        try { if (compEngine != null) { compEngine.setLumaListener(null); compEngine.close(); } } catch (Throwable ignored) {}
        compEngine = null;
    }

    private void destroyFlash() {
        if (flashHandle != 0) { try { NativeCore.nativeFlashDestroy(flashHandle); } catch (Throwable ignored) {} flashHandle = 0; }
    }

    private void startCompanion() {
        if (compRecording) return;
        final String c = compCode();
        if (c.length() < 3) { setCompStatus("Enter the session code (3+ letters) from the lead device."); return; }
        marks.clear();
        try {
            if (compVideoMode) {
                destroyFlash();
                try { flashHandle = NativeCore.nativeFlashCreate(); } catch (Throwable ignored) { flashHandle = 0; }
                if (compEngine == null) {
                    compEngine = new CameraEngine(this, new CameraEngine.ErrorListener() {
                        @Override public void onError(final String m) {
                            runOnUiThread(new Runnable() { @Override public void run() { setCompStatus("Camera error: " + m); } });
                        }
                    });
                    compEngine.openPreview(compPreview);
                }
                compRecordStartMs = SystemClock.elapsedRealtime();
                compEngine.setLumaListener(new CameraEngine.LumaListener() {
                    @Override public void onLuma(double mean, double[] grid) {
                        if (flashHandle != 0 && compRecording) {
                            try {
                                long now = SystemClock.elapsedRealtime();
                                if (NativeCore.nativeFlashFeed(flashHandle, mean, now)) marks.add(now - compRecordStartMs);
                            } catch (Throwable ignored) {}
                        }
                    }
                });
                File f = new File(clipsDir, Names.brollName(c));
                compRecording = true; // before start so pre-roll luma is fed
                if (!compEngine.startVideo(f)) {
                    compRecording = false;
                    try { compEngine.setLumaListener(null); } catch (Throwable ignored) {}
                    destroyFlash(); setCompStatus("Could not start video recording."); return;
                }
                compRecordStartMs = SystemClock.elapsedRealtime();
            } else {
                File f = new File(clipsDir, Names.dialogueName(c));
                try { wavHandle = NativeCore.nativeStartWav(f.getAbsolutePath()); } catch (Throwable ignored) { wavHandle = 0; }
                if (wavHandle == 0) { setCompStatus("Could not start audio recording."); return; }
                compRecording = true;
                compRecordStartMs = SystemClock.elapsedRealtime();
            }
        } catch (Throwable e) { compRecording = false; setCompStatus("Start failed: " + e.getMessage()); return; }
        syncButton.setVisibility(View.GONE); compStopButton.setVisibility(View.VISIBLE);
        countdownLeft = 3;
        handler.removeCallbacks(countdownRunnable);
        handler.post(countdownRunnable);
        refreshCompList();
    }

    private void stopCompanionRecording() {
        if (!compRecording) { syncButton.setVisibility(View.VISIBLE); compStopButton.setVisibility(View.GONE); return; }
        handler.removeCallbacks(countdownRunnable); handler.removeCallbacks(rmsRunnable);
        String c = compCode();
        try {
            if (compVideoMode) {
                if (compEngine != null) {
                    try { compEngine.stopVideo(); } catch (Throwable ignored) {}
                    try { compEngine.setLumaListener(null); } catch (Throwable ignored) {}
                }
                destroyFlash();
                if (!marks.isEmpty()) {
                    try {
                        JSONObject obj = new JSONObject(); obj.put("session_code", c);
                        JSONArray arr = new JSONArray();
                        for (Long m : marks) arr.put(m.longValue());
                        obj.put("flash_marks_ms", arr);
                        writeText(new File(clipsDir, "sync_marks_" + c + ".json"), obj.toString(2));
                    } catch (Throwable ignored) {}
                }
                setCompStatus("Video saved for session " + c + ".");
            } else {
                if (wavHandle != 0) { try { NativeCore.nativeStopWav(wavHandle); } catch (Throwable ignored) {} wavHandle = 0; }
                setCompStatus("Audio saved for session " + c + ".");
            }
        } catch (Throwable e) { setCompStatus("Stop failed: " + e.getMessage()); }
        compRecording = false;
        flashOverlay.setVisibility(View.INVISIBLE);
        syncButton.setVisibility(View.VISIBLE); compStopButton.setVisibility(View.GONE);
        refreshCompList();
    }

    private void ensureTone() {
        if (toneGen == null) { try { toneGen = new ToneGenerator(AudioManager.STREAM_MUSIC, 90); } catch (Throwable ignored) {} }
    }

    private void beep(boolean zero) {
        try {
            ensureTone();
            if (toneGen != null) {
                if (zero) toneGen.startTone(ToneGenerator.TONE_PROP_ACK, 350);
                else toneGen.startTone(ToneGenerator.TONE_PROP_BEEP, 120);
            }
        } catch (Throwable ignored) {}
    }

    private void releaseTone() {
        if (toneGen != null) { try { toneGen.release(); } catch (Throwable ignored) {} toneGen = null; }
    }

    // ---------- clips / files / export ----------

    private List<File> clipFiles(String forCode) {
        List<File> out = new ArrayList<File>();
        if (forCode == null || forCode.length() == 0 || clipsDir == null) return out;
        File[] files = clipsDir.listFiles();
        if (files == null) return out;
        for (File f : files) {
            String n = f.getName();
            if (f.isFile() && (n.contains("_" + forCode + "_") || n.contains("_" + forCode + "-"))) out.add(f);
        }
        Collections.sort(out, new Comparator<File>() {
            @Override public int compare(File a, File b) { return Long.compare(b.lastModified(), a.lastModified()); }
        });
        return out;
    }

    private void refreshSessionList() {
        sessionNames.clear();
        for (File f : clipFiles(code)) sessionNames.add(f.getName());
        if (sessionAdapter != null) sessionAdapter.notifyDataSetChanged();
    }

    private void refreshCompList() {
        compNames.clear();
        String c = compCode();
        if (c.length() == 0) { try { c = prefs.getCode(); } catch (Throwable ignored) {} }
        for (File f : clipFiles(c)) compNames.add(f.getName());
        if (compAdapter != null) compAdapter.notifyDataSetChanged();
    }

    private void writeText(File f, String text) throws Exception {
        FileOutputStream out = new FileOutputStream(f);
        out.write(text.getBytes("UTF-8")); out.close();
    }

    private String mimeFor(String name) {
        String n = name.toLowerCase(Locale.US);
        if (n.endsWith(".mp4")) return "video/mp4";
        if (n.endsWith(".wav")) return "audio/x-wav";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".json")) return "application/json";
        return "application/octet-stream";
    }

    private void copyStream(InputStream in, OutputStream out) throws Exception {
        byte[] buf = new byte[8192]; int r;
        while ((r = in.read(buf)) != -1) out.write(buf, 0, r);
    }

    private void exportClips(String forCode) {
        exportCode = forCode == null ? "" : forCode;
        if (exportCode.length() == 0) { try { exportCode = prefs.getCode(); } catch (Throwable ignored) {} }
        if (Build.VERSION.SDK_INT <= 28
            && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, PERM_EXPORT);
            return;
        }
        doExport(exportCode);
    }

    private void doExport(String forCode) {
        List<File> files = clipFiles(forCode);
        if (files.isEmpty()) { Toast.makeText(this, "Exported 0 clips to Downloads/Unwritten", Toast.LENGTH_LONG).show(); return; }
        int count = 0;
        try {
            if (Build.VERSION.SDK_INT >= 29) {
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
            } else {
                File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Unwritten");
                //noinspection ResultOfMethodCallIgnored
                dir.mkdirs();
                for (File f : files) {
                    FileInputStream in = new FileInputStream(f);
                    FileOutputStream out = new FileOutputStream(new File(dir, f.getName()));
                    copyStream(in, out); in.close(); out.close(); count++;
                }
            }
            Toast.makeText(this, "Exported " + count + " clips to Downloads/Unwritten", Toast.LENGTH_LONG).show();
        } catch (Throwable e) {
            Toast.makeText(this, "Export failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
        refreshSessionList(); refreshCompList();
    }
}
