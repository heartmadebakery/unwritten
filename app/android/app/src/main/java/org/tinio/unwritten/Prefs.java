package org.tinio.unwritten;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.Random;

public final class Prefs {

    public static final String PREFS_NAME = "uw";

    public static final String DEFAULT_APPRENTICE_LINE =
            "From your card alone, I\u2019d cut straight down \u2014 blade at 90 degrees, "
                    + "medium pressure, right in the center, one smooth pass.";

    private static final String KEY_ROLE = "role";
    private static final String KEY_CODE = "code";
    private static final String KEY_APPRENTICE_LINE = "apprentice_line";
    private static final String KEY_STEP = "step";

    private static final String DEFAULT_STEP = "show";

    private final SharedPreferences prefs;

    public Prefs(Context context) {
        prefs = context.getApplicationContext()
                .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public static String defaultRole(boolean wideScreen) {
        return wideScreen ? "interviewer" : "recorder";
    }

    public String getRole(boolean wideScreen) {
        String role = prefs.getString(KEY_ROLE, null);
        if (role == null || role.length() == 0) {
            return defaultRole(wideScreen);
        }
        return role;
    }

    public void setRole(String role) {
        if (role == null) {
            prefs.edit().remove(KEY_ROLE).apply();
        } else {
            prefs.edit().putString(KEY_ROLE, role).apply();
        }
    }

    public String getCode() {
        String code = prefs.getString(KEY_CODE, null);
        if (code == null || code.length() == 0) {
            code = Names.newCode(new Random());
            prefs.edit().putString(KEY_CODE, code).apply();
        }
        return code;
    }

    public String rotateCode() {
        String current = prefs.getString(KEY_CODE, null);
        String next = Names.newCode(new Random());
        if (current != null && Names.CODE_WORDS.length > 1) {
            int guard = 0;
            while (next.equals(current) && guard < 16) {
                next = Names.newCode(new Random());
                guard++;
            }
        }
        prefs.edit().putString(KEY_CODE, next).apply();
        return next;
    }

    public String getApprenticeLine() {
        return prefs.getString(KEY_APPRENTICE_LINE, DEFAULT_APPRENTICE_LINE);
    }

    public void setApprenticeLine(String line) {
        if (line == null) {
            prefs.edit().remove(KEY_APPRENTICE_LINE).apply();
        } else {
            prefs.edit().putString(KEY_APPRENTICE_LINE, line).apply();
        }
    }

    public String getStep() {
        return prefs.getString(KEY_STEP, DEFAULT_STEP);
    }

    public void setStep(String step) {
        if (step == null) {
            prefs.edit().remove(KEY_STEP).apply();
        } else {
            prefs.edit().putString(KEY_STEP, step).apply();
        }
    }
}
