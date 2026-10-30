package org.tinio.unwritten;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** Hub store client: lists published lessons, fetches one session in
 *  full, and deletes a hub record. Signer only — the hub lives on the
 *  signer, so direct (library-key) mode has no hub at all.
 *  Framework APIs only, no third-party libraries. All methods throw on
 *  failure; callers run them off the UI thread, like CloudUploader. */
public class HubClient {

    private final String signerUrl;
    private final String signerToken;

    public HubClient(String signerUrl, String signerToken) {
        this.signerUrl = signerUrl == null ? "" : signerUrl.trim();
        this.signerToken = signerToken == null ? "" : signerToken.trim();
    }

    public static boolean available(String signerUrl, String signerToken) {
        return signerUrl != null && !signerUrl.trim().isEmpty()
                && signerToken != null && !signerToken.trim().isEmpty();
    }

    public boolean available() {
        return available(signerUrl, signerToken);
    }

    /** Published sessions, newest first. */
    public JSONArray list() throws Exception {
        return new JSONArray(getRaw("/hub/sessions"));
    }

    /** One full session record (write-up, corrections, chapters, URLs). */
    public JSONObject get(String videoId) throws Exception {
        if (videoId == null || videoId.isEmpty()) throw new IOException("videoId required");
        return new JSONObject(getRaw("/hub/sessions/" + URLEncoder.encode(videoId, "UTF-8")));
    }

    /** Deletes a hub record. A missing record counts as gone. */
    public void delete(String videoId) throws Exception {
        if (videoId == null || videoId.isEmpty()) throw new IOException("videoId required");
        HttpURLConnection c = null;
        try {
            URL url = new URL(signerUrl + "/hub/sessions/" + URLEncoder.encode(videoId, "UTF-8"));
            c = (HttpURLConnection) url.openConnection();
            c.setRequestMethod("DELETE");
            c.setRequestProperty("Accept", "application/json");
            if (!signerToken.isEmpty()) c.setRequestProperty("X-Signer-Token", signerToken);
            c.setConnectTimeout(30000);
            c.setReadTimeout(30000);
            int status = c.getResponseCode();
            if (status != 200 && status != 204 && status != 404) {
                throw new IOException("Hub delete failed (" + status + "): " + readBody(c));
            }
        } finally {
            if (c != null) try { c.disconnect(); } catch (Throwable ignored) { }
        }
    }

    private String getRaw(String path) throws Exception {
        HttpURLConnection c = null;
        try {
            URL url = new URL(signerUrl + path);
            c = (HttpURLConnection) url.openConnection();
            c.setRequestMethod("GET");
            c.setRequestProperty("Accept", "application/json");
            if (!signerToken.isEmpty()) c.setRequestProperty("X-Signer-Token", signerToken);
            c.setConnectTimeout(30000);
            c.setReadTimeout(60000);
            int status = c.getResponseCode();
            String body = readBody(c);
            if (status < 200 || status >= 300) {
                throw new IOException("Hub request failed (" + status + "): " + body);
            }
            return body;
        } finally {
            if (c != null) try { c.disconnect(); } catch (Throwable ignored) { }
        }
    }

    private static String readBody(HttpURLConnection c) {
        InputStream in = null;
        try {
            int status = c.getResponseCode();
            in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            if (in == null) return "";
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } catch (Throwable ignored) {
            return "";
        } finally {
            if (in != null) try { in.close(); } catch (Throwable ignored) { }
        }
    }
}
