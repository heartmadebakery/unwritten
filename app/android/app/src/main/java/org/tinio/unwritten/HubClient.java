package org.tinio.unwritten;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.io.OutputStream;
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

    /** Operator set-asides, newest first: videos the hub never
     *  shows. The Record screen badges matching takes instead. */
    public JSONArray ignored() throws Exception {
        return new JSONArray(getRaw("/hub/ignored"));
    }

    /** One full session record (write-up, corrections, chapters, URLs). */
    public JSONObject get(String videoId) throws Exception {
        if (videoId == null || videoId.isEmpty()) throw new IOException("videoId required");
        return new JSONObject(getRaw("/hub/sessions/" + URLEncoder.encode(videoId, "UTF-8")));
    }

    /** Queues a video URL for the pipeline fetcher (YouTube/watch
     *  links the app cannot download itself). Returns the job id. */
    public String queueFetchJob(String url) throws Exception {
        return queueFetchJob(url, null);
    }

    /** Queues a link that continues a session: joinTo is that
     *  session's video id, and the signer ties the fetched video on as
     *  its next part once the pipeline is done. */
    public String queueFetchJob(String url, String joinTo) throws Exception {
        if (url == null || url.trim().isEmpty()) throw new IOException("url required");
        HttpURLConnection c = null;
        try {
            URL endpoint = new URL(signerUrl + "/fetch/jobs");
            c = (HttpURLConnection) endpoint.openConnection();
            c.setRequestMethod("POST");
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("Content-Type", "application/json");
            if (!signerToken.isEmpty()) c.setRequestProperty("X-Signer-Token", signerToken);
            c.setDoOutput(true);
            c.setConnectTimeout(30000);
            c.setReadTimeout(30000);
            JSONObject req = new JSONObject().put("url", url.trim());
            if (joinTo != null && !joinTo.trim().isEmpty()) req.put("joinTo", joinTo.trim());
            byte[] payload = req.toString().getBytes("UTF-8");
            OutputStream out = c.getOutputStream();
            try { out.write(payload); } finally { try { out.close(); } catch (Throwable ignored) { } }
            int status = c.getResponseCode();
            String body = readBody(c);
            if (status == 401) throw new IOException("Signer refused the token — rebuild the app to stamp a fresh one.");
            if (status < 200 || status >= 300) throw new IOException("Queue failed (" + status + "): " + body);
            String id = new JSONObject(body).optString("id", "");
            if (id.isEmpty()) throw new IOException("Queue returned no job id.");
            return id;
        } finally {
            if (c != null) try { c.disconnect(); } catch (Throwable ignored) { }
        }
    }

    /** Ties videos into one overall session: videoIds[1..] join the
     *  end of videoIds[0]'s session, in order. Returns {groupId, parts}. */
    public JSONObject tie(java.util.List<String> videoIds) throws Exception {
        if (videoIds == null || videoIds.size() < 2) throw new IOException("tie needs two videos");
        org.json.JSONArray ids = new org.json.JSONArray();
        for (String v : videoIds) ids.put(v);
        Object[] r = send("POST", "/hub/parts", new JSONObject().put("videoIds", ids).toString());
        int status = (Integer) r[0];
        if (status == 401) throw new IOException("Signer refused the token — rebuild the app to stamp a fresh one.");
        if (status < 200 || status >= 300) throw new IOException("Tie failed (" + status + "): " + r[1]);
        return new JSONObject((String) r[1]);
    }

    /** Unties one part: it stands alone again. Returns whether it was tied. */
    public boolean untie(String videoId) throws Exception {
        if (videoId == null || videoId.isEmpty()) throw new IOException("videoId required");
        Object[] r = send("DELETE", "/hub/parts/" + URLEncoder.encode(videoId, "UTF-8"), null);
        int status = (Integer) r[0];
        if (status < 200 || status >= 300) throw new IOException("Untie failed (" + status + "): " + r[1]);
        return new JSONObject((String) r[1]).optBoolean("untied", false);
    }

    private Object[] send(String method, String path, String json) throws Exception {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(signerUrl + path).openConnection();
            c.setRequestMethod(method);
            c.setRequestProperty("Accept", "application/json");
            if (!signerToken.isEmpty()) c.setRequestProperty("X-Signer-Token", signerToken);
            c.setConnectTimeout(30000);
            c.setReadTimeout(30000);
            if (json != null) {
                c.setRequestProperty("Content-Type", "application/json");
                c.setDoOutput(true);
                OutputStream out = c.getOutputStream();
                try { out.write(json.getBytes("UTF-8")); } finally { try { out.close(); } catch (Throwable ignored) { } }
            }
            int status = c.getResponseCode();
            return new Object[] { status, readBody(c) };
        } finally {
            if (c != null) try { c.disconnect(); } catch (Throwable ignored) { }
        }
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
