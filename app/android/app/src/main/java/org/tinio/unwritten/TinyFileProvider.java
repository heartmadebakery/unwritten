package org.tinio.unwritten;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Read-only content:// access to the recorder's clips, so external
 * players can open a session on Android 7+ (file:// intents arrive
 * unreadable there — no grant is possible for them). Zero
 * dependencies by design: this is the androidx FileProvider's job
 * in ~80 lines, serving exactly one directory.
 *
 * URIs look like content://org.tinio.unwritten.files/clips/&lt;name&gt;
 * and resolve only to files physically inside the clips dir —
 * anything else (.., absolute paths, missing files) is refused.
 */
public class TinyFileProvider extends ContentProvider {

    public static final String AUTHORITY = "org.tinio.unwritten.files";

    /** Content URI for a clip, or null when the file is not servable. */
    public static Uri uriForFile(Context ctx, File file) {
        try {
            File root = clipsRoot(ctx);
            if (root == null || file == null) return null;
            String rootPath = root.getCanonicalPath();
            String filePath = file.getCanonicalPath();
            if (!filePath.startsWith(rootPath + File.separator)) return null;
            if (!file.isFile()) return null;
            return new Uri.Builder().scheme("content").authority(AUTHORITY)
                    .appendPath("clips").appendPath(file.getName()).build();
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static File clipsRoot(Context ctx) {
        try {
            File ext = ctx.getExternalFilesDir(null);
            File base = ext != null ? ext : ctx.getFilesDir();
            return new File(base, "clips");
        } catch (Throwable ignored) {
            return null;
        }
    }

    private File resolve(Uri uri) throws FileNotFoundException {
        try {
            Context ctx = getContext();
            if (ctx == null) throw new FileNotFoundException("no context");
            if (uri == null || uri.getPathSegments().size() != 2
                    || !"clips".equals(uri.getPathSegments().get(0))) {
                throw new FileNotFoundException("bad uri: " + uri);
            }
            String name = uri.getLastPathSegment();
            if (name == null || name.isEmpty() || name.contains("..")
                    || name.contains("/") || name.contains(File.separator)) {
                throw new FileNotFoundException("bad name");
            }
            File root = clipsRoot(ctx);
            if (root == null) throw new FileNotFoundException("no clips dir");
            File file = new File(root, name);
            String rootPath = root.getCanonicalPath();
            String filePath = file.getCanonicalPath();
            if (!filePath.startsWith(rootPath + File.separator)) {
                throw new FileNotFoundException("outside clips dir");
            }
            if (!file.isFile()) throw new FileNotFoundException("not a file");
            return file;
        } catch (FileNotFoundException e) {
            throw e;
        } catch (Throwable t) {
            throw new FileNotFoundException("unresolvable uri: " + uri);
        }
    }

    @Override public boolean onCreate() { return true; }

    @Override public ParcelFileDescriptor openFile(Uri uri, String mode)
            throws FileNotFoundException {
        if (mode != null && (mode.contains("w") || mode.contains("+"))) {
            throw new SecurityException("read-only provider");
        }
        return ParcelFileDescriptor.open(resolve(uri),
                ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                 String[] selectionArgs, String sortOrder) {
        try {
            File file = resolve(uri);
            MatrixCursor cursor = new MatrixCursor(
                    new String[]{OpenableColumns.DISPLAY_NAME,
                                 OpenableColumns.SIZE}, 1);
            cursor.addRow(new Object[]{file.getName(), file.length()});
            return cursor;
        } catch (Throwable ignored) {
            return null;
        }
    }

    @Override public String getType(Uri uri) {
        String name = uri == null ? "" : String.valueOf(uri.getLastPathSegment());
        if (name.endsWith(".mp4")) return "video/mp4";
        if (name.endsWith(".webm")) return "video/webm";
        if (name.endsWith(".m4a") || name.endsWith(".mp3")) return "audio/*";
        return "video/*";
    }

    @Override public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("read-only");
    }

    @Override public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only");
    }

    @Override public int update(Uri uri, ContentValues values, String selection,
                               String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only");
    }
}
