package org.tinio.unwritten;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.InetSocketAddress;
import java.net.URI;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;

import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/** Optional Cloud upload: presigned TUS (resumable) upload of a
 *  finished lesson, then status polling until Cloud finishes encoding.
 *  Two credential modes, mirroring the web recorder:
 *   - signer mode: POST {title[, videoId]} to the signer URL (see
 *     app/cloud-signer) -> {videoId, libraryId, signature, expire};
 *     the library API key never lives on this device.
 *   - direct mode: the library API key is configured on-device; this
 *     class creates the video and signs locally (SHA-256 of
 *     libraryId + apiKey + expire + videoId, per the vendor's TUS docs).
 *  Implemented over a raw SSLSocket instead of HttpURLConnection so
 *  TUS PATCH works on every supported Android version. Framework APIs
 *  only, no third-party libraries. All methods block; call off-UI. */
public final class CloudUploader {

    public interface Listener {
        void onSession(String videoId, String uploadUrl); // TUS resource known; persist for resume
        void onProgress(long sent, long total);
        void onUploaded(String videoId);        // bytes done; encoding next
        void onFinished(String videoId);        // status 4: playable
        void onFailed(String videoId, String message);
    }

    private static final String TUS_URL = "https://video.bunnycdn.com/tusupload";
    private static final String API = "https://video.bunnycdn.com";
    private static final int CHUNK = 5 * 1024 * 1024;

    final String libraryId;
    final String apiKey;       // direct mode only; "" in signer mode
    final String signerUrl;    // "" in direct mode
    final String signerToken;  // optional

    public CloudUploader(String libraryId, String apiKey, String signerUrl, String signerToken) {
        this.libraryId = libraryId == null ? "" : libraryId.trim();
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.signerUrl = signerUrl == null ? "" : signerUrl.trim();
        this.signerToken = signerToken == null ? "" : signerToken.trim();
    }

    public boolean configured() {
        if (!signerUrl.isEmpty()) return true;
        return !libraryId.isEmpty() && !apiKey.isEmpty();
    }

    private boolean useDirect() {
        return !libraryId.isEmpty() && !apiKey.isEmpty();
    }

    public String embedUrl(String libId, String videoId) {
        return "https://player.mediadelivery.net/embed/" + libId + "/" + videoId;
    }

    /** Library that credentials() most recently resolved (signer mode
     *  learns it from the signer response). */
    public volatile String lastLibraryId = "";

    /** Credentials for one video's TUS upload resource. */
    public static final class Creds {
        public String videoId, signature, libraryId;
        public long expire;
    }

    public Creds credentials(String title, String reuseVideoId) throws Exception {
        if (!useDirect()) {
            JSONObject body = new JSONObject();
            body.put("title", title);
            if (reuseVideoId != null) body.put("videoId", reuseVideoId);
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("Content-Type", "application/json");
            h.put("Accept", "application/json");
            if (!signerToken.isEmpty()) h.put("X-Signer-Token", signerToken);
            Resp r = request("POST", signerUrl, h, body.toString().getBytes("UTF-8"));
            if (r.status < 200 || r.status >= 300) throw new IOException("signer refused (" + r.status + ")");
            JSONObject d = new JSONObject(r.text());
            Creds c = new Creds();
            lastLibraryId = d.optString("libraryId", libraryId);
            c.videoId = d.optString("videoId", reuseVideoId == null ? "" : reuseVideoId);
            c.signature = d.optString("signature", "");
            c.expire = d.optLong("expire", 0);
            c.libraryId = d.optString("libraryId", libraryId);
            if (c.videoId.isEmpty() || c.signature.isEmpty() || c.expire == 0)
                throw new IOException("signer returned incomplete credentials");
            return c;
        }
        String videoId = reuseVideoId;
        if (videoId == null || videoId.isEmpty()) {
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("AccessKey", apiKey);
            h.put("Accept", "application/json");
            h.put("Content-Type", "application/json");
            JSONObject body = new JSONObject();
            body.put("title", title);
            Resp r = request("POST", API + "/library/" + libraryId + "/videos", h,
                    body.toString().getBytes("UTF-8"));
            if (r.status < 200 || r.status >= 300)
                throw new IOException("Cloud create failed (" + r.status + ") — check library ID and API key");
            JSONObject v = new JSONObject(r.text());
            videoId = v.optString("guid", "");
            if (videoId.isEmpty()) videoId = v.optString("videoId", "");
            if (videoId.isEmpty()) throw new IOException("Cloud create returned no video id");
        }
        Creds c = new Creds();
        lastLibraryId = libraryId;
        c.videoId = videoId;
        c.expire = System.currentTimeMillis() / 1000L + 86400L;
        c.signature = sha256Hex(libraryId + apiKey + c.expire + videoId);
        c.libraryId = libraryId;
        return c;
    }

    /** Video status: 0 created, 1 uploaded, 2 processing, 3 transcoding,
     *  4 finished/playable, 5 error, 6 upload failed. -1 on HTTP error. */
    /** Deletes the cloud copy. Throws on failure. */
    public void deleteVideo(String videoId) throws Exception {
        int status;
        if (!useDirect()) {
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("Accept", "application/json");
            if (!signerToken.isEmpty()) h.put("X-Signer-Token", signerToken);
            String sep = signerUrl.contains("?") ? "&" : "?";
            Resp r = request("DELETE", signerUrl + sep + "videoId=" + videoId, h, null);
            status = r.status;
        } else {
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("AccessKey", apiKey);
            h.put("Accept", "application/json");
            Resp r = request("DELETE", API + "/library/" + libraryId + "/videos/" + videoId, h, null);
            status = r.status;
        }
        if (status != 200 && status != 204 && status != 404)
            throw new IOException("Cloud delete failed (" + status + ")");
    }

    public int videoStatus(String videoId) throws Exception {
        String text;
        int status;
        if (!useDirect()) {
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("Accept", "application/json");
            if (!signerToken.isEmpty()) h.put("X-Signer-Token", signerToken);
            String sep = signerUrl.contains("?") ? "&" : "?";
            Resp r = request("GET", signerUrl + sep + "videoId=" + videoId, h, null);
            status = r.status; text = r.text();
        } else {
            Map<String, String> h = new LinkedHashMap<String, String>();
            h.put("AccessKey", apiKey);
            h.put("Accept", "application/json");
            Resp r = request("GET", API + "/library/" + libraryId + "/videos/" + videoId, h, null);
            status = r.status; text = r.text();
        }
        if (status < 200 || status >= 300) return -1;
        return new JSONObject(text).optInt("status", -1);
    }

    /** Full flow for one file: (resume or create) TUS upload, then poll
     *  encoding. savedUploadUrl/savedVideoId come from a previous attempt
     *  (pass nulls for a fresh upload). Listener callbacks fire on the
     *  calling thread. */
    public void upload(final File file, String savedUploadUrl, String savedVideoId,
                       final Listener listener) {
        String videoId = savedVideoId;
        try {
            Creds creds = credentials(file.getName(), savedVideoId);
            videoId = creds.videoId;
            String uploadUrl = savedUploadUrl;
            long offset = -1;
            if (uploadUrl != null && !uploadUrl.isEmpty()) {
                try { offset = tusHead(uploadUrl, creds); } catch (Exception ignored) { offset = -1; }
                if (offset < 0 || offset > file.length()) { uploadUrl = null; offset = -1; }
            }
            if (uploadUrl == null) {
                uploadUrl = tusCreate(creds, file);
                offset = 0;
            }
            listener.onSession(videoId, uploadUrl);
            tusSend(file, uploadUrl, creds, offset, listener);
            listener.onUploaded(videoId);
            for (int i = 0; i < 120; i++) {
                Thread.sleep(5000);
                int st;
                try { st = videoStatus(videoId); } catch (Exception e) { st = -1; }
                if (st == 4) { listener.onFinished(videoId); return; }
                if (st == 5 || st == 6) { listener.onFailed(videoId, "Cloud encoding failed (status " + st + ")"); return; }
            }
            listener.onFailed(videoId, "Still processing on Cloud — check the dashboard; the upload itself finished.");
        } catch (Exception e) {
            listener.onFailed(videoId, e.getMessage() == null ? "upload failed" : e.getMessage());
        }
    }

    private Map<String, String> authHeaders(Creds c) {
        Map<String, String> h = new LinkedHashMap<String, String>();
        h.put("AuthorizationSignature", c.signature);
        h.put("AuthorizationExpire", String.valueOf(c.expire));
        h.put("LibraryId", c.libraryId);
        h.put("VideoId", c.videoId);
        h.put("Tus-Resumable", "1.0.0");
        return h;
    }

    private String tusCreate(Creds creds, File file) throws Exception {
        Map<String, String> h = authHeaders(creds);
        h.put("Upload-Length", String.valueOf(file.length()));
        h.put("Upload-Metadata", "filetype " + b64("video/mp4") + ",title " + b64(file.getName()));
        Resp r = request("POST", TUS_URL, h, null);
        if (r.status != 201) throw new IOException("Cloud upload start failed (" + r.status + ")");
        String loc = r.headers.get("location");
        if (loc == null || loc.isEmpty()) throw new IOException("Cloud upload start returned no URL");
        return loc.startsWith("/") ? API + loc : loc;
    }

    private long tusHead(String uploadUrl, Creds creds) throws Exception {
        Resp r = request("HEAD", uploadUrl, authHeaders(creds), null);
        if (r.status == 404 || r.status == 410) return -1;
        if (r.status < 200 || r.status >= 300) throw new IOException("resume check " + r.status);
        String off = r.headers.get("upload-offset");
        try { return off == null ? -1 : Long.parseLong(off.trim()); }
        catch (NumberFormatException e) { return -1; }
    }

    private void tusSend(File file, String uploadUrl, Creds creds, long offset,
                         Listener listener) throws Exception {
        long total = file.length();
        int attempt = 0;
        RandomAccessFile raf = new RandomAccessFile(file, "r");
        try {
            byte[] buf = new byte[CHUNK];
            while (offset < total) {
                int want = (int) Math.min(CHUNK, total - offset);
                raf.seek(offset);
                int read = 0;
                while (read < want) {
                    int n = raf.read(buf, read, want - read);
                    if (n < 0) break;
                    read += n;
                }
                if (read <= 0) throw new IOException("could not read lesson file");
                Resp r;
                try {
                    Map<String, String> h = authHeaders(creds);
                    h.put("Upload-Offset", String.valueOf(offset));
                    h.put("Content-Type", "application/offset+octet-stream");
                    r = request("PATCH", uploadUrl, h, java.util.Arrays.copyOf(buf, read));
                } catch (IOException net) {
                    if (++attempt > 8) throw net;
                    long so = -1;
                    try { so = tusHead(uploadUrl, creds); } catch (Exception ignored) { }
                    if (so >= 0) offset = so;
                    Thread.sleep(Math.min(3000L * attempt, 15000L));
                    continue;
                }
                if (r.status >= 400 && r.status < 500 && r.status != 409 && r.status != 423)
                    throw new IOException("Cloud refused the upload (" + r.status + ")");
                if (r.status < 200 || r.status >= 300) {
                    if (++attempt > 8) throw new IOException("Cloud upload failed (" + r.status + ")");
                    long so = -1;
                    try { so = tusHead(uploadUrl, creds); } catch (Exception ignored) { }
                    if (so >= 0) offset = so;
                    Thread.sleep(Math.min(3000L * attempt, 15000L));
                    continue;
                }
                attempt = 0;
                String so = r.headers.get("upload-offset");
                long server = -1;
                if (so != null) { try { server = Long.parseLong(so.trim()); } catch (NumberFormatException ignored) { } }
                offset = server >= 0 ? server : offset + read;
                listener.onProgress(offset, total);
            }
        } finally {
            try { raf.close(); } catch (IOException ignored) { }
        }
    }

    // ------------------------------------------------------------ transport

    static final class Resp {
        int status;
        final Map<String, String> headers = new LinkedHashMap<String, String>();
        byte[] body = new byte[0];
        String text() throws Exception { return new String(body, "UTF-8"); }
    }

    /** Minimal HTTPS/1.1 over SSLSocket: no redirects, small responses. */
    private Resp request(String method, String url, Map<String, String> headers,
                         byte[] body) throws Exception {
        URI uri = new URI(url);
        String scheme = uri.getScheme() == null ? "https" : uri.getScheme();
        if (!"https".equalsIgnoreCase(scheme)) throw new IOException("https required: " + url);
        String host = uri.getHost();
        int port = uri.getPort() > 0 ? uri.getPort() : 443;
        String path = uri.getRawPath() == null || uri.getRawPath().isEmpty() ? "/" : uri.getRawPath();
        if (uri.getRawQuery() != null) path += "?" + uri.getRawQuery();

        SSLSocket socket = (SSLSocket) SSLSocketFactory.getDefault().createSocket();
        try {
            try {
                SSLParameters params = socket.getSSLParameters();
                params.setServerNames(java.util.Collections.singletonList(new SNIHostName(host)));
                socket.setSSLParameters(params);
            } catch (Exception ignored) { /* SNI not available — handshake will fail on SNI-required hosts */ }
            socket.connect(new InetSocketAddress(host, port), 20000);
            socket.setSoTimeout(60000);
            socket.startHandshake();
            OutputStream out = socket.getOutputStream();
            StringBuilder head = new StringBuilder();
            head.append(method).append(' ').append(path).append(" HTTP/1.1\r\n");
            head.append("Host: ").append(host).append("\r\n");
            head.append("Connection: close\r\n");
            head.append("User-Agent: UnwrittenRecorder/1.0\r\n");
            if (headers != null) for (Map.Entry<String, String> e : headers.entrySet())
                head.append(e.getKey()).append(": ").append(e.getValue()).append("\r\n");
            head.append("Content-Length: ").append(body == null ? 0 : body.length).append("\r\n\r\n");
            out.write(head.toString().getBytes("UTF-8"));
            if (body != null && body.length > 0) out.write(body);
            out.flush();
            return readResponse(socket.getInputStream());
        } finally {
            try { socket.close(); } catch (IOException ignored) { }
        }
    }

    private Resp readResponse(InputStream in) throws IOException {
        ByteArrayOutputStream raw = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int headerEnd = -1, total = 0, n;
        byte[] all = new byte[0];
        // Read until headers complete, then per Content-Length or chunked.
        while ((n = in.read(buf)) != -1) {
            raw.write(buf, 0, n);
            total += n;
            all = raw.toByteArray();
            if (headerEnd < 0) {
                headerEnd = indexOfHeaderEnd(all, total);
                if (headerEnd >= 0) {
                    Resp probe = parseHead(all, headerEnd);
                    String cl = probe.headers.get("content-length");
                    String te = probe.headers.get("transfer-encoding");
                    if (te != null && te.toLowerCase(java.util.Locale.US).contains("chunked")) {
                        // chunked: need to see terminating 0-chunk; wait for close or parse
                        // Don't break early — collect until stream closes, then decode
                    } else if (cl != null) {
                        int want = headerEnd + Integer.parseInt(cl.trim());
                        if (total >= want) break;
                    } else if (probe.status == 204 || probe.status == 304) break;
                    // otherwise (no length, no chunked): read until close
                }
            } else {
                Resp probe = parseHead(all, headerEnd);
                String cl = probe.headers.get("content-length");
                String te = probe.headers.get("transfer-encoding");
                if (te != null && te.toLowerCase(java.util.Locale.US).contains("chunked")) {
                    // wait for close
                } else if (cl != null && total >= headerEnd + Integer.parseInt(cl.trim())) break;
            }
        }
        all = raw.toByteArray();
        if (headerEnd < 0) headerEnd = indexOfHeaderEnd(all, all.length);
        if (headerEnd < 0) throw new IOException("no HTTP response");
        Resp resp = parseHead(all, headerEnd);
        String te = resp.headers.get("transfer-encoding");
        if (te != null && te.toLowerCase(java.util.Locale.US).contains("chunked")) {
            resp.body = decodeChunked(all, headerEnd);
        } else {
            int bodyLen = Math.max(0, all.length - headerEnd);
            String cl = resp.headers.get("content-length");
            if (cl != null) bodyLen = Math.min(bodyLen, Integer.parseInt(cl.trim()));
            resp.body = new byte[bodyLen];
            System.arraycopy(all, headerEnd, resp.body, 0, bodyLen);
        }
        return resp;
    }

    private static byte[] decodeChunked(byte[] all, int headerEnd) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int pos = headerEnd;
        while (pos < all.length) {
            int lineEnd = -1;
            for (int i = pos; i + 1 < all.length; i++) {
                if (all[i] == '\r' && all[i+1] == '\n') { lineEnd = i; break; }
            }
            if (lineEnd < 0) break;
            String hex = new String(all, pos, lineEnd - pos, "UTF-8").trim();
            int semi = hex.indexOf(';');
            if (semi >= 0) hex = hex.substring(0, semi).trim();
            int chunkSize;
            try { chunkSize = Integer.parseInt(hex, 16); } catch (NumberFormatException e) { break; }
            pos = lineEnd + 2;
            if (chunkSize == 0) break;
            if (pos + chunkSize > all.length) break; // incomplete
            out.write(all, pos, chunkSize);
            pos += chunkSize + 2; // skip trailing CRLF
        }
        return out.toByteArray();
    }

    private static int indexOfHeaderEnd(byte[] b, int len) {
        for (int i = 0; i + 3 < len; i++)
            if (b[i] == '\r' && b[i + 1] == '\n' && b[i + 2] == '\r' && b[i + 3] == '\n') return i + 4;
        return -1;
    }

    private Resp parseHead(byte[] all, int headerEnd) throws IOException {
        Resp resp = new Resp();
        String head = new String(all, 0, headerEnd, "UTF-8");
        String[] lines = head.split("\r\n");
        if (lines.length == 0) throw new IOException("empty response");
        String[] parts = lines[0].split(" ");
        if (parts.length < 2) throw new IOException("bad status line: " + lines[0]);
        resp.status = Integer.parseInt(parts[1]);
        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');
            if (colon > 0) resp.headers.put(
                    lines[i].substring(0, colon).trim().toLowerCase(java.util.Locale.US),
                    lines[i].substring(colon + 1).trim());
        }
        return resp;
    }

    static String sha256Hex(String text) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] digest = md.digest(text.getBytes("UTF-8"));
        StringBuilder sb = new StringBuilder(digest.length * 2);
        for (byte b : digest) sb.append(String.format("%02x", b & 0xff));
        return sb.toString();
    }

    private static String b64(String s) throws Exception {
        return android.util.Base64.encodeToString(s.getBytes("UTF-8"),
                android.util.Base64.NO_WRAP);
    }
}
