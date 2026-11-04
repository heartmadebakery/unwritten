package org.tinio.unwritten;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
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

    // Hearth palette (docs/DESIGN.md): warm paper by default, a
    // matching dark set when the system is in night mode. Chosen once
    // in onCreate (a uiMode change recreates the activity), so every
    // builder below reads the right set. Names kept from the old dark
    // palette: BG canvas, PANEL surface, PRESSED sunken, TEXT ink,
    // DIM secondary ink, BRIGHT the ember accent, RED danger.
    private boolean night;
    private int BG, PANEL, PRESSED, TEXT, DIM, LINE, RING, BRIGHT, EMBER_PRESS,
            EMBER_INK, EMBER_SOFT, SAGE, SAGE_SOFT, HONEY, HONEY_SOFT, RED;
    // Cover washes (letter on wash), picked by washIndex(title).
    private int[] WASH, WASH_INK;
    private static final int MENU_CAMERA = 1;
    private static final int PERM_RECORD = 7;
    private static final int REQ_UPLOAD = 8;

    private File clipsDir;
    private final Handler handler = new Handler();

    private TextureView preview;
    private TextView status;
    private Button recordButton;
    private LinearLayout lessonContainer;
    private LinearLayout homeScreen, recordScreen, uploadScreen;
    private LinearLayout uploadHistory;
    private android.widget.ScrollView rootScroll;
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
    private Button exportBtn;
    private android.widget.Switch cloudToggleButton;
    // The Switch acts only on a real change: toggleCloudEnabled() flips
    // persisted state, so a programmatic setChecked must never flip it.
    private final android.widget.CompoundButton.OnCheckedChangeListener cloudSwitchListener =
        new android.widget.CompoundButton.OnCheckedChangeListener() {
            @Override public void onCheckedChanged(android.widget.CompoundButton b, boolean isChecked) {
                if (isChecked != cloudEnabledCfg()) toggleCloudEnabled();
            }
        };
    private TextView zoomLabel, micWarn, speechWarn, recBadge, dockHint;
    private android.widget.ImageView cloudGlyph;
    private LinearLayout zoomRow;
    private LinearLayout hubContainer;
    private JSONArray hubRows = new JSONArray();
    private JSONObject hubDetail;
    private String hubNotice = "";
    // Session parts: the hub session that takes, uploads and links made
    // now continue ("Add a part" on a hub session sets it; Home or
    // "Make it its own session" clears it). Null = each is its own.
    private String joinToVideoId = null, joinToTitle = null;
    private final List<LinearLayout> joinBanners = new ArrayList<LinearLayout>();
    private JSONObject ignoredById = new JSONObject();
    private JSONObject ignoredByTitle = new JSONObject();
    private SeekBar zoomSeek;
    private long speechQuietSince;
    private File lastLessonFile;
    // The take MediaRecorder is writing right now (null between
    // takes): not a session until the stop callback finalizes it.
    private volatile File liveTake;
    private final ExecutorService cloudExec = Executors.newCachedThreadPool();
    private final Set<String> cloudInFlight = new HashSet<String>();

    private final Runnable timerRunnable = new Runnable() {
        @Override public void run() {
            if (engine != null && engine.isRecording()) {
                long s = (SystemClock.elapsedRealtime() - recordStartMs) / 1000;
                String t = (s / 60) + ":" + String.format(Locale.US, "%02d", s % 60);
                recordButton.setText("■ Stop  " + t);
                if (recBadge != null) recBadge.setText("● REC  " + t);
                handler.postDelayed(this, 500);
            }
        }
    };

    // ---------- helpers ----------

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    private void applyPalette() {
        night = (getResources().getConfiguration().uiMode
                & android.content.res.Configuration.UI_MODE_NIGHT_MASK)
                == android.content.res.Configuration.UI_MODE_NIGHT_YES;
        BRIGHT = Color.parseColor("#D2452A");
        EMBER_PRESS = Color.parseColor("#B83A20");
        RED = Color.parseColor("#C23B22");
        if (!night) {
            BG = Color.parseColor("#FAF6F1"); PANEL = Color.WHITE; PRESSED = Color.parseColor("#F3ECE4");
            TEXT = Color.parseColor("#2A211C"); DIM = Color.parseColor("#6F625A");
            LINE = Color.parseColor("#EADFD3"); RING = Color.parseColor("#DCCFC2");
            EMBER_INK = Color.parseColor("#B83A20"); EMBER_SOFT = Color.parseColor("#FCE8E1");
            SAGE = Color.parseColor("#2F7A4B"); SAGE_SOFT = Color.parseColor("#E3F2E7");
            HONEY = Color.parseColor("#8A5A00"); HONEY_SOFT = Color.parseColor("#FFF3D6");
            WASH = new int[] { 0xFFFCE3D9, 0xFFFBEFD2, 0xFFE2EFE1, 0xFFDDEBF4, 0xFFECE3F3, 0xFFF2E3D8 };
            WASH_INK = new int[] { 0xFFB5432A, 0xFF8A5A00, 0xFF2F6B3F, 0xFF2B5F80, 0xFF6A4486, 0xFF8A4F2E };
        } else {
            BG = Color.parseColor("#171310"); PANEL = Color.parseColor("#221C18"); PRESSED = Color.parseColor("#2D2621");
            TEXT = Color.parseColor("#F7EFE6"); DIM = Color.parseColor("#B9AA9C");
            LINE = Color.parseColor("#3A312A"); RING = Color.parseColor("#5A4E44");
            EMBER_INK = Color.parseColor("#FF8A6B"); EMBER_SOFT = Color.parseColor("#3A2420");
            SAGE = Color.parseColor("#7FD39B"); SAGE_SOFT = Color.parseColor("#1F2E24");
            HONEY = Color.parseColor("#F2C46B"); HONEY_SOFT = Color.parseColor("#33281A");
            WASH = new int[] { 0xFF3A2420, 0xFF33281A, 0xFF1F2E24, 0xFF1C2A33, 0xFF2B2233, 0xFF33251C };
            WASH_INK = new int[] { 0xFFFF9C82, 0xFFF2C46B, 0xFF7FD39B, 0xFF8CC4E6, 0xFFC7A6E0, 0xFFE0A884 };
        }
    }

    private TextView label(String text, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(text); t.setTextSize(sp); t.setTextColor(color);
        t.setPadding(dp(4), dp(4), dp(4), dp(4));
        return t;
    }

    private static final android.graphics.Typeface MEDIUM =
        android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL);
    private static final android.graphics.Typeface BOLD =
        android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.BOLD);

    /** A rounded, flat fill (no ripple) — card and field backgrounds. */
    private android.graphics.drawable.Drawable rounded(int fill, int radiusDp) {
        android.graphics.drawable.GradientDrawable g = new android.graphics.drawable.GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(radiusDp));
        return g;
    }

    /** A rounded fill with the Material ripple a flat setBackgroundColor
     *  lacks — every tappable surface gets touch feedback. */
    private android.graphics.drawable.Drawable ripple(int fill, int radiusDp) {
        return ripple(rounded(fill, radiusDp), rounded(Color.WHITE, radiusDp));
    }

    private android.graphics.drawable.Drawable ripple(android.graphics.drawable.Drawable content,
                                                      android.graphics.drawable.Drawable mask) {
        return new android.graphics.drawable.RippleDrawable(
            android.content.res.ColorStateList.valueOf(night ? 0x33FFFFFF : 0x1F2A211C), content, mask);
    }

    /** Ripple for a row inside a card (the card clips the corners). */
    private android.graphics.drawable.Drawable rowRipple() {
        return new android.graphics.drawable.RippleDrawable(
            android.content.res.ColorStateList.valueOf(night ? 0x22FFFFFF : 0x142A211C), null,
            new android.graphics.drawable.ColorDrawable(Color.WHITE));
    }

    /** A card: rounded surface that clips its rows to the corners and,
     *  in light mode, floats on a soft Material elevation. */
    private void cardStyle(View v) {
        v.setBackground(rounded(PANEL, 20));
        v.setClipToOutline(true);
        v.setElevation(night ? 0 : dp(2));
    }

    /** Section header: sentence case, bold, with an optional subtitle. */
    private TextView sectionHeader(String text) {
        TextView t = label(text, 20, TEXT);
        t.setTypeface(BOLD);
        t.setPadding(dp(4), dp(22), dp(4), dp(8));
        return t;
    }

    /** Tonal button: rounded sunken fill, ripple, 52dp tall pill. */
    private Button button(String text) {
        return styledButton(text, PRESSED, TEXT);
    }

    /** The one primary action on a screen: filled ember, medium. */
    private Button primaryButton(String text, int fill) {
        Button b = styledButton(text, fill, 0xFFFFFFFF);
        b.setTypeface(MEDIUM);
        b.setMinHeight(dp(56)); b.setMinimumHeight(dp(56));
        return b;
    }

    private Button styledButton(String text, int fill, int textColor) {
        Button b = new Button(this);
        b.setText(text); b.setTextSize(17); b.setTextColor(textColor);
        b.setAllCaps(false);
        b.setTypeface(MEDIUM);
        b.setBackground(ripple(fill, 28));
        b.setStateListAnimator(null);
        b.setMinHeight(dp(52)); b.setMinimumHeight(dp(52));
        b.setPadding(dp(20), dp(10), dp(20), dp(10));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(6), 0, dp(6));
        b.setLayoutParams(lp);
        return b;
    }

    /** A pill chip: a status in words ("Uploading 42%", "In the cloud"). */
    private TextView chip(String text, int bg, int fg) {
        TextView t = new TextView(this);
        t.setText(text); t.setTextSize(13); t.setTextColor(fg);
        t.setTypeface(MEDIUM);
        t.setSingleLine(true);
        t.setBackground(rounded(bg, 14));
        t.setPadding(dp(10), dp(3), dp(10), dp(3));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(4), dp(6), 0);
        t.setLayoutParams(lp);
        return t;
    }

    /** A lesson wears the same warm wash everywhere: the sum of the
     *  title's UTF-16 code units, modulo the six cover pairs. */
    private static int washIndex(String title) {
        int n = 0;
        if (title != null) for (int i = 0; i < title.length(); i++) n += title.charAt(i);
        return n % 6;
    }

    private static String initialOf(String title) {
        if (title != null) for (int i = 0; i < title.length(); i++) {
            char ch = title.charAt(i);
            if (Character.isLetterOrDigit(ch)) return String.valueOf(Character.toUpperCase(ch));
        }
        return "\u2022";
    }

    /** A cover tile: the lesson's initial on its warm wash. */
    private TextView cover(String title, int sizeDp, int textSp, int radiusDp) {
        int w = washIndex(title);
        TextView t = new TextView(this);
        t.setText(initialOf(title));
        t.setTextSize(textSp);
        t.setTypeface(BOLD);
        t.setTextColor(WASH_INK[w]);
        t.setGravity(Gravity.CENTER);
        t.setBackground(rounded(WASH[w], radiusDp));
        t.setLayoutParams(new LinearLayout.LayoutParams(dp(sizeDp), dp(sizeDp)));
        t.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return t;
    }

    /** A 48dp round icon button with a ripple and a spoken label. */
    private android.widget.ImageButton iconButton(int glyph, int color, Integer bg, String desc,
                                                  View.OnClickListener onClick) {
        android.widget.ImageButton b = new android.widget.ImageButton(this);
        b.setImageDrawable(new Glyphs(glyph, color, dp(22)));
        b.setBackground(ripple(bg != null ? bg : Color.TRANSPARENT, 24));
        b.setScaleType(android.widget.ImageView.ScaleType.CENTER);
        b.setContentDescription(desc);
        b.setPadding(0, 0, 0, 0);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(48), dp(48));
        lp.setMargins(dp(2), 0, 0, 0);
        b.setLayoutParams(lp);
        if (onClick != null) b.setOnClickListener(onClick);
        return b;
    }

    /** A glyph in a rounded wash square (tiles, the Cloud row). */
    private android.widget.ImageView glyphBadge(int glyph, int fg, int bg, int sizeDp, int radiusDp) {
        android.widget.ImageView v = new android.widget.ImageView(this);
        v.setImageDrawable(new Glyphs(glyph, fg, dp(sizeDp / 2 + 2)));
        v.setScaleType(android.widget.ImageView.ScaleType.CENTER);
        v.setBackground(rounded(bg, radiusDp));
        v.setLayoutParams(new LinearLayout.LayoutParams(dp(sizeDp), dp(sizeDp)));
        v.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return v;
    }

    /** A home action tile: glyph on top, title and a line of help at the
     *  bottom; filled ember for the primary action, surface otherwise.
     *  Tiles dip a little while pressed and ripple, Material-style. */
    private LinearLayout actionTile(String title, String sub, int glyph, boolean primary,
                                    View.OnClickListener onClick) {
        final LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setPadding(dp(18), dp(18), dp(18), dp(18));
        tile.setMinimumHeight(dp(168));
        int fill = primary ? BRIGHT : PANEL;
        tile.setBackground(ripple(rounded(fill, 24), rounded(Color.WHITE, 24)));
        tile.setElevation(night && !primary ? 0 : dp(primary ? 6 : 2));
        tile.setClickable(true);
        tile.setFocusable(true);
        tile.setContentDescription(title + ". " + sub);
        tile.setOnClickListener(onClick);
        tile.setOnTouchListener(new View.OnTouchListener() {
            @Override public boolean onTouch(View v, android.view.MotionEvent e) {
                int a = e.getActionMasked();
                if (a == android.view.MotionEvent.ACTION_DOWN) v.animate().scaleX(0.96f).scaleY(0.96f).setDuration(120).start();
                else if (a == android.view.MotionEvent.ACTION_UP || a == android.view.MotionEvent.ACTION_CANCEL)
                    v.animate().scaleX(1f).scaleY(1f).setDuration(180).start();
                return false;
            }
        });
        tile.addView(glyphBadge(glyph, primary ? Color.WHITE : EMBER_INK,
                primary ? 0x33FFFFFF : EMBER_SOFT, 48, 16));
        View spacer = new View(this);
        tile.addView(spacer, new LinearLayout.LayoutParams(1, 0, 1f));
        TextView t = new TextView(this);
        t.setText(title); t.setTextSize(20); t.setTypeface(BOLD);
        t.setTextColor(primary ? Color.WHITE : TEXT);
        t.setPadding(0, dp(14), 0, dp(2));
        tile.addView(t);
        TextView st = new TextView(this);
        st.setText(sub); st.setTextSize(14);
        st.setTextColor(primary ? 0xE0FFFFFF : DIM);
        tile.addView(st);
        return tile;
    }

    // ---------- lifecycle ----------

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // External playback goes through TinyFileProvider (content://
        // with a read grant) — file:// intents arrive unreadable on
        // Android 7+, so there is no StrictMode bypass here.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        // Hearth: warm paper, or its dark set when the system is in
        // night mode (Theme.DeviceDefault.DayNight themes the dialogs,
        // toasts and widgets to match).
        applyPalette();
        // System bars and the action bar wear the app's own canvas,
        // with dark icons on the light canvas.
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        if (!night) {
            getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
        android.app.ActionBar bar = getActionBar();
        if (bar != null) {
            bar.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(BG));
            bar.setElevation(0);
        }
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
        // The ActionBar carries the app title now (screen titles + Up
        // in showScreen); the tagline lives on the home screen itself.
        l.setPadding(dp(18), dp(8), dp(18), dp(32));

        // One app, four screens. Home (record/upload actions with the
        // hub last) is the landing; record owns the viewfinder and
        // opens it only on entry, so landing never prompts for the
        // camera, with cloud and device sessions below. Upload offers
        // the system picker or Fetch from link, which is a screen of
        // its own — a picked video rides the exact session path of a
        // take.
        homeScreen = new LinearLayout(this);
        homeScreen.setOrientation(LinearLayout.VERTICAL);
        l.addView(homeScreen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        recordScreen = new LinearLayout(this);
        recordScreen.setOrientation(LinearLayout.VERTICAL);
        recordScreen.setVisibility(View.GONE);
        l.addView(recordScreen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        uploadScreen = new LinearLayout(this);
        uploadScreen.setOrientation(LinearLayout.VERTICAL);
        uploadScreen.setVisibility(View.GONE);
        l.addView(uploadScreen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        buildHomeScreen();
        buildUploadScreen();
        buildRecordScreen();

        status = label("", 16, TEXT); // hidden - status conveyed via list icons + toasts

        rootScroll = new ScrollView(MainActivity.this); rootScroll.setBackgroundColor(BG); rootScroll.addView(l);
        // Cards cast their elevation shadows past their own bounds.
        l.setClipChildren(false); l.setClipToPadding(false);
        setContentView(rootScroll);
    }

    private void buildHomeScreen() {
        // The ActionBar steps aside on home (showScreen hides it): a
        // greeting and a large title sit in the content instead, like
        // Material's expanded large top app bar.
        homeScreen.setClipChildren(false);
        TextView hello = label(greeting(), 15, DIM);
        hello.setTypeface(MEDIUM);
        hello.setPadding(dp(2), dp(18), dp(2), 0);
        homeScreen.addView(hello);
        TextView big = label("Unwritten Craft", 32, TEXT);
        big.setTypeface(BOLD);
        big.setPadding(dp(2), 0, dp(2), dp(4));
        homeScreen.addView(big);
        TextView tagline = label("Record, upload, and revisit craft lessons.", 16, DIM);
        tagline.setPadding(dp(2), 0, dp(2), dp(14));
        homeScreen.addView(tagline);

        // Two action tiles: Record (filled ember, the primary action)
        // and Upload video (its own screen: choose a file or fetch
        // from a link).
        LinearLayout tiles = new LinearLayout(this);
        tiles.setOrientation(LinearLayout.HORIZONTAL);
        tiles.setClipChildren(false);
        LinearLayout goRecord = actionTile("Record", "Film a lesson, the way you'd teach anyway",
                Glyphs.RECORD, true,
                new View.OnClickListener() { @Override public void onClick(View v) { showScreen("record"); } });
        LinearLayout upload = actionTile("Upload video", "From your phone or a link",
                Glyphs.UPLOAD, false,
                new View.OnClickListener() { @Override public void onClick(View v) { showScreen("upload"); } });
        // Both MATCH_PARENT: LinearLayout gives the pair one uniform height.
        LinearLayout.LayoutParams tl = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
        tl.setMargins(0, 0, dp(6), 0);
        tiles.addView(goRecord, tl);
        LinearLayout.LayoutParams tr = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
        tr.setMargins(dp(6), 0, 0, 0);
        tiles.addView(upload, tr);
        homeScreen.addView(tiles);

        // Hub: published lessons, same stories as the web hub. The hub
        // lives on the signer, so this section only fills when a signer
        // URL and token are configured and Cloud is on. The refresh
        // action is the pull-to-refresh analogue (no SwipeRefreshLayout
        // without AndroidX): the hub also reloads on return to home.
        LinearLayout hubHead = new LinearLayout(this);
        hubHead.setOrientation(LinearLayout.HORIZONTAL);
        hubHead.setGravity(Gravity.BOTTOM);
        LinearLayout hubTitles = new LinearLayout(this);
        hubTitles.setOrientation(LinearLayout.VERTICAL);
        hubTitles.addView(sectionHeader("Hub sessions"));
        TextView hubSub = label("Lessons the pipeline has written up", 14, DIM);
        hubSub.setPadding(dp(4), 0, dp(4), dp(10));
        hubTitles.addView(hubSub);
        hubHead.addView(hubTitles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        android.widget.ImageButton hubRefresh = iconButton(Glyphs.REFRESH, TEXT, null, "Refresh the hub",
                new View.OnClickListener() { @Override public void onClick(View v) { loadHub(); } });
        LinearLayout.LayoutParams rl = (LinearLayout.LayoutParams) hubRefresh.getLayoutParams();
        rl.setMargins(0, 0, 0, dp(8));
        hubHead.addView(hubRefresh);
        homeScreen.addView(hubHead);
        hubContainer = new LinearLayout(MainActivity.this);
        hubContainer.setOrientation(LinearLayout.VERTICAL);
        hubContainer.setBackground(rounded(PANEL, 20));
        hubContainer.setClipToOutline(true);
        hubContainer.setElevation(night ? 0 : dp(2));
        homeScreen.addView(hubContainer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    /** Upload video: two ways in — choose a file, or Fetch from link
     *  (its own screen). Toasts report each pick, here and nowhere else. */
    private void buildUploadScreen() {
        uploadScreen.setClipChildren(false);
        uploadScreen.addView(joinBannerView());
        TextView note = label("Add a lesson video. It is saved as a session and uploaded to Cloud, and the pipeline picks it up like a recording.", 15, DIM);
        note.setPadding(dp(2), dp(8), dp(2), dp(14));
        uploadScreen.addView(note);
        LinearLayout choose = optionRow("Choose a video", "From your library or Files", Glyphs.UPLOAD,
                new View.OnClickListener() { @Override public void onClick(View v) { pickUpload(); } });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 0, 0, dp(12));
        uploadScreen.addView(choose, lp);
        // Fetch from link lives here now, after the upload section —
        // no separate screen. Paste a link: YouTube/watch pages queue
        // to the pipeline fetcher, which downloads and processes them
        // like a take.
        LinearLayout linkCard = new LinearLayout(this);
        linkCard.setOrientation(LinearLayout.VERTICAL);
        linkCard.setPadding(dp(16), dp(14), dp(16), dp(10));
        cardStyle(linkCard);
        LinearLayout linkHead = new LinearLayout(this);
        linkHead.setOrientation(LinearLayout.HORIZONTAL);
        linkHead.setGravity(Gravity.CENTER_VERTICAL);
        linkHead.addView(glyphBadge(Glyphs.LINK, EMBER_INK, EMBER_SOFT, 36, 12));
        TextView linkTitle = label("Fetch from link", 17, TEXT);
        linkTitle.setTypeface(MEDIUM);
        linkTitle.setPadding(dp(12), 0, 0, 0);
        linkHead.addView(linkTitle);
        linkCard.addView(linkHead);
        linkCard.addView(label("A YouTube or video link, instead of a file", 14, DIM));
        final EditText urlInput = new EditText(this);
        urlInput.setHint("Paste a video link…");
        urlInput.setTextSize(16);
        urlInput.setTextColor(TEXT);
        urlInput.setHintTextColor(DIM);
        urlInput.setSingleLine(true);
        urlInput.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_GO);
        // The keyboard's Go submits, like iOS — the IME option alone
        // would leave Go a dead key.
        urlInput.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_GO) {
                    queueFetchUrl(urlInput.getText().toString().trim());
                    return true;
                }
                return false;
            }
        });
        urlInput.setBackground(rounded(PRESSED, 14));
        urlInput.setPadding(dp(16), dp(14), dp(16), dp(14));
        urlInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        LinearLayout.LayoutParams urlLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        urlLp.setMargins(0, dp(12), 0, dp(4));
        linkCard.addView(urlInput, urlLp);
        Button urlFetch = button("Fetch from link");
        urlFetch.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { queueFetchUrl(urlInput.getText().toString().trim()); } });
        linkCard.addView(urlFetch);
        uploadScreen.addView(linkCard, lp);
        TextView histTitle = label("Previous uploads and fetches", 17, TEXT);
        histTitle.setTypeface(MEDIUM);
        histTitle.setPadding(dp(2), dp(10), dp(2), dp(4));
        uploadScreen.addView(histTitle, lp);
        uploadHistory = new LinearLayout(this);
        uploadHistory.setOrientation(LinearLayout.VERTICAL);
        uploadScreen.addView(uploadHistory, lp);
    }

    /** Previous upload/fetch attempts, like the record screen lists
     *  sessions — an indicator that an upload or fetch occurred. */
    private void renderUploadHistory() {
        if (uploadHistory == null) return;
        uploadHistory.removeAllViews();
        uploadHistory.addView(label("Uploads", 14, DIM));
        boolean anyUp = false;
        for (File f : clipFiles()) {
            if (!f.getName().contains("upload_")) continue;
            anyUp = true;
            uploadHistory.addView(uploadHistoryRow(f.getName()));
        }
        if (!anyUp) uploadHistory.addView(label("No uploads yet.", 14, DIM));
        uploadHistory.addView(label("Fetches", 14, DIM));
        JSONArray attempts = fetchAttempts();
        if (attempts.length() == 0) {
            uploadHistory.addView(label("No links queued yet.", 14, DIM));
            return;
        }
        for (int i = 0; i < attempts.length(); i++) {
            try {
                JSONObject a = attempts.getJSONObject(i);
                String url = a.optString("url", "");
                long date = a.optLong("date", 0);
                boolean ok = a.optBoolean("ok", true);
                String when = date > 0 ? java.text.DateFormat
                        .getDateTimeInstance(java.text.DateFormat.SHORT, java.text.DateFormat.SHORT)
                        .format(new java.util.Date(date)) : "";
                uploadHistory.addView(historyTextRow(url,
                        (ok ? "Queued ✓" : "Couldn't queue") + (when.isEmpty() ? "" : " · " + when)));
            } catch (Throwable ignored) { }
        }
    }

    private LinearLayout uploadHistoryRow(final String name) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(2), dp(8), dp(2), dp(8));
        LinearLayout mid = new LinearLayout(this);
        mid.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        mid.setLayoutParams(mp);
        TextView title = label(displayDateFor(name), 16, TEXT);
        title.setTypeface(MEDIUM);
        title.setSingleLine(true);
        title.setEllipsize(android.text.TextUtils.TruncateAt.END);
        mid.addView(title);
        mid.addView(label(leftIconWords(name) + cloudSuffix(name), 14, DIM));
        row.addView(mid);
        JSONObject link = cloudLink(name);
        if (link != null && "failed".equals(link.optString("state", ""))) {
            Button retry = new Button(this);
            retry.setText("Retry");
            retry.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    retryCloud(name);
                    renderUploadHistory();
                }
            });
            row.addView(retry);
        }
        return row;
    }

    private LinearLayout historyTextRow(String title, String sub) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(dp(2), dp(8), dp(2), dp(8));
        TextView t = label(title, 16, TEXT);
        t.setSingleLine(true);
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        row.addView(t);
        row.addView(label(sub, 14, DIM));
        return row;
    }

    /** One tappable card of the Upload screen: glyph, title, a line of help. */
    private LinearLayout optionRow(String title, String sub, int glyph, View.OnClickListener onClick) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(16), dp(14), dp(16), dp(14));
        cardStyle(row);
        row.setClickable(true);
        row.setContentDescription(title);
        row.setOnClickListener(onClick);
        row.addView(glyphBadge(glyph, EMBER_INK, EMBER_SOFT, 44, 14));
        LinearLayout texts = new LinearLayout(this);
        texts.setOrientation(LinearLayout.VERTICAL);
        texts.setPadding(dp(14), 0, 0, 0);
        TextView t = label(title, 17, TEXT);
        t.setTypeface(MEDIUM);
        texts.addView(t);
        texts.addView(label(sub, 14, DIM));
        row.addView(texts, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        return row;
    }

    /** Fetch from link: a screen of its own, reached from Upload. */
    /** A personal hello over the title, by the phone's own clock. */
    private static String greeting() {
        int h = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY);
        return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    }

    private void buildRecordScreen() {
        // No custom back button: the ActionBar Up button and the system
        // Back button are the ways off this screen (see the action-bar
        // section below).
        recordScreen.setClipChildren(false);
        recordScreen.addView(joinBannerView());
        // Viewfinder with in-player overlay (playback appears inside viewfinder)
        viewfinderBox = new android.widget.FrameLayout(this);
        viewfinderBox.setBackground(rounded(Color.BLACK, 24));
        viewfinderBox.setClipToOutline(true);
        viewfinderBox.setElevation(night ? 0 : dp(4));
        preview = new TextureView(this);
        viewfinderBox.addView(preview, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(300)));
        localPlayer = new android.widget.VideoView(this);
        localPlayer.setVisibility(View.GONE);
        viewfinderBox.addView(localPlayer, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(300)));
        // Playback controls float over the bottom of the viewfinder as
        // round translucent buttons.
        playerControls = new LinearLayout(this);
        playerControls.setOrientation(LinearLayout.HORIZONTAL);
        playerControls.setGravity(Gravity.CENTER);
        playerControls.setVisibility(View.GONE);
        playerControls.setPadding(dp(6), dp(6), dp(6), dp(12));
        Button vfPlay = overlayButton("▶", "Play");
        vfPlay.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (localPlayer != null && isViewfinderPlaying) localPlayer.start(); } });
        Button vfPause = overlayButton("⏸", "Pause");
        vfPause.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (localPlayer != null) localPlayer.pause(); } });
        Button vfClose = overlayButton("✕", "Close player");
        vfClose.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { stopLocalPlayback(); } });
        playerControls.addView(vfPlay); playerControls.addView(vfPause); playerControls.addView(vfClose);
        android.widget.FrameLayout.LayoutParams ctrlLp = new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ctrlLp.gravity = Gravity.BOTTOM;
        viewfinderBox.addView(playerControls, ctrlLp);
        // REC badge over the viewfinder, like iOS and the web: the
        // Stop button text alone is not enough.
        recBadge = new TextView(this);
        recBadge.setText("● REC");
        recBadge.setTextSize(15); recBadge.setTextColor(0xFFFFFFFF);
        recBadge.setTypeface(BOLD);
        GradientDrawable badgeBg = new GradientDrawable();
        badgeBg.setShape(GradientDrawable.RECTANGLE);
        badgeBg.setCornerRadius(dp(20));
        badgeBg.setColor(Color.parseColor("#8C000000"));
        recBadge.setBackground(badgeBg);
        recBadge.setPadding(dp(12), dp(6), dp(14), dp(6));
        recBadge.setVisibility(View.GONE);
        android.widget.FrameLayout.LayoutParams badgeLp = new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        badgeLp.gravity = Gravity.TOP | Gravity.START;
        badgeLp.setMargins(dp(14), dp(14), dp(14), dp(14));
        viewfinderBox.addView(recBadge, badgeLp);
        LinearLayout.LayoutParams vfLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        vfLp.setMargins(0, dp(6), 0, 0);
        recordScreen.addView(viewfinderBox, vfLp);

        // Warning banners directly below the stage, like the web app.
        micWarn = label("🎤  No microphone. The mentor's words won't be recorded — and the mentor's words are the whole point. Check Settings to re-enable it.", 15, 0xFFFFFFFF);
        micWarn.setBackground(rounded(RED, 16));
        micWarn.setPadding(dp(14), dp(12), dp(14), dp(12));
        micWarn.setVisibility(View.GONE);
        recordScreen.addView(micWarn, bannerLp());
        speechWarn = label("🔇  Quiet for a while. No speech in the last minute — and the mentor's words are the whole point. Check the mic is close enough.", 15, HONEY);
        speechWarn.setBackground(rounded(HONEY_SOFT, 16));
        speechWarn.setPadding(dp(14), dp(12), dp(14), dp(12));
        speechWarn.setVisibility(View.GONE);
        recordScreen.addView(speechWarn, bannerLp());

        // Zoom directly below the viewfinder, in a pill track.
        zoomRow = new LinearLayout(this);
        zoomRow.setOrientation(LinearLayout.HORIZONTAL);
        zoomRow.setGravity(Gravity.CENTER_VERTICAL);
        zoomRow.setPadding(dp(4), 0, dp(8), 0);
        zoomRow.setBackground(rounded(PANEL, 28));
        zoomRow.setElevation(night ? 0 : dp(2));
        Button zoomOut = zoomButton("−");
        zoomSeek = new SeekBar(this);
        zoomSeek.setMax(100);
        zoomSeek.setProgressTintList(android.content.res.ColorStateList.valueOf(BRIGHT));
        zoomSeek.setThumbTintList(android.content.res.ColorStateList.valueOf(BRIGHT));
        zoomSeek.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(RING));
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        zoomSeek.setLayoutParams(sp);
        Button zoomIn = zoomButton("+");
        zoomLabel = label("1.0×", 14, DIM);
        zoomLabel.setTypeface(MEDIUM);
        zoomLabel.setMinWidth(dp(48));
        zoomLabel.setGravity(Gravity.CENTER);
        zoomRow.addView(zoomOut);
        zoomRow.addView(zoomSeek);
        zoomRow.addView(zoomIn);
        zoomRow.addView(zoomLabel);
        LinearLayout.LayoutParams zoomLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        zoomLp.setMargins(0, dp(10), 0, 0);
        recordScreen.addView(zoomRow, zoomLp);
        zoomOut.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(-0.2f); } });
        zoomIn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { nudgeZoom(+0.2f); } });
        zoomSeek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean fromUser) { if (fromUser) applyZoomFromSlider(); }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });

        // The shutter dock: the round shutter centred in a card, with a
        // line of help under it. The button keeps its shared "● Record"
        // / "■ Stop  m:ss" text for TalkBack; paintRecordButton draws it.
        LinearLayout dock = new LinearLayout(this);
        dock.setOrientation(LinearLayout.VERTICAL);
        dock.setGravity(Gravity.CENTER_HORIZONTAL);
        dock.setPadding(dp(16), dp(18), dp(16), dp(14));
        cardStyle(dock);
        dock.setClipToOutline(false);
        recordButton = primaryButton("● Record", BRIGHT);
        recordButton.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleRecord(); } });
        recordButton.setLayoutParams(new LinearLayout.LayoutParams(dp(88), dp(88)));
        dock.addView(recordButton);
        dockHint = label("", 15, DIM);
        dockHint.setGravity(Gravity.CENTER);
        dockHint.setPadding(dp(8), dp(10), dp(8), 0);
        dock.addView(dockHint);
        LinearLayout.LayoutParams dockLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        dockLp.setMargins(0, dp(12), 0, 0);
        recordScreen.addView(dock, dockLp);
        paintRecordButton(false);

        // Cloud: a real Switch row in a card (the camera switch lives in
        // the action bar menu, like a camera app's toolbar).
        LinearLayout cloudRow = new LinearLayout(this);
        cloudRow.setOrientation(LinearLayout.HORIZONTAL);
        cloudRow.setGravity(Gravity.CENTER_VERTICAL);
        cloudRow.setPadding(dp(12), dp(12), dp(16), dp(12));
        cardStyle(cloudRow);
        cloudGlyph = glyphBadge(Glyphs.CLOUD, SAGE, SAGE_SOFT, 44, 14);
        cloudRow.addView(cloudGlyph);
        LinearLayout cloudText = new LinearLayout(this);
        cloudText.setOrientation(LinearLayout.VERTICAL);
        cloudText.setPadding(dp(10), 0, dp(8), 0);
        TextView cloudTitle = label("Cloud", 17, TEXT);
        cloudTitle.setTypeface(MEDIUM);
        cloudTitle.setPadding(dp(4), 0, dp(4), 0);
        cloudText.addView(cloudTitle);
        TextView cloudSub = label("Upload a copy for streamed playback", 14, DIM);
        cloudSub.setPadding(dp(4), 0, dp(4), 0);
        cloudText.addView(cloudSub);
        cloudRow.addView(cloudText, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        // Kept under its old name: the contract tests and the other
        // paint/sweep paths still call it the cloud toggle.
        cloudToggleButton = new android.widget.Switch(this);
        cloudToggleButton.setThumbTintList(new android.content.res.ColorStateList(
            new int[][] { new int[] { android.R.attr.state_checked }, new int[] {} },
            new int[] { Color.WHITE, night ? DIM : Color.WHITE }));
        cloudToggleButton.setTrackTintList(new android.content.res.ColorStateList(
            new int[][] { new int[] { android.R.attr.state_checked }, new int[] {} },
            new int[] { SAGE, RING }));
        cloudToggleButton.setMinimumHeight(dp(48));
        cloudToggleButton.setOnCheckedChangeListener(cloudSwitchListener);
        cloudRow.addView(cloudToggleButton);
        LinearLayout.LayoutParams cloudLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        cloudLp.setMargins(0, dp(12), 0, 0);
        recordScreen.addView(cloudRow, cloudLp);

        // This device: a frame of the video, the date and a status chip,
        // then save / share actions — rows in one card.
        recordScreen.addView(sectionHeader("This device"));
        lessonContainer = new LinearLayout(MainActivity.this);
        lessonContainer.setOrientation(LinearLayout.VERTICAL);
        lessonContainer.setBackground(rounded(PANEL, 20));
        lessonContainer.setClipToOutline(true);
        lessonContainer.setElevation(night ? 0 : dp(2));
        recordScreen.addView(lessonContainer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        exportBtn = button("Export sessions to Downloads");
        LinearLayout.LayoutParams exLp = (LinearLayout.LayoutParams) exportBtn.getLayoutParams();
        exLp.setMargins(0, dp(12), 0, 0);
        exportBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { exportClips(); } });
        recordScreen.addView(exportBtn);

        TextView note = label("Every session is saved on this phone, and with Cloud on a copy is uploaded for streamed playback. Tap a session to play it; touch and hold to delete it from the phone and the cloud.", 14, DIM);
        note.setPadding(dp(4), dp(14), dp(4), dp(4));
        note.setLineSpacing(0, 1.2f);
        recordScreen.addView(note);

        // Debug overrides hide behind a small link at the bottom.
        Button advancedLink = new Button(this);
        advancedLink.setText("Advanced settings");
        advancedLink.setTextSize(14); advancedLink.setTextColor(DIM); advancedLink.setAllCaps(false);
        advancedLink.setPaintFlags(advancedLink.getPaintFlags() | android.graphics.Paint.UNDERLINE_TEXT_FLAG);
        advancedLink.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        advancedLink.setBackground(ripple(Color.TRANSPARENT, 12));
        advancedLink.setStateListAnimator(null);
        advancedLink.setMinHeight(dp(48)); advancedLink.setMinimumHeight(dp(48));
        advancedLink.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showCloudSettings(); } });
        recordScreen.addView(advancedLink);
    }

    private LinearLayout.LayoutParams bannerLp() {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(10), 0, 0);
        return lp;
    }

    /** A round translucent button floating over the video. */
    private Button overlayButton(String text, String desc) {
        Button b = new Button(this);
        b.setText(text); b.setTextSize(16); b.setTextColor(Color.WHITE); b.setAllCaps(false);
        b.setBackground(ripple(Color.parseColor("#8C000000"), 24));
        b.setStateListAnimator(null);
        b.setContentDescription(desc);
        b.setMinWidth(0); b.setMinimumWidth(0); b.setMinHeight(0); b.setMinimumHeight(0);
        b.setPadding(0, 0, 0, 0);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(48), dp(48));
        lp.setMargins(dp(6), 0, dp(6), 0);
        b.setLayoutParams(lp);
        return b;
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
            else { pendingRecord = false; showError("Camera and microphone permission denied — enable them in Settings to record."); }
        }
    }

    // ---------- screens & upload ----------

    private void showScreen(String name) {
        currentScreen = name;
        boolean home = "home".equals(name);
        boolean record = "record".equals(name);
        if (home) clearJoinTarget();
        paintJoinBanners();
        android.app.ActionBar bar = getActionBar();
        if (bar != null) {
            bar.setTitle(home ? "Unwritten Craft" : record ? "Record" : "Upload video");
            bar.setDisplayHomeAsUpEnabled(!home);
            // Home carries its own greeting and large title; the bar
            // returns with the Up arrow on every other screen.
            if (home) bar.hide(); else bar.show();
        }
        if (rootScroll != null) rootScroll.scrollTo(0, 0);
        invalidateOptionsMenu();
        if (homeScreen != null) homeScreen.setVisibility(home ? View.VISIBLE : View.GONE);
        if (recordScreen != null) recordScreen.setVisibility(record ? View.VISIBLE : View.GONE);
        if (uploadScreen != null) uploadScreen.setVisibility("upload".equals(name) ? View.VISIBLE : View.GONE);
        if (record) {
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
            if (home) loadHub();
        }
        // The upload screen lists previous attempts: refresh on entry
        // so a just-saved pick shows immediately.
        if ("upload".equals(name)) renderUploadHistory();
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

    // Fetch attempts: links queued to the pipeline for fetching, logged
    // locally (newest first, capped) so the upload screen can list them
    // afterwards — the pipeline's outcome shows up in the hub.
    private JSONArray fetchAttempts() {
        try { return new JSONArray(cloudPrefs().getString("fetchAttempts", "[]")); }
        catch (Throwable ignored) { return new JSONArray(); }
    }
    private void logFetchAttempt(String url, boolean ok) {
        try {
            JSONArray prev = fetchAttempts();
            JSONObject e = new JSONObject();
            e.put("url", url);
            e.put("date", System.currentTimeMillis());
            e.put("ok", ok);
            JSONArray next = new JSONArray();
            next.put(e);
            for (int i = 0; i < prev.length() && next.length() < 20; i++) next.put(prev.get(i));
            cloudPrefs().edit().putString("fetchAttempts", next.toString()).apply();
        } catch (Throwable ignored) { }
    }

    private void queueFetchUrl(final String url) {
        if (url.isEmpty()) {
            Toast.makeText(this, "Paste a link first.", Toast.LENGTH_SHORT).show();
            return;
        }
        if (!HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) {
            Toast.makeText(this, "Queuing needs the signer token — rebuild the app to stamp one.", Toast.LENGTH_LONG).show();
            return;
        }
        Toast.makeText(this, "⬇ Queuing…", Toast.LENGTH_SHORT).show();
        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
        // Continuing a session: the fetched video becomes its next part.
        final String join = joinToVideoId, joinTitle = joinToTitle;
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                new HubClient(surl, stok).queueFetchJob(url, join);
                logFetchAttempt(url, true);
            } catch (final Exception e) {
                logFetchAttempt(url, false);
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Couldn't queue that link (" + e.getMessage() + ")", Toast.LENGTH_LONG).show();
                } });
                return;
            }
            runOnUiThread(new Runnable() { @Override public void run() {
                Toast.makeText(MainActivity.this, "✅ Queued — the pipeline will fetch the video."
                        + (join == null ? "" : " It joins " + joinTitle + " as its next part."), Toast.LENGTH_LONG).show();
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
        // The bytes land under a name the list ignores and rename into
        // place only when complete: a refresh mid-copy must never list
        // (or sweep up and upload) half a lesson.
        final File part = new File(clipsDir, dest.getName() + ".part");
        Toast.makeText(this, "Copying upload…", Toast.LENGTH_SHORT).show();
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                InputStream in = getContentResolver().openInputStream(uri);
                if (in == null) throw new IOException("Could not open the picked file.");
                OutputStream out = new java.io.FileOutputStream(part);
                try {
                    copyStream(in, out);
                } finally {
                    try { in.close(); } catch (Throwable ignored) {}
                    try { out.close(); } catch (Throwable ignored) {}
                }
                if (!part.renameTo(dest)) throw new IOException("Could not save the copied upload.");
            } catch (final Exception e) {
                try { part.delete(); } catch (Throwable ignored) {}
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Upload failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                } });
                return;
            }
            markJoin(dest.getName());
            runOnUiThread(new Runnable() { @Override public void run() {
                refreshClipList();
                maybeCloudUpload(dest);
                renderUploadHistory();
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
                    // cleanly. A live take keeps its UI. Errors arrive
                    // on the camera thread: Handler calls are safe
                    // here, but the view writes hop to the UI thread
                    // (a view write here throws, and the engine
                    // swallows it, stranding "■ Stop").
                    if (engine == null || !engine.isRecording()) {
                        handler.removeCallbacks(timerRunnable);
                        handler.removeCallbacks(speechRunnable);
                        runOnUiThread(new Runnable() { @Override public void run() {
                            if (engine != null && engine.isRecording()) return;
                            liveTake = null;
                            hideSpeechWarn();
                            recordButton.setText("● Record"); paintRecordButton(false);
                            if (recBadge != null) recBadge.setVisibility(View.GONE);
                        } });
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

    /** The shutter: a ring with an ember disc while idle, a rounded
     *  ember square while recording — the camera idiom, on a ripple. The
     *  button text stays the shared "● Record" / "■ Stop  m:ss" for
     *  TalkBack; it is drawn transparent. The dock's hint follows. */
    private void paintRecordButton(boolean recording) {
        if (recordButton == null) return;
        GradientDrawable ring = new GradientDrawable();
        ring.setShape(GradientDrawable.OVAL);
        ring.setStroke(dp(5), RING);
        GradientDrawable core = new GradientDrawable();
        core.setColor(BRIGHT);
        int inset;
        if (recording) { core.setCornerRadius(dp(9)); inset = dp(26); }
        else { core.setShape(GradientDrawable.OVAL); inset = dp(11); }
        android.graphics.drawable.LayerDrawable face = new android.graphics.drawable.LayerDrawable(
            new android.graphics.drawable.Drawable[] { ring, core });
        face.setLayerInset(1, inset, inset, inset, inset);
        GradientDrawable mask = new GradientDrawable();
        mask.setShape(GradientDrawable.OVAL);
        mask.setColor(Color.WHITE);
        recordButton.setBackground(ripple(face, mask));
        recordButton.setTextColor(Color.TRANSPARENT);
        recordButton.setPadding(0, 0, 0, 0);
        recordButton.setMinWidth(0); recordButton.setMinimumWidth(0);
        if (dockHint != null) dockHint.setText(recording
                ? "Recording — teach the way you'd teach anyway. Tap to stop."
                : "Tap to record a lesson — teach the way you'd teach anyway.");
    }

    private void showMicWarn() { if (micWarn != null) micWarn.setVisibility(View.VISIBLE); }
    private void hideMicWarn() { if (micWarn != null) micWarn.setVisibility(View.GONE); }
    private void showSpeechWarn() { if (speechWarn != null) speechWarn.setVisibility(View.VISIBLE); }
    private void hideSpeechWarn() { if (speechWarn != null) speechWarn.setVisibility(View.GONE); }
    /** The action-bar camera item names the camera it would switch TO. */
    private void paintCamToggle() { invalidateOptionsMenu(); }

    private void switchCamera() {
        if (engine == null || engine.isRecording()) return;
        engine.switchCamera();
        handler.postDelayed(new Runnable() { @Override public void run() { paintCamToggle(); refreshZoomUi(); } }, 1200);
        handler.postDelayed(new Runnable() { @Override public void run() { refreshZoomUi(); } }, 2500);
    }

    /** A round 48dp − / + zoom button inside the zoom pill. */
    private Button zoomButton(String text) {
        Button b = new Button(this);
        b.setText(text); b.setTextSize(22); b.setTextColor(TEXT);
        b.setAllCaps(false);
        b.setBackground(ripple(Color.TRANSPARENT, 24));
        b.setStateListAnimator(null);
        b.setMinWidth(0); b.setMinimumWidth(0);
        b.setMinHeight(0); b.setMinimumHeight(0);
        b.setPadding(0, 0, 0, 0);
        b.setLayoutParams(new LinearLayout.LayoutParams(dp(48), dp(48)));
        return b;
    }

    // ---------- action bar ----------

    @Override public boolean onCreateOptionsMenu(android.view.Menu menu) {
        android.view.MenuItem cam = menu.add(0, MENU_CAMERA, 0, "Back camera");
        cam.setIcon(new Glyphs(Glyphs.CAMERA, TEXT, dp(24)));
        cam.setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS);
        return true;
    }

    @Override public boolean onPrepareOptionsMenu(android.view.Menu menu) {
        android.view.MenuItem cam = menu.findItem(MENU_CAMERA);
        if (cam != null) {
            cam.setVisible("record".equals(currentScreen));
            cam.setTitle(engine != null && engine.isFront()
                    ? "Front camera — switch to back" : "Back camera — switch to front");
        }
        return true;
    }

    @Override public boolean onOptionsItemSelected(android.view.MenuItem item) {
        if (item.getItemId() == android.R.id.home) { onBackPressed(); return true; }
        if (item.getItemId() == MENU_CAMERA) { switchCamera(); return true; }
        return super.onOptionsItemSelected(item);
    }

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
                liveTake = f;
                recordStartMs = SystemClock.elapsedRealtime();
                recordButton.setText("■ Stop  0:00"); paintRecordButton(true);
                recordButton.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                if (recBadge != null) { recBadge.setText("● REC  0:00"); recBadge.setVisibility(View.VISIBLE); }
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
                // now is the file complete and safe to list and upload
                // (and to read a duration from).
                liveTake = null;
                if (lastLessonFile != null
                        && (!lastLessonFile.exists() || lastLessonFile.length() == 0)) {
                    // The engine drops a take stopped too early, and a
                    // zero-byte file is no lesson either: say so out
                    // loud, like iOS and the web, instead of a silent
                    // no-row (or an empty row that would upload).
                    try { lastLessonFile.delete(); } catch (Throwable ignored) {}
                    lastLessonFile = null;
                    showError("⚠️ That take was empty — nothing was captured. Record the lesson again.");
                }
                if (lastLessonFile != null) durationCache.remove(lastLessonFile.getName());
                if (lastLessonFile != null) markJoin(lastLessonFile.getName());
                refreshClipList();
                if (lastLessonFile != null) maybeCloudUpload(lastLessonFile);
                // A stop that finishes off the record screen (the up arrow
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
        recordButton.setText("● Record"); paintRecordButton(false);
        recordButton.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
        if (recBadge != null) recBadge.setVisibility(View.GONE);
    }

    // ---------- clips / files / export ----------

    private List<File> clipFiles() {
        List<File> out = new ArrayList<File>();
        if (clipsDir == null) return out;
        File[] files = clipsDir.listFiles();
        if (files == null) return out;
        // The take being recorded is not a session yet: listed, it
        // could be played, deleted, or uploaded half written.
        File live = liveTake;
        for (File f : files) {
            if (live != null && f.getName().equals(live.getName())) continue;
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

    // One background probe per session gives both its length and a
    // frame of the video for the row's thumbnail (MediaMetadataRetriever
    // off the UI thread; the caches are only touched on the UI thread).
    private final Map<String,String> durationCache = new java.util.HashMap<String,String>();
    private final Map<String,android.graphics.Bitmap> thumbCache = new java.util.HashMap<String,android.graphics.Bitmap>();
    private final Set<String> probing = new HashSet<String>();

    private String formatDuration(int sec) {
        if (sec <= 0) return "";
        int h = sec / 3600, m = (sec / 60) % 60, s = sec % 60;
        if (h > 0) return String.format(Locale.US, "%d:%02d:%02d", h, m, s);
        return String.format(Locale.US, "%d:%02d", m, s);
    }

    private String durationFor(String name) {
        if (durationCache.containsKey(name)) return durationCache.get(name);
        probeClip(name);
        return "";
    }

    private android.graphics.Bitmap thumbFor(String name) {
        if (!durationCache.containsKey(name)) probeClip(name);
        return thumbCache.get(name);
    }

    private void probeClip(final String name) {
        if (probing.contains(name) || clipsDir == null) return;
        probing.add(name);
        final File f = new File(clipsDir, name);
        cloudExec.execute(new Runnable() { @Override public void run() {
            String out = "";
            android.graphics.Bitmap thumb = null;
            android.media.MediaMetadataRetriever mmr = new android.media.MediaMetadataRetriever();
            try {
                mmr.setDataSource(f.getAbsolutePath());
                String dur = mmr.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_DURATION);
                long ms = 0;
                if (dur != null) {
                    ms = Long.parseLong(dur);
                    long s = ms / 1000;
                    long m = s / 60;
                    long h = m / 60;
                    s = s % 60; m = m % 60;
                    if (h > 0) out = String.format(Locale.US, "%d:%02d:%02d", h, m, s);
                    else out = String.format(Locale.US, "%d:%02d", m, s);
                }
                android.graphics.Bitmap frame = mmr.getFrameAtTime(Math.min(1000000L, ms * 500L),
                        android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
                if (frame != null) {
                    int side = Math.min(frame.getWidth(), frame.getHeight());
                    android.graphics.Bitmap sq = android.graphics.Bitmap.createBitmap(frame,
                            (frame.getWidth() - side) / 2, (frame.getHeight() - side) / 2, side, side);
                    thumb = android.graphics.Bitmap.createScaledBitmap(sq, dp(56), dp(56), true);
                }
            } catch (Throwable ignored) {
            } finally {
                try { mmr.release(); } catch (Throwable ignored) {}
            }
            final String fOut = out;
            final android.graphics.Bitmap fThumb = thumb;
            runOnUiThread(new Runnable() { @Override public void run() {
                probing.remove(name);
                durationCache.put(name, fOut);
                if (fThumb != null) thumbCache.put(name, fThumb);
                refreshClipList();
            } });
        } });
    }

    // Copying a long lesson takes seconds: both exports run on the
    // background pool (on the UI thread it is an ANR) and report back
    // with a Toast.
    private void downloadSingle(String name) {
        final File f = new File(clipsDir, name);
        if (!f.exists()) { Toast.makeText(this, "File missing.", Toast.LENGTH_SHORT).show(); return; }
        Toast.makeText(this, "Saving " + f.getName() + " to Downloads…", Toast.LENGTH_SHORT).show();
        cloudExec.execute(new Runnable() { @Override public void run() {
            String msg;
            try {
                exportToDownloads(getContentResolver(), f);
                msg = "Saved " + f.getName() + " to Downloads/Unwritten";
            } catch (Throwable e) {
                msg = "Download failed: " + e.getMessage();
            }
            final String toast = msg;
            runOnUiThread(new Runnable() { @Override public void run() {
                Toast.makeText(MainActivity.this, toast, Toast.LENGTH_LONG).show();
            } });
        } });
    }

    /** A 56dp video frame with the length on it; a warm cover with a
     *  video (or mic) glyph until the frame is ready. */
    private View thumbView(String name) {
        android.widget.FrameLayout box = new android.widget.FrameLayout(this);
        box.setBackground(rounded(Color.BLACK, 14));
        box.setClipToOutline(true);
        android.graphics.Bitmap bmp = thumbFor(name);
        String dur = durationFor(name);
        if (bmp != null) {
            android.widget.ImageView iv = new android.widget.ImageView(this);
            iv.setImageBitmap(bmp);
            iv.setScaleType(android.widget.ImageView.ScaleType.CENTER_CROP);
            box.addView(iv, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        } else {
            int w = washIndex(name);
            box.setBackground(rounded(WASH[w], 14));
            android.widget.ImageView iv = new android.widget.ImageView(this);
            String mime = mimeFor(name);
            iv.setImageDrawable(new Glyphs(mime != null && mime.startsWith("audio") ? Glyphs.MIC : Glyphs.VIDEO, WASH_INK[w], dp(24)));
            iv.setScaleType(android.widget.ImageView.ScaleType.CENTER);
            box.addView(iv, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        }
        if (!dur.isEmpty()) {
            TextView d = new TextView(this);
            d.setText(dur); d.setTextSize(11); d.setTextColor(Color.WHITE); d.setTypeface(MEDIUM);
            d.setBackground(rounded(Color.parseColor("#9E000000"), 6));
            d.setPadding(dp(5), dp(1), dp(5), dp(1));
            android.widget.FrameLayout.LayoutParams dl = new android.widget.FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            dl.gravity = Gravity.BOTTOM | Gravity.END;
            dl.setMargins(0, 0, dp(4), dp(4));
            box.addView(d, dl);
        }
        box.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        box.setLayoutParams(new LinearLayout.LayoutParams(dp(56), dp(56)));
        return box;
    }

    private void addRowButton(LinearLayout row, int glyph, int color, Integer bg, String desc,
                              View.OnClickListener onClick) {
        // Every right-hand action is a 48dp round target with a ripple.
        row.addView(iconButton(glyph, color, bg, desc, onClick));
    }

    private void refreshClipList() {
        clipNames.clear();
        for (File f : clipFiles()) clipNames.add(f.getName());
        if (lessonContainer == null) return;
        lessonContainer.removeAllViews();
        if (clipNames.isEmpty()) {
            // Empty state: a glyph in an ember wash, a title, one line of help.
            LinearLayout empty = new LinearLayout(this);
            empty.setOrientation(LinearLayout.VERTICAL);
            empty.setGravity(Gravity.CENTER_HORIZONTAL);
            empty.setPadding(dp(20), dp(24), dp(20), dp(24));
            android.widget.ImageView eg = glyphBadge(Glyphs.VIDEO, EMBER_INK, EMBER_SOFT, 56, 28);
            empty.addView(eg);
            TextView et = label("Nothing yet.", 17, TEXT);
            et.setTypeface(MEDIUM);
            et.setGravity(Gravity.CENTER);
            et.setPadding(dp(4), dp(10), dp(4), 0);
            empty.addView(et);
            TextView eh = label("Sessions you record or upload appear here.", 14, DIM);
            eh.setGravity(Gravity.CENTER);
            empty.addView(eh);
            lessonContainer.addView(empty);
            return;
        }
        boolean first = true;
        for (final String name : clipNames) {
            if (!first) {
                View divider = new View(this);
                divider.setBackgroundColor(LINE);
                LinearLayout.LayoutParams dl = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1);
                dl.setMargins(dp(82), 0, 0, 0);
                lessonContainer.addView(divider, dl);
            }
            first = false;
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setBackground(rowRipple());
            row.setMinimumHeight(dp(80));
            row.setPadding(dp(12), dp(10), dp(6), dp(10));

            // left: a frame of the video (the old cloud/device icon is a chip now)
            View left = thumbView(name);
            row.addView(left);

            // middle: the date, then the status in words
            String dur = durationFor(name);
            LinearLayout mid = new LinearLayout(this);
            mid.setOrientation(LinearLayout.VERTICAL);
            mid.setPadding(dp(14), 0, dp(6), 0);
            LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            mid.setLayoutParams(mp);
            TextView date = new TextView(this);
            date.setText(displayDateFor(name));
            date.setTextColor(TEXT); date.setTextSize(16); date.setTypeface(MEDIUM);
            date.setSingleLine(true);
            date.setEllipsize(android.text.TextUtils.TruncateAt.END);
            mid.addView(date);
            LinearLayout chips = new LinearLayout(this);
            chips.setOrientation(LinearLayout.HORIZONTAL);
            mid.addView(chips);
            row.addView(mid);
            // whole row plays in the viewfinder; the right buttons are separate
            row.setClickable(true);
            View.OnClickListener playClick = new View.OnClickListener() { @Override public void onClick(View v) { playInViewfinder(name); } };
            row.setOnClickListener(playClick);
            row.setContentDescription("Session " + displayDateFor(name) + (dur.isEmpty() ? "" : ", " + dur)
                    + ". " + leftIconWords(name) + ". Tap to play, touch and hold to delete.");

            // right: save a copy always; then share when ready, progress
            // while uploading, a spinner while preparing, retry on failure
            JSONObject link = cloudLink(name);
            if (link != null && !link.optString("joinTo", "").isEmpty()) {
                String jt = link.optString("joinTitle", "a session");
                chips.addView(link.optBoolean("joined", false)
                        ? chip("Part of " + jt, SAGE_SOFT, SAGE)
                        : chip("Joins " + jt + " after upload", HONEY_SOFT, HONEY));
            }
            String st = link == null ? "" : link.optString("state", "");
            boolean isReady = "ready".equals(st);
            if (link == null) {
                chips.addView(chip("On this phone", PRESSED, DIM));
                addRowButton(row, Glyphs.DOWNLOAD, TEXT, null, "Save a copy", new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
            } else if (isReady) {
                // Cloud-linking never removes the on-device download:
                // ready rows keep ↓ next to ↗.
                chips.addView(chip("In the cloud", SAGE_SOFT, SAGE));
                addRowButton(row, Glyphs.DOWNLOAD, TEXT, null, "Save a copy", new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
                addRowButton(row, Glyphs.SHARE, TEXT, PRESSED, "Share session link", new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLinkFor(name); } });
            } else {
                addRowButton(row, Glyphs.DOWNLOAD, TEXT, null, "Save a copy", new View.OnClickListener() { @Override public void onClick(View v) { downloadSingle(name); } });
                // uploading: progress; processing: share once it has an id; failed: retry
                if ("uploading".equals(st)) {
                    int pct = link.optInt("progress", 0);
                    chips.addView(chip("Uploading " + pct + "%", EMBER_SOFT, EMBER_INK));
                    TextView ring = new TextView(this);
                    ring.setText(pct + "%");
                    ring.setTextSize(10); ring.setTextColor(EMBER_INK); ring.setTypeface(BOLD);
                    ring.setGravity(Gravity.CENTER);
                    ring.setBackground(progressRing(pct));
                    ring.setContentDescription("Uploading " + pct + " percent");
                    LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(40), dp(40));
                    bp.setMargins(dp(6), 0, dp(4), 0);
                    ring.setLayoutParams(bp);
                    row.addView(ring);
                } else if ("processing".equals(st)) {
                    chips.addView(chip("Preparing", HONEY_SOFT, HONEY));
                    String vid = link.optString("videoId", "");
                    if (!vid.isEmpty()) {
                        addRowButton(row, Glyphs.SHARE, DIM, PRESSED, "Share session link", new View.OnClickListener() { @Override public void onClick(View v) { shareCloudLinkFor(name); } });
                    } else {
                        android.widget.ProgressBar spin = new android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleSmall);
                        spin.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(HONEY));
                        spin.setContentDescription("Preparing");
                        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(24), dp(24));
                        bp.setMargins(dp(14), 0, dp(12), 0);
                        spin.setLayoutParams(bp);
                        row.addView(spin);
                    }
                } else if ("failed".equals(st)) {
                    TextView retryChip = chip("Upload failed · Retry", EMBER_SOFT, EMBER_INK);
                    retryChip.setClickable(true);
                    retryChip.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { retryCloud(name); } });
                    chips.addView(retryChip);
                    android.widget.ImageButton stv = iconButton(Glyphs.RETRY, EMBER_INK, null, "Retry cloud upload", null);
                    stv.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { retryCloud(name); } });
                    row.addView(stv);
                }
            }

            // ignored badge: takes the pipeline operator set aside
            // never reach the hub; the reason rides along for readers
            String ignReason = ignoredReasonFor(name);
            if (ignReason != null) {
                TextView stv = chip("Ignored", PRESSED, DIM);
                stv.setContentDescription(ignReason.isEmpty() ? "Ignored by the operator" : "Ignored by the operator: " + ignReason);
                chips.addView(stv);
            }

            // long-press row to delete
            View.OnLongClickListener longDelete = new View.OnLongClickListener() {
                @Override public boolean onLongClick(View v) { confirmDeleteLesson(name); return true; }
            };
            row.setOnLongClickListener(longDelete);

            lessonContainer.addView(row);
        }
        // Cloud progress changed: the upload screen's history shows the
        // same session states, so refresh it alongside.
        renderUploadHistory();
    }

    /** Upload progress as a ring: a sunken track with an ember arc. */
    private android.graphics.drawable.Drawable progressRing(final int pct) {
        final android.graphics.Paint p = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        p.setStyle(android.graphics.Paint.Style.STROKE);
        p.setStrokeWidth(dp(4));
        p.setStrokeCap(android.graphics.Paint.Cap.ROUND);
        return new android.graphics.drawable.Drawable() {
            @Override public void draw(android.graphics.Canvas c) {
                android.graphics.RectF r = new android.graphics.RectF(getBounds());
                r.inset(dp(3), dp(3));
                p.setColor(PRESSED);
                c.drawOval(r, p);
                p.setColor(BRIGHT);
                c.drawArc(r, -90, 360f * Math.max(0, Math.min(100, pct)) / 100f, false, p);
            }
            @Override public void setAlpha(int alpha) { }
            @Override public void setColorFilter(android.graphics.ColorFilter cf) { }
            @Override public int getOpacity() { return android.graphics.PixelFormat.TRANSLUCENT; }
        };
    }

    /** The left icon's link state, in words (for TalkBack). */
    private String leftIconWords(String name) {
        String icon = leftIconFor(name);
        if ("\uD83D\uDCF1".equals(icon)) return "On this phone";
        if ("\u2601\u2191".equals(icon)) return "Uploading";
        if ("\u2601\u2026".equals(icon)) return "Preparing";
        if ("\u2601!".equals(icon)) return "Upload failed";
        return "In the cloud";
    }

    private String mimeFor(String name) {
        String n = name.toLowerCase(Locale.US);
        if (n.endsWith(".mp4")) return "video/mp4";
        if (n.endsWith(".wav")) return "audio/x-wav";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".webm")) return "video/webm";
        if (n.endsWith(".mov")) return "video/quicktime";
        if (n.endsWith(".mkv")) return "video/x-matroska";
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
        final List<File> files = clipFiles();
        if (files.isEmpty()) { Toast.makeText(this, "Exported 0 sessions to Downloads/Unwritten", Toast.LENGTH_LONG).show(); return; }
        Toast.makeText(this, "Exporting " + files.size() + " sessions to Downloads…", Toast.LENGTH_SHORT).show();
        cloudExec.execute(new Runnable() { @Override public void run() {
            int count = 0, failed = 0;
            ContentResolver cr = getContentResolver();
            for (File f : files) {
                try {
                    exportToDownloads(cr, f);
                    count++;
                } catch (Throwable e) {
                    failed++;
                }
            }
            String msg = "Exported " + count + " sessions to Downloads/Unwritten";
            if (failed > 0) msg += " (" + failed + " failed)";
            final String toast = msg;
            runOnUiThread(new Runnable() { @Override public void run() {
                Toast.makeText(MainActivity.this, toast, Toast.LENGTH_LONG).show();
                refreshClipList();
            } });
        } });
    }

    /** One file into Downloads/Unwritten. Throws on failure, and never
     *  orphans the IS_PENDING row: it would sit in Downloads invisible
     *  and unopenable. */
    private void exportToDownloads(ContentResolver cr, File f) throws Exception {
        Uri uri = null;
        try {
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.Downloads.DISPLAY_NAME, f.getName());
            cv.put(MediaStore.Downloads.MIME_TYPE, mimeFor(f.getName()));
            cv.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Unwritten");
            cv.put(MediaStore.Downloads.IS_PENDING, 1);
            uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new Exception("MediaStore insert failed for " + f.getName());
            FileInputStream in = new FileInputStream(f);
            OutputStream out = null;
            try {
                out = cr.openOutputStream(uri);
                if (out == null) throw new Exception("Could not open output for " + f.getName());
                copyStream(in, out);
            } finally {
                try { in.close(); } catch (Throwable ignored) {}
                if (out != null) try { out.close(); } catch (Throwable ignored) {}
            }
            ContentValues done = new ContentValues(); done.put(MediaStore.Downloads.IS_PENDING, 0);
            cr.update(uri, done, null, null);
        } catch (Exception e) {
            if (uri != null) { try { cr.delete(uri, null, null); } catch (Throwable ignored) {} }
            throw e;
        }
    }

    // ---------- Cloud streaming (optional) ----------

    private SharedPreferences cloudPrefs() { return getSharedPreferences(CLOUD_PREFS, MODE_PRIVATE); }
    private void migrateCloudPrefs() {
        // One-time move from the pre-rename store: only the Cloud
        // switch is adopted (connection values load fresh from the
        // stamped build on every load — user-ordered Nov 4). Then the
        // legacy store is cleared.
        try {
            SharedPreferences legacy = getSharedPreferences("unwritten_bunny", MODE_PRIVATE); // legacy store name
            if (legacy.getAll().isEmpty()) return;
            if (legacy.contains("enabled"))
                cloudPrefs().edit().putBoolean("enabled", legacy.getBoolean("enabled", true)).apply();
            legacy.edit().clear().apply();
        } catch (Throwable ignored) { }
    }

    // Connection values load fresh from the stamped build on every
    // load — nothing persists them. Only the Cloud on/off switch
    // persists, under "enabled".
    private String cloudEffSignerUrl() {
        return CLOUD_SIGNER_DEFAULT;
    }
    private String cloudEffSignerToken() {
        return CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT;
    }
    private CloudUploader cloudUploader() {
        CloudUploader up = new CloudUploader(cloudEffSignerUrl(), cloudEffSignerToken());
        return up.configured() ? up : null;
    }
    private boolean cloudEnabledCfg() {
        return cloudPrefs().getBoolean("enabled", true) && cloudUploader() != null;
    }

    // True when an upload could possibly succeed: the build carries
    // a stamped signer token. Without this, token-less builds fire
    // doomed uploads that can only 401.
    private boolean canUpload() {
        return HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken());
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
        // Sessions only: never a live take or an upload mid-copy.
        for (File f : clipFiles()) maybeCloudUpload(f);
    }

    // Cloud credentials, like the iOS and web settings panels. Fields
    // prefill with STORED overrides only — never effective values, so
    // opening this can never persist the build defaults as overrides
    // and shadow a later stamp rotation. Hints name the defaults.
    // Read-only debug info: connection values load fresh from the
    // stamped build on every load and can't be changed here, so a
    // stale saved URL can never break uploads again.
    private void showCloudSettings() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(4);
        form.setPadding(pad, pad, pad, pad);
        form.addView(label("Build values, shown for debugging — they load fresh from this build and can't be changed here.", 14, DIM));
        form.addView(label("Signer URL", 14, DIM));
        TextView urlTv = new TextView(this);
        urlTv.setText(cloudEffSignerUrl());
        urlTv.setTextSize(16);
        urlTv.setTextColor(TEXT);
        form.addView(urlTv);
        form.addView(label("Signer token", 14, DIM));
        TextView tokTv = new TextView(this);
        tokTv.setText(cloudEffSignerToken().isEmpty()
                ? "missing — rebuild the app to stamp one"
                : "stamped into this build ✓");
        tokTv.setTextSize(16);
        tokTv.setTextColor(TEXT);
        form.addView(tokTv);
        new AlertDialog.Builder(this)
                .setTitle("Cloud settings")
                .setView(form)
                .setPositiveButton("Done", null)
                .show();
    }

    private void applyCloudDependentVisibility() {
        boolean on = cloudEnabledCfg();
        if (exportBtn != null) exportBtn.setVisibility(on ? View.GONE : View.VISIBLE);
        refreshClipList();
        loadHub();
    }

    private void paintCloudToggle() {
        if (cloudToggleButton == null) return;
        // The Cloud glyph sits on a sage wash when on, sunken when off.
        if (cloudGlyph != null) {
            boolean on = cloudEnabledCfg();
            cloudGlyph.setBackground(rounded(on ? SAGE_SOFT : PRESSED, 14));
            android.graphics.drawable.Drawable g = cloudGlyph.getDrawable();
            if (g instanceof Glyphs) ((Glyphs) g).setColor(on ? SAGE : DIM);
        }
        // Set the switch without firing its listener (no echo toggle).
        cloudToggleButton.setOnCheckedChangeListener(null);
        cloudToggleButton.setChecked(cloudEnabledCfg());
        cloudToggleButton.setOnCheckedChangeListener(cloudSwitchListener);
        applyCloudDependentVisibility();
    }

    private void playInViewfinder(String name) {
        File f = new File(clipsDir, name);
        if (!f.exists()) { Toast.makeText(this, "File missing.", Toast.LENGTH_SHORT).show(); return; }
        // Sessions live on home; playback happens on the record screen.
        showScreen("record");
        // A row tapped below the fold used to play in an off-screen
        // viewfinder (the iOS playback fix found the same bug):
        // scroll up so the video is visible.
        if (rootScroll != null) rootScroll.post(new Runnable() { @Override public void run() { rootScroll.smoothScrollTo(0, 0); } });
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
        // Every screen steps back to home.
        if (!"home".equals(currentScreen)) { showScreen("home"); return; }
        super.onBackPressed();
    }

    private String cloudWatchUrl(String name) {
        JSONObject link = cloudLink(name);
        if (link == null) return null;
        String vid = link.optString("videoId", "");
        if (vid.isEmpty()) return null;
        String lib = link.optString("libraryId", "");
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
        if (!HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) return "This build carries no signer token — rebuild it to stamp one.";
        if (hubNotice != null && !hubNotice.isEmpty()) return hubNotice;
        return "No published sessions yet — run the pipeline's publish step.";
    }

    private void loadHub() {
        if (!hubAvailable()) {
            hubRows = new JSONArray();
            hubDetail = null;
            hubNotice = "";
            ignoredById = new JSONObject();
            ignoredByTitle = new JSONObject();
            runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); refreshClipList(); } });
            return;
        }
        loadIgnored();
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                HubClient hub = new HubClient(cloudEffSignerUrl(), cloudEffSignerToken());
                hubRows = hub.list();
                hubNotice = "";
                if (hubDetail != null) {
                    boolean stillThere = false;
                    // A tied session lists under its first part: keep the
                    // detail while any of its parts is listed.
                    Set<String> cur = new HashSet<String>();
                    for (JSONObject p : hubParts(hubDetail)) cur.add(p.optString("videoId", ""));
                    for (int i = 0; i < hubRows.length(); i++) {
                        if (cur.contains(hubRows.optJSONObject(i).optString("videoId", ""))) { stillThere = true; break; }
                    }
                    if (!stillThere) hubDetail = null;
                }
                runOnUiThread(new Runnable() { @Override public void run() { refreshHubRows(); } });
            } catch (final Exception e) {
                android.util.Log.e("UnwrittenHub", "hub list failed", e);
                final String msg = String.valueOf(e.getMessage());
                if (msg.contains("(401)") || msg.contains("(403)")) {
                    hubNotice = "Signer refused the token — rebuild the app to stamp a fresh one.";
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

    // Ignored badges: the pipeline operator's set-asides, fetched
    // alongside the hub. Matching takes get an "ignored" badge in
    // the Record list; the hub never shows these at all. Match rule,
    // same as the web and iOS recorders: the take's cloud-link
    // videoId, else its filename against the marker title (upload
    // titles are filenames). A failed fetch just leaves badges off.
    private void loadIgnored() {
        if (!hubAvailable()) return;
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                JSONArray rows = new HubClient(cloudEffSignerUrl(), cloudEffSignerToken()).ignored();
                JSONObject byId = new JSONObject();
                JSONObject byTitle = new JSONObject();
                for (int i = 0; i < rows.length(); i++) {
                    JSONObject r = rows.optJSONObject(i);
                    if (r == null) continue;
                    String vid = r.optString("videoId", "");
                    String title = r.optString("title", "");
                    String reason = r.optString("reason", "");
                    if (!vid.isEmpty()) byId.put(vid, reason);
                    if (!title.isEmpty()) byTitle.put(title, reason);
                }
                ignoredById = byId;
                ignoredByTitle = byTitle;
                runOnUiThread(new Runnable() { @Override public void run() { refreshClipList(); } });
            } catch (final Exception e) {
                android.util.Log.e("UnwrittenHub", "ignored list failed", e);
            }
        } });
    }

    // The ignore reason for a take, or null when not ignored.
    private String ignoredReasonFor(String name) {
        JSONObject link = cloudLink(name);
        String vid = link == null ? "" : link.optString("videoId", "");
        if (!vid.isEmpty() && ignoredById.has(vid)) return ignoredById.optString(vid, "");
        if (ignoredByTitle.has(name)) return ignoredByTitle.optString(name, "");
        return null;
    }

    private void refreshHubRows() {
        if (hubContainer == null) return;
        hubContainer.removeAllViews();
        if (hubDetail != null) hubContainer.addView(hubDetailView(hubDetail));
        if (hubRows == null || hubRows.length() == 0) {
            // The reason (or simply empty), with a glyph in an ember wash.
            LinearLayout empty = new LinearLayout(this);
            empty.setOrientation(LinearLayout.VERTICAL);
            empty.setGravity(Gravity.CENTER_HORIZONTAL);
            empty.setPadding(dp(20), dp(24), dp(20), dp(24));
            empty.addView(glyphBadge(Glyphs.BOOK, EMBER_INK, EMBER_SOFT, 56, 28));
            TextView et = label(hubStatusText(), 15, DIM);
            et.setGravity(Gravity.CENTER);
            et.setPadding(dp(4), dp(10), dp(4), 0);
            empty.addView(et);
            hubContainer.addView(empty);
            return;
        }
        for (int i = 0; i < hubRows.length(); i++) {
            final JSONObject row = hubRows.optJSONObject(i);
            if (row == null) continue;
            if (i > 0 || hubDetail != null) {
                View divider = new View(this);
                divider.setBackgroundColor(LINE);
                LinearLayout.LayoutParams dl = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1);
                dl.setMargins(dp(82), 0, 0, 0);
                hubContainer.addView(divider, dl);
            }
            LinearLayout r = new LinearLayout(this);
            r.setOrientation(LinearLayout.HORIZONTAL);
            r.setGravity(Gravity.CENTER_VERTICAL);
            r.setBackground(rowRipple());
            r.setMinimumHeight(dp(80));
            r.setPadding(dp(12), dp(10), dp(8), dp(10));
            String title = row.optString("title", row.optString("videoId", ""));
            String date = row.optString("lessonDate", "");
            String dur = formatDuration(row.optInt("durationSeconds", 0));
            // A cover tile: the lesson's initial on its warm wash.
            r.addView(cover(title, 56, 24, 14));
            LinearLayout mid = new LinearLayout(this);
            mid.setOrientation(LinearLayout.VERTICAL);
            mid.setPadding(dp(14), 0, dp(8), 0);
            TextView t = new TextView(this);
            t.setText(title); t.setTextSize(17); t.setTextColor(TEXT); t.setTypeface(MEDIUM);
            t.setSingleLine(true);
            t.setEllipsize(android.text.TextUtils.TruncateAt.END);
            mid.addView(t);
            String hubSub = !date.isEmpty() && !dur.isEmpty() ? date + " \u2022 " + dur : (!date.isEmpty() ? date : dur);
            // A tied session lists once: its parts and any still processing.
            int partCount = row.optInt("partCount", 1), pendingParts = row.optInt("pendingParts", 0);
            if (partCount > 1) hubSub += (hubSub.isEmpty() ? "" : " \u2022 ") + partCount + " parts";
            if (pendingParts > 0) hubSub += (hubSub.isEmpty() ? "" : " \u2022 ") + pendingParts + " processing";
            if (!hubSub.isEmpty()) {
                TextView d = new TextView(this);
                d.setText(hubSub); d.setTextSize(14); d.setTextColor(DIM);
                d.setPadding(0, dp(3), 0, 0);
                mid.addView(d);
            }
            r.addView(mid, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            android.widget.ImageView go = new android.widget.ImageView(this);
            go.setImageDrawable(new Glyphs(Glyphs.CHEVRON, DIM, dp(18)));
            go.setScaleType(android.widget.ImageView.ScaleType.CENTER);
            r.addView(go, new LinearLayout.LayoutParams(dp(32), dp(48)));
            r.setContentDescription(title + (hubSub.isEmpty() ? "" : ", " + hubSub) + ". Opens the lesson.");
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

    /** A 48dp-tall ripple button that shares a row (weight 1). */
    private Button smallHubButton(String text) {
        Button b = styledButton(text, PRESSED, TEXT);
        b.setTextSize(15);
        b.setMinHeight(dp(48)); b.setMinimumHeight(dp(48));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(48), 1f);
        lp.setMargins(dp(3), dp(6), dp(3), dp(6));
        b.setLayoutParams(lp);
        return b;
    }

    /** Write-ups are Markdown: inline bold and italic render, line
     *  breaks stay — the same inline-only reading as iOS and the web.
     *  Step screengrabs (![Step N](stills/...)) live in the page, not the
     *  hub: the hub has no still URLs, so they strip out here. */
    private CharSequence inlineMarkdown(String md) {
        String noImg = md.replaceAll("!\\[Step\\s+\\d+\\]\\([^)]+\\)", "");
        String html = android.text.TextUtils.htmlEncode(noImg)
            .replaceAll("\\*\\*([^*\\n]+)\\*\\*", "<b>$1</b>")
            .replaceAll("(^|[^*])\\*([^*\\n]+)\\*", "$1<i>$2</i>")
            .replace("\n", "<br>");
        return android.text.Html.fromHtml(html, android.text.Html.FROM_HTML_MODE_LEGACY);
    }

    /** A lesson, listing style: a warm cover banner with its initial,
     *  the title and date, an ember Play pill with round Share and
     *  Delete, the write-up, corrections as quote cards, and chapters
     *  as a list of time chips. */
    private View hubDetailView(final JSONObject obj) {
        String title = obj.optString("title", obj.optString("videoId", ""));
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(PANEL, 20));
        try { card.setElevation(dp(night ? 0 : 4)); } catch (Throwable ignored) {}
        card.setClipToOutline(true);
        LinearLayout.LayoutParams cardLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        card.setLayoutParams(cardLp);
        // The cover banner, with Close in its corner.
        android.widget.FrameLayout banner = new android.widget.FrameLayout(this);
        int w = washIndex(title);
        banner.setBackgroundColor(WASH[w]);
        TextView big = new TextView(this);
        big.setText(initialOf(title)); big.setTextSize(64); big.setTypeface(BOLD);
        big.setTextColor(WASH_INK[w]); big.setGravity(Gravity.CENTER);
        big.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        banner.addView(big, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(150)));
        android.widget.ImageButton close = iconButton(Glyphs.CLOSE, TEXT, PANEL, "Close", new View.OnClickListener() { @Override public void onClick(View v) {
            hubDetail = null;
            if (isViewfinderPlaying) stopLocalPlayback();
            refreshHubRows();
        } });
        android.widget.FrameLayout.LayoutParams closeLp = new android.widget.FrameLayout.LayoutParams(dp(48), dp(48));
        closeLp.gravity = Gravity.TOP | Gravity.END;
        closeLp.setMargins(0, dp(10), dp(10), 0);
        close.setElevation(dp(2));
        banner.addView(close, closeLp);
        card.addView(banner);

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(18), dp(16), dp(18), dp(18));
        card.addView(body);
        TextView t = label(title, 24, TEXT);
        t.setTypeface(BOLD);
        t.setPadding(0, 0, 0, 0);
        body.addView(t);
        String date = obj.optString("lessonDate", "");
        String detailDur = formatDuration(obj.optInt("durationSeconds", 0));
        String detailSub = !date.isEmpty() && !detailDur.isEmpty() ? date + " \u2022 " + detailDur : (!date.isEmpty() ? date : detailDur);
        if (!detailSub.isEmpty()) {
            TextView d = label(detailSub, 15, DIM);
            d.setPadding(0, dp(4), 0, 0);
            body.addView(d);
        }
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        actions.setPadding(0, dp(14), 0, dp(4));
        Button play = primaryButton("▶  Play", BRIGHT);
        play.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { playHubRemote(obj, 0); } });
        actions.addView(play, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        android.widget.ImageButton share = iconButton(Glyphs.SHARE, TEXT, PRESSED, "Share session link",
                new View.OnClickListener() { @Override public void onClick(View v) { shareHubSession(obj); } });
        ((LinearLayout.LayoutParams) share.getLayoutParams()).setMargins(dp(10), 0, 0, 0);
        actions.addView(share);
        android.widget.ImageButton del = iconButton(Glyphs.TRASH, RED, PRESSED, "Delete from the hub and the cloud",
                new View.OnClickListener() { @Override public void onClick(View v) {
            if (hubParts(obj).size() > 1) { confirmDeleteHubParts(obj); return; }
            confirmDeleteHub(obj.optString("title", obj.optString("videoId", "")), obj.optString("videoId", ""));
        } });
        ((LinearLayout.LayoutParams) del.getLayoutParams()).setMargins(dp(8), 0, 0, 0);
        actions.addView(del);
        body.addView(actions);
        // Parts: each plays on its own or unties; Play above runs them
        // all in order.
        final List<JSONObject> parts = hubParts(obj);
        final boolean multi = parts.size() > 1;
        int pending = obj.optInt("pendingParts", 0);
        if (multi || pending > 0) {
            body.addView(detailHeader("Parts"));
            for (int i = 0; i < parts.size(); i++) {
                final JSONObject p = parts.get(i);
                final int idx = i;
                LinearLayout pr = new LinearLayout(this);
                pr.setOrientation(LinearLayout.HORIZONTAL);
                pr.setGravity(Gravity.CENTER_VERTICAL);
                pr.setMinimumHeight(dp(48));
                TextView pc = chip("▶ Part " + (i + 1), EMBER_SOFT, EMBER_INK);
                pc.setClickable(true);
                pc.setContentDescription("Play part " + (i + 1));
                pc.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { playHubRemote(obj, idx); } });
                ((LinearLayout.LayoutParams) pc.getLayoutParams()).setMargins(0, 0, dp(10), 0);
                pr.addView(pc);
                String pd = formatDuration(p.optInt("durationSeconds", 0));
                final String ptitle = p.optString("title", p.optString("videoId", ""));
                pr.addView(label(ptitle + (pd.isEmpty() ? "" : " \u2022 " + pd), 15, TEXT),
                        new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
                if (multi) {
                    Button un = smallHubButton("Untie");
                    un.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(44)));
                    un.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) {
                        untieHubPart(obj, p.optString("videoId", ""), ptitle);
                    } });
                    pr.addView(un);
                }
                body.addView(pr);
            }
            if (pending > 0) {
                TextView pn = label(pending + " more part" + (pending > 1 ? "s" : "")
                        + " still processing — they appear here once the pipeline has written them up.", 14, DIM);
                pn.setPadding(0, dp(6), 0, 0);
                body.addView(pn);
            }
        }
        // Continue this session: whatever is recorded, uploaded or
        // fetched next becomes its next part.
        body.addView(detailHeader("Add a part"));
        LinearLayout add = new LinearLayout(this);
        add.setOrientation(LinearLayout.HORIZONTAL);
        String[][] ways = { {"Record", "record"}, {"Upload", "upload"} };
        for (final String[] way : ways) {
            Button b = smallHubButton(way[0]);
            b.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { startJoin(obj, way[1]); } });
            add.addView(b);
        }
        body.addView(add);
        Button tie = smallHubButton("Tie a session to this one");
        tie.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)));
        tie.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showTiePicker(obj); } });
        body.addView(tie);
        String writeup = obj.optString("writeupMd", "");
        if (!writeup.isEmpty()) {
            View rule = new View(this);
            rule.setBackgroundColor(LINE);
            LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1);
            rl.setMargins(0, dp(12), 0, dp(12));
            body.addView(rule, rl);
            TextView wu = label("", 16, TEXT);
            wu.setText(inlineMarkdown(writeup));
            wu.setLineSpacing(0, 1.3f);
            wu.setTextIsSelectable(true);
            wu.setPadding(0, 0, 0, 0);
            body.addView(wu);
        }
        JSONArray corrections = obj.optJSONArray("corrections");
        if (corrections != null && corrections.length() > 0) {
            body.addView(detailHeader("Corrections"));
            for (int i = 0; i < corrections.length(); i++) {
                JSONObject c = corrections.optJSONObject(i);
                if (c == null) continue;
                // A quote card: time chip, the mentor's words, what they corrected.
                LinearLayout q = new LinearLayout(this);
                q.setOrientation(LinearLayout.VERTICAL);
                q.setBackground(rounded(BG, 18));
                q.setPadding(dp(14), dp(12), dp(14), dp(12));
                LinearLayout.LayoutParams ql = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                ql.setMargins(0, 0, 0, dp(10));
                TextView tc = chip((multi && c.optInt("part", 0) > 0 ? "Part " + c.optInt("part", 0) + " \u00b7 " : "")
                        + c.optString("start", ""), EMBER_SOFT, EMBER_INK);
                q.addView(tc);
                TextView quote = label("\u201C" + c.optString("quote", "") + "\u201D", 16, TEXT);
                quote.setPadding(0, dp(8), 0, 0);
                q.addView(quote);
                if (!c.optString("correcting", "").isEmpty()) {
                    TextView fix = label("Correcting: " + c.optString("correcting", ""), 14, DIM);
                    fix.setPadding(0, dp(4), 0, 0);
                    q.addView(fix);
                }
                body.addView(q, ql);
            }
        }
        JSONArray chapters = obj.optJSONArray("chapters");
        if (chapters != null && chapters.length() > 0) {
            body.addView(detailHeader("Chapters"));
            for (int i = 0; i < chapters.length(); i++) {
                JSONObject c = chapters.optJSONObject(i);
                if (c == null) continue;
                LinearLayout ch = new LinearLayout(this);
                ch.setOrientation(LinearLayout.HORIZONTAL);
                ch.setGravity(Gravity.CENTER_VERTICAL);
                ch.setMinimumHeight(dp(44));
                TextView tc = chip((multi && c.optInt("part", 0) > 0 ? "Part " + c.optInt("part", 0) + " \u00b7 " : "")
                        + c.optString("start", ""), EMBER_SOFT, EMBER_INK);
                ((LinearLayout.LayoutParams) tc.getLayoutParams()).setMargins(0, 0, dp(12), 0);
                ch.addView(tc);
                ch.addView(label(c.optString("label", ""), 15, TEXT));
                body.addView(ch);
            }
        }
        return card;
    }

    private TextView detailHeader(String text) {
        TextView h = label(text, 19, TEXT);
        h.setTypeface(BOLD);
        h.setPadding(0, dp(20), 0, dp(10));
        return h;
    }

    private String hubEmbedUrl(JSONObject obj) {
        if (obj == null) return null;
        String vid = obj.optString("videoId", "");
        if (vid == null || vid.isEmpty()) return null;
        String lib = obj.optString("libraryId", "");
        if (lib == null || lib.isEmpty()) return null;
        return "https://player.mediadelivery.net/embed/" + lib + "/" + vid;
    }

    private void shareHubSession(JSONObject obj) {
        List<JSONObject> parts = hubParts(obj);
        if (parts.size() > 1) {
            // One link per part, in order.
            StringBuilder text = new StringBuilder();
            for (int i = 0; i < parts.size(); i++) {
                JSONObject p = parts.get(i);
                try { if (p.optString("libraryId", "").isEmpty()) p.put("libraryId", obj.optString("libraryId", "")); } catch (Throwable ignored) {}
                String u = hubEmbedUrl(p);
                if (u != null) text.append("Part ").append(i + 1).append(": ").append(u).append("\n");
            }
            Intent share = new Intent(Intent.ACTION_SEND);
            share.setType("text/plain");
            share.putExtra(Intent.EXTRA_SUBJECT, obj.optString("title", "hub session"));
            share.putExtra(Intent.EXTRA_TEXT, text.toString().trim());
            try { startActivity(Intent.createChooser(share, "Share session links")); }
            catch (Throwable e) { Toast.makeText(this, "No app can share links.", Toast.LENGTH_LONG).show(); }
            return;
        }
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

    /** Play runs every part in order: each one's end starts the next
     *  (an untied session is one part and plays as before). */
    private void playHubRemote(final JSONObject whole, final int from) {
        final List<JSONObject> parts = hubParts(whole);
        if (from < 0 || from >= parts.size()) return;
        final JSONObject obj = parts.get(from);
        if (obj.optString("libraryId", "").isEmpty()) {
            try { obj.put("libraryId", whole.optString("libraryId", "")); } catch (Throwable ignored) {}
        }
        final boolean hasNext = from + 1 < parts.size();
        final String mp4 = obj.optString("mp4Url", "");
        final String hls = obj.optString("hlsUrl", "");
        final String src = (mp4 != null && !mp4.isEmpty()) ? mp4
                : ((hls != null && !hls.isEmpty()) ? hls : "");
        final String embed = hubEmbedUrl(obj);
        if (src.isEmpty() && (embed == null || embed.isEmpty())) {
            Toast.makeText(this, "No playable stream on this hub session yet.", Toast.LENGTH_LONG).show();
            return;
        }
        if (!src.isEmpty()) {
            // The hub's own player: watching a published lesson never
            // opens the camera (iOS hub screen, web home player). MP4
            // first, HLS next, the Cloud embed page last.
            try {
                final android.widget.VideoView hubPlayer = new android.widget.VideoView(this);
                hubPlayer.setMinimumHeight(dp(220));
                hubPlayer.setMinimumWidth(dp(300));
                final AlertDialog dlg = new AlertDialog.Builder(this)
                        .setTitle(parts.size() > 1
                                ? "Part " + (from + 1) + " of " + parts.size() + " · " + obj.optString("title", "Hub session")
                                : obj.optString("title", "Hub session"))
                        .setView(hubPlayer)
                        .setPositiveButton("Close", null)
                        .create();
                hubPlayer.setOnPreparedListener(new android.media.MediaPlayer.OnPreparedListener() {
                    @Override public void onPrepared(android.media.MediaPlayer mp) { hubPlayer.start(); }
                });
                hubPlayer.setOnCompletionListener(new android.media.MediaPlayer.OnCompletionListener() {
                    @Override public void onCompletion(android.media.MediaPlayer mp) {
                        if (!hasNext) return;
                        try { dlg.dismiss(); } catch (Throwable ignored) {}
                        playHubRemote(whole, from + 1);
                    }
                });
                hubPlayer.setOnErrorListener(new android.media.MediaPlayer.OnErrorListener() {
                    @Override public boolean onError(android.media.MediaPlayer mp, int what, int extra) {
                        try { dlg.dismiss(); } catch (Throwable ignored) {}
                        Toast.makeText(MainActivity.this, "This device can't play that stream here — opening the Cloud player.", Toast.LENGTH_LONG).show();
                        openInBrowser(embed);
                        return true;
                    }
                });
                // The Cloud CDN's hotlink protection 403s streams
                // without the player page as Referer (the iOS playback
                // fix found this): send the embed URL with the request.
                if (embed != null && !embed.isEmpty()) {
                    java.util.Map<String, String> headers = new java.util.HashMap<String, String>();
                    headers.put("Referer", embed);
                    hubPlayer.setVideoURI(Uri.parse(src), headers);
                } else {
                    hubPlayer.setVideoURI(Uri.parse(src));
                }
                dlg.show();
                return;
            } catch (Throwable e) {
                Toast.makeText(this, "Playback failed (" + e.getMessage() + ") — opening the Cloud player.", Toast.LENGTH_LONG).show();
            }
        }
        openInBrowser(embed);
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
                if (up == null) throw new IOException("This build carries no signer token.");
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

    // ---------- session parts: continue a session, tie sessions ----------

    /** The capture screens' note: which session these takes join, with
     *  the way out on the note itself. One per screen, painted together. */
    private LinearLayout joinBannerView() {
        LinearLayout b = new LinearLayout(this);
        b.setOrientation(LinearLayout.VERTICAL);
        b.setBackground(rounded(SAGE_SOFT, 18));
        b.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(8), 0, dp(12));
        b.setLayoutParams(lp);
        TextView t = label("", 15, TEXT);
        t.setTag("joinText");
        b.addView(t);
        Button own = smallHubButton("Make it its own session");
        own.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(44)));
        own.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) {
            clearJoinTarget();
            paintJoinBanners();
        } });
        b.addView(own);
        b.setVisibility(View.GONE);
        joinBanners.add(b);
        return b;
    }

    private void paintJoinBanners() {
        for (LinearLayout b : joinBanners) {
            if (joinToVideoId == null) { b.setVisibility(View.GONE); continue; }
            TextView t = (TextView) b.findViewWithTag("joinText");
            if (t != null) t.setText("Adds a part to " + joinToTitle
                    + " — it joins that session in the hub once uploaded.");
            b.setVisibility(View.VISIBLE);
        }
    }

    private void clearJoinTarget() { joinToVideoId = null; joinToTitle = null; }

    /** "Add a part" on a hub session: Record / Upload / Link continue it. */
    private void startJoin(JSONObject session, String screen) {
        joinToVideoId = session.optString("videoId", "");
        joinToTitle = session.optString("title", joinToVideoId);
        if (joinToVideoId.isEmpty()) clearJoinTarget();
        showScreen(screen);
    }

    /** A saved take or upload remembers the session it continues. */
    private void markJoin(String name) {
        if (joinToVideoId == null || name == null) return;
        synchronized (cloudLinkLock) {
            try {
                JSONObject links = cloudLinks();
                JSONObject cur = links.optJSONObject(name);
                if (cur == null) cur = new JSONObject();
                cur.put("joinTo", joinToVideoId);
                cur.put("joinTitle", joinToTitle);
                links.put(name, cur);
                cloudPrefs().edit().putString("links", links.toString()).apply();
            } catch (Throwable ignored) { }
        }
    }

    private final Set<String> tieInFlight = new HashSet<String>();

    /** Ties a take onto its session once its upload has a video id;
     *  three tries, then a status line — Record retries on its next
     *  resume, so a tie is never silently dropped. */
    private void tieCloudPart(final String name) {
        JSONObject link = cloudLink(name);
        if (link == null) return;
        final String join = link.optString("joinTo", ""), vid = link.optString("videoId", "");
        final String jt = link.optString("joinTitle", "its session");
        if (join.isEmpty() || vid.isEmpty() || link.optBoolean("joined", false)) return;
        if (!HubClient.available(cloudEffSignerUrl(), cloudEffSignerToken())) {
            if (status != null) status.setText("☁ Couldn't tie this take to " + jt
                    + " — this build carries no signer token. Rebuild to stamp one; it will retry on the next upload.");
            return;
        }
        synchronized (tieInFlight) { if (!tieInFlight.add(name)) return; }
        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
        new Thread(new Runnable() { @Override public void run() {
            try {
                Exception last = null;
                for (int attempt = 1; attempt <= 3; attempt++) {
                    try {
                        new HubClient(surl, stok).tie(java.util.Arrays.asList(join, vid));
                        synchronized (cloudLinkLock) {
                            JSONObject links = cloudLinks();
                            JSONObject cur = links.optJSONObject(name);
                            if (cur != null) {
                                cur.put("joined", true);
                                cloudPrefs().edit().putString("links", links.toString()).apply();
                            }
                        }
                        runOnUiThread(new Runnable() { @Override public void run() { refreshClipList(); } });
                        return;
                    } catch (Exception e) {
                        last = e;
                        try { Thread.sleep(2000L * attempt); } catch (InterruptedException ie) { return; }
                    }
                }
                final String why = last == null ? "" : last.getMessage();
                runOnUiThread(new Runnable() { @Override public void run() {
                    if (status != null) status.setText("☁ Couldn't tie this take to " + jt + " (" + why
                            + ") — it will retry when you next open the app. The take itself is safe.");
                } });
            } finally {
                synchronized (tieInFlight) { tieInFlight.remove(name); }
            }
        } }).start();
    }

    /** The parts of a hub session in order (itself when untied, or
     *  when an older signer sends no parts). */
    private List<JSONObject> hubParts(JSONObject obj) {
        List<JSONObject> out = new ArrayList<JSONObject>();
        JSONArray ps = obj == null ? null : obj.optJSONArray("parts");
        if (ps != null) for (int i = 0; i < ps.length(); i++) {
            JSONObject p = ps.optJSONObject(i);
            if (p != null) out.add(p);
        }
        if (out.isEmpty() && obj != null) out.add(obj);
        return out;
    }

    /** Tie: pick another hub session; it (with its own parts) joins the
     *  end of this one. */
    private void showTiePicker(final JSONObject obj) {
        final List<JSONObject> others = new ArrayList<JSONObject>();
        Set<String> mine = new HashSet<String>();
        for (JSONObject p : hubParts(obj)) mine.add(p.optString("videoId", ""));
        for (int i = 0; hubRows != null && i < hubRows.length(); i++) {
            JSONObject r = hubRows.optJSONObject(i);
            if (r != null && !mine.contains(r.optString("videoId", ""))) others.add(r);
        }
        if (others.isEmpty()) { Toast.makeText(this, "No other hub sessions to tie on.", Toast.LENGTH_LONG).show(); return; }
        String[] names = new String[others.size()];
        for (int i = 0; i < names.length; i++) {
            JSONObject r = others.get(i);
            int n = r.optInt("partCount", 1);
            names[i] = r.optString("title", r.optString("videoId", "")) + (n > 1 ? "  (" + n + " parts)" : "");
        }
        new AlertDialog.Builder(this)
                .setTitle("Which session comes next?")
                .setItems(names, new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        tieHubSessions(obj, others.get(which).optString("videoId", ""));
                    }
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void tieHubSessions(final JSONObject obj, final String otherId) {
        final String first = obj.optString("videoId", "");
        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
        cloudExec.execute(new Runnable() { @Override public void run() {
            try {
                new HubClient(surl, stok).tie(java.util.Arrays.asList(first, otherId));
            } catch (final Exception e) {
                runOnUiThread(new Runnable() { @Override public void run() {
                    Toast.makeText(MainActivity.this, "Couldn't tie those sessions (" + e.getMessage() + ") — nothing changed.", Toast.LENGTH_LONG).show();
                } });
                return;
            }
            runOnUiThread(new Runnable() { @Override public void run() {
                Toast.makeText(MainActivity.this, "Tied — they're one session now.", Toast.LENGTH_SHORT).show();
                openHubSession(first);
                loadHub();
            } });
        } });
    }

    private void untieHubPart(final JSONObject obj, final String videoId, String title) {
        new AlertDialog.Builder(this)
                .setTitle("Untie this part?")
                .setMessage("'" + title + "' becomes its own session again. Nothing is deleted.")
                .setPositiveButton("Untie", new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        String stay = videoId;
                        for (JSONObject p : hubParts(obj)) {
                            if (!videoId.equals(p.optString("videoId", ""))) { stay = p.optString("videoId", ""); break; }
                        }
                        final String reopen = stay;
                        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
                        cloudExec.execute(new Runnable() { @Override public void run() {
                            try {
                                new HubClient(surl, stok).untie(videoId);
                            } catch (final Exception e) {
                                runOnUiThread(new Runnable() { @Override public void run() {
                                    Toast.makeText(MainActivity.this, "Couldn't untie that part (" + e.getMessage() + ") — nothing changed.", Toast.LENGTH_LONG).show();
                                } });
                                return;
                            }
                            runOnUiThread(new Runnable() { @Override public void run() {
                                Toast.makeText(MainActivity.this, "Part untied — it's its own session again.", Toast.LENGTH_SHORT).show();
                                openHubSession(reopen);
                                loadHub();
                            } });
                        } });
                    }
                })
                .setNegativeButton("Keep", null)
                .show();
    }

    /** One overall session: deleting it deletes every part, each named
     *  first. A failure stops the run and says how far it got. */
    private void confirmDeleteHubParts(final JSONObject obj) {
        final List<JSONObject> parts = hubParts(obj);
        StringBuilder names = new StringBuilder();
        for (int i = 0; i < parts.size(); i++)
            names.append(i + 1).append(". ").append(parts.get(i).optString("title", parts.get(i).optString("videoId", ""))).append("\n");
        new AlertDialog.Builder(this)
                .setTitle("Delete all " + parts.size() + " parts?")
                .setMessage(names + "\nEach is deleted from the cloud and the hub. To keep one, untie it first.")
                .setPositiveButton("Delete all", new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        final String surl = cloudEffSignerUrl(), stok = cloudEffSignerToken();
                        hubDetail = null;
                        cloudExec.execute(new Runnable() { @Override public void run() {
                            int done = 0;
                            String err = null;
                            for (JSONObject p : parts) {
                                String vid = p.optString("videoId", "");
                                try {
                                    new HubClient(surl, stok).delete(vid);
                                } catch (Exception e) { err = e.getMessage(); break; }
                                try { CloudUploader up = cloudUploader(); if (up != null) up.deleteVideo(vid); }
                                catch (Exception e) { err = "hub entry removed, but the cloud copy remains: " + e.getMessage(); done++; break; }
                                done++;
                            }
                            final String msg = err == null ? "All " + done + " parts deleted from the hub and the cloud."
                                    : "Stopped at part " + (done + 1) + " of " + parts.size() + " (" + err + "); the rest are untouched.";
                            runOnUiThread(new Runnable() { @Override public void run() {
                                if (status != null) status.setText("🗑 " + msg);
                                Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show();
                                loadHub();
                            } });
                        } });
                    }
                })
                .setNegativeButton("Keep", null)
                .show();
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
      synchronized (cloudLinkLock) {
        try {
            JSONObject links = cloudLinks();
            if (links.optJSONObject(name) != null) {
                links.remove(name);
                cloudPrefs().edit().putString("links", links.toString()).apply();
            }
        } catch (Throwable ignored) { }
      }
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
                        if (up == null) throw new IOException("This build carries no signer token.");
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
        durationCache.remove(name);
        thumbCache.remove(name);
        refreshClipList();
        Toast.makeText(this, doneToast, Toast.LENGTH_SHORT).show();
    }
    // Serializes the links blob's read-modify-write: upload callbacks
    // persist from the cloud pool while the UI thread writes too, and
    // a late progress write must never clobber a finished state back
    // to uploading.
    private final Object cloudLinkLock = new Object();

    private void setCloudLink(String name, String state, String videoId, String libraryId,
                              String uploadUrl, int progress) {
      synchronized (cloudLinkLock) {
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
            cloudFailed(name, null, "Cloud credentials missing — this build carries no signer token. Rebuild the app to stamp one.");
            Toast.makeText(this, "Signer token missing — rebuild the app to stamp one.", Toast.LENGTH_LONG).show();
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
                    if (up == null) { cloudFailed(name, savedVid, "This build carries no signer token."); return; }
                    up.upload(f, savedUrl, savedVid, new CloudUploader.Listener() {
                        @Override public void onSession(String videoId, String uploadUrl) {
                            setCloudLink(name, "uploading", videoId, null, uploadUrl, -1);
                            // The id exists now: a take that continues a session is tied on before its bytes finish.
                            tieCloudPart(name);
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
            if (auth) Toast.makeText(MainActivity.this, "Signer refused — rebuild the app to stamp a fresh one.", Toast.LENGTH_LONG).show();
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
            // A tie that failed earlier (offline, signer down) retries here.
            if (!link.optString("joinTo", "").isEmpty() && !link.optString("videoId", "").isEmpty()
                    && !link.optBoolean("joined", false)) tieCloudPart(name);
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
        // No camera yet (permissions not granted), no zoom row either.
        if (zoomRow != null && (engine == null || zoomSeek == null)) zoomRow.setVisibility(View.GONE);
        if (engine == null || zoomSeek == null) return;
        float max = engine.getMaxZoom();
        float cur = engine.getZoom();
        // No zoom range, no zoom row (iOS, web): never dead UI.
        if (zoomRow != null) zoomRow.setVisibility(max > 1.01f ? View.VISIBLE : View.GONE);
        syncZoomUi(cur, max);
        zoomSeek.setEnabled(max > 1.0f);
    }
}
