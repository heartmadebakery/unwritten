package org.tinio.unwritten;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Random;

public final class Names {

    public static final String[] CODE_WORDS = {
            "PLUM", "BREAD", "OVEN", "RIVER", "MANGO",
            "LODGE", "CORAL", "BASIL", "HARBOR", "MEADOW"
    };

    private Names() {
    }

    public static String stamp() {
        Date now = new Date();
        SimpleDateFormat fmt = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US);
        String base = fmt.format(now);
        long millis = now.getTime() % 1000L;
        if (millis < 0) {
            millis += 1000L;
        }
        String ms;
        if (millis < 10) {
            ms = "00" + millis;
        } else if (millis < 100) {
            ms = "0" + millis;
        } else {
            ms = String.valueOf(millis);
        }
        return base + "-" + ms;
    }

    public static String clipName(String step, String code, String ext) {
        String e = ext == null ? "" : ext;
        if (e.startsWith(".")) {
            e = e.substring(1);
        }
        return "unwritten_" + step + "_" + code + "_" + stamp() + "." + e;
    }

    public static String brollName(String code) {
        return "unwritten_broll_" + code + "_" + stamp() + ".mp4";
    }

    public static String dialogueName(String code) {
        return "unwritten_dialogue_" + code + "_" + stamp() + ".wav";
    }

    public static String photoName(String step, String code) {
        return "unwritten_" + step + "_" + code + "_" + stamp() + ".jpg";
    }

    public static String newCode(Random random) {
        Random r = random != null ? random : new Random();
        return CODE_WORDS[r.nextInt(CODE_WORDS.length)];
    }
}
