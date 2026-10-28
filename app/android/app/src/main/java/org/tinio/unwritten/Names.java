package org.tinio.unwritten;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** The filename contract (single source of truth): one lesson, one file.
 *  The pipeline takes the largest media file in the lesson folder as the
 *  lesson, so takes need no step names or session codes — only a
 *  timestamp that can never collide. */
public final class Names {

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

    public static String lessonName(String ext) {
        String e = ext == null ? "" : ext;
        if (e.startsWith(".")) {
            e = e.substring(1);
        }
        return "unwritten_lesson_" + stamp() + "." + e;
    }
}
