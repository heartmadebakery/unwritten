package org.tinio.unwritten;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CameraMetadata;
import android.hardware.camera2.CaptureFailure;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.TotalCaptureResult;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Log;
import android.util.Size;
import android.view.Surface;
import android.view.TextureView;
import android.view.WindowManager;

import java.io.File;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/**
 * Careful Camera2 wrapper for the Pixel 4 base device (and anything
 * at or above its Android 10 / API 29 baseline).
 * All camera work runs on a single HandlerThread named "uw-cam".
 * No public method throws.
 */
public final class CameraEngine {
    private static final String TAG = "UWCam";

    public interface LumaListener { void onLuma(double mean, double[] grid); }
    public interface PhotoListener { void onPhoto(byte[] jpeg); }
    public interface ErrorListener { void onError(String message); }

    private final Context appContext;
    private final ErrorListener errors;

    // Thread lifecycle (guarded by threadLock where noted).
    private final Object threadLock = new Object();
    private HandlerThread camThread;
    private Handler camHandler;

    // Generation guards stale callbacks/runnables after close()/reopen.
    private volatile int generation;

    private volatile TextureView textureView;

    // Camera state (mostly confined to cam thread; volatile for public reads).
    private CameraDevice camera;
    private CameraCharacteristics characteristics;
    private String cameraId;
    private int lensFacing = CameraCharacteristics.LENS_FACING_BACK;
    private int sensorOrientation;
    private CameraCaptureSession session;
    private Surface previewSurface;

    private Size videoSize;
    private Size previewSize;
    private Size yuvSize;
    private Size jpegSize;

    private ImageReader yuvReader;
    private ImageReader jpegReader;

    private float maxDigitalZoom = 1.0f;
    private float currentZoom = 1.0f;
    private android.graphics.Rect activeArrayRect;

    private volatile LumaListener lumaListener;
    private long lastLumaMs;

    private MediaRecorder recorder;
    private Surface recorderSurface;
    private volatile boolean recording;
    private volatile boolean recorderStartPending;
    private long recordStartMs;

    private volatile boolean cameraOpening;
    private volatile boolean sessionConfiguring;
    private volatile File queuedVideoFile;

    private PhotoListener pendingPhotoListener;
    private boolean photoInProgress;
    private boolean photoSessionActive;
    private boolean photoCaptureDone;
    private boolean photoImageDone;

    public CameraEngine(Context context, ErrorListener errors) {
        Context c = context != null ? context.getApplicationContext() : null;
        this.appContext = c != null ? c : context;
        this.errors = errors;
    }

    // ------------------------------------------------------------------ util

    private void reportError(String message) {
        try { Log.w(TAG, message); } catch (Throwable ignored) { }
        ErrorListener l = errors;
        if (l != null) {
            try { l.onError(message); } catch (Throwable ignored) { }
        }
    }

    private boolean ensureThread() {
        synchronized (threadLock) {
            if (camThread != null && camThread.isAlive() && camHandler != null) return true;
            try {
                camThread = new HandlerThread("uw-cam");
                camThread.start();
                camHandler = new Handler(camThread.getLooper());
                return true;
            } catch (Throwable t) {
                camThread = null;
                camHandler = null;
                return false;
            }
        }
    }

    private Handler handler() {
        synchronized (threadLock) { return camHandler; }
    }

    private boolean post(final int gen, final Runnable r) {
        Handler h = handler();
        if (h == null) return false;
        try {
            return h.post(new Runnable() {
                @Override public void run() {
                    if (gen != generation) return;
                    try { r.run(); } catch (Throwable t) {
                        reportError("Camera operation failed: " + t.getMessage());
                    }
                }
            });
        } catch (Throwable t) {
            return false;
        }
    }

    // ------------------------------------------------------------- public API

    public void openPreview(final TextureView view) {
        try {
            if (view == null) { reportError("openPreview: null TextureView"); return; }
            if (appContext == null) { reportError("openPreview: null Context"); return; }
            if (!ensureThread()) { reportError("openPreview: could not start camera thread"); return; }
            final int gen = ++generation;
            textureView = view;
            view.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
                @Override public void onSurfaceTextureAvailable(SurfaceTexture st, int w, int h) {
                    post(gen, new Runnable() {
                        @Override public void run() { openCameraLocked(gen); }
                    });
                }
                @Override public void onSurfaceTextureSizeChanged(SurfaceTexture st, int w, int h) {
                    post(gen, new Runnable() {
                        @Override public void run() {
                            if (camera != null) {
                                releasePreviewSurface();
                                createPreviewSurface();
                                buildSession(recorderSurface != null, false);
                            }
                        }
                    });
                }
                @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture st) {
                    post(gen, new Runnable() {
                        @Override public void run() { closeCameraOnly(); }
                    });
                    return true;
                }
                @Override public void onSurfaceTextureUpdated(SurfaceTexture st) { }
            });
            if (view.isAvailable()) {
                post(gen, new Runnable() {
                    @Override public void run() { openCameraLocked(gen); }
                });
            }
        } catch (Throwable t) {
            reportError("openPreview failed: " + t.getMessage());
        }
    }

    public void setLumaListener(final LumaListener l) {
        try {
            lumaListener = l;
            final int gen = generation;
            Handler h = handler();
            if (h == null || camera == null) return;
            if (!post(gen, new Runnable() {
                @Override public void run() {
                    if (l == null) {
                        closeYuvReader();
                        if (camera != null) buildSession(recorderSurface != null, false);
                    } else {
                        ensureYuvReader(gen);
                        if (camera != null) buildSession(recorderSurface != null, false);
                    }
                }
            })) {
                // No thread; value is stored and applied on next open.
            }
        } catch (Throwable t) {
            reportError("setLumaListener failed: " + t.getMessage());
        }
    }

    public boolean startVideo(final File out) {
        try {
            if (out == null) { reportError("startVideo: null output file"); return false; }
            if (handler() == null) { reportError("startVideo: camera not open"); return false; }
            if (recording || recorderStartPending) {
                reportError("startVideo: already recording");
                return false;
            }
            if (photoInProgress) { reportError("startVideo: photo in progress"); return false; }
            if (queuedVideoFile != null) { reportError("startVideo: a start is already queued"); return false; }
            if (camera == null && !cameraOpening) {
                reportError("startVideo: camera not open");
                return false;
            }
            final int gen = generation;
            boolean posted = post(gen, new Runnable() {
                @Override public void run() { startVideoInternal(out); }
            });
            if (!posted) { reportError("startVideo: camera thread unavailable"); return false; }
            return true;
        } catch (Throwable t) {
            reportError("startVideo failed: " + t.getMessage());
            return false;
        }
    }

    public void stopVideo() {
        try {
            final int gen = generation;
            if (handler() == null) return;
            post(gen, new Runnable() {
                @Override public void run() { stopVideoInternal(); }
            });
        } catch (Throwable t) {
            reportError("stopVideo failed: " + t.getMessage());
        }
    }

    public boolean isRecording() {
        return recording;
    }

    public float getMaxZoom() { return maxDigitalZoom > 1.0f ? maxDigitalZoom : 1.0f; }
    public float getZoom() { return currentZoom; }
    public void setZoom(final float zoom) {
        final float clamped = Math.max(1.0f, Math.min(getMaxZoom(), zoom));
        currentZoom = clamped;
        final int gen = generation;
        Handler h = handler();
        if (h != null && camera != null) {
            post(gen, new Runnable() { @Override public void run() { applyZoomToSession(clamped); } });
        }
    }
    private void applyZoomToSession(float zoom) {
        if (session == null || camera == null) return;
        try {
            boolean hasRecorder = recorderSurface != null && recorder != null;
            CaptureRequest.Builder b = camera.createCaptureRequest(
                    hasRecorder ? CameraDevice.TEMPLATE_RECORD : CameraDevice.TEMPLATE_PREVIEW);
            b.addTarget(previewSurface);
            if (hasRecorder) b.addTarget(recorderSurface);
            if (lumaListener != null && yuvReader != null) {
                try { b.addTarget(yuvReader.getSurface()); } catch (Throwable ignored) {}
            }
            b.set(CaptureRequest.CONTROL_AF_MODE, hasRecorder
                    ? CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO
                    : CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            try { b.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON); } catch (Throwable ignored) {}
            applyZoom(b, zoom);
            session.setRepeatingRequest(b.build(), null, handler());
        } catch (Throwable t) {
            reportError("Zoom failed: " + t.getMessage());
        }
    }
    private void applyZoom(CaptureRequest.Builder b, float zoom) {
        if (zoom <= 1.0f) return;
        // Prefer CONTROL_ZOOM_RATIO on API 30+ (compileSdk 34 has it)
        try {
            b.set(CaptureRequest.CONTROL_ZOOM_RATIO, zoom);
            return;
        } catch (Throwable ignored) {}
        // Fallback: crop region
        if (activeArrayRect == null) return;
        int cx = activeArrayRect.centerX();
        int cy = activeArrayRect.centerY();
        int w = (int) (activeArrayRect.width() / zoom);
        int h = (int) (activeArrayRect.height() / zoom);
        w = w & ~1; h = h & ~1; // even
        android.graphics.Rect crop = new android.graphics.Rect(cx - w/2, cy - h/2, cx + w/2, cy + h/2);
        try { b.set(CaptureRequest.SCALER_CROP_REGION, crop); } catch (Throwable ignored) {}
    }

    public void takePhoto(final PhotoListener l) {
        try {
            if (l == null) { reportError("takePhoto: null listener"); return; }
            if (recording || recorderStartPending) {
                reportError("takePhoto: photos are for between takes (recording in progress)");
                return;
            }
            if (handler() == null || camera == null) {
                if (handler() == null) { reportError("takePhoto: camera not open"); return; }
                // Camera may still be opening; queue onto cam thread to re-check.
            }
            final int gen = generation;
            boolean posted = post(gen, new Runnable() {
                @Override public void run() { takePhotoInternal(l); }
            });
            if (!posted) reportError("takePhoto: camera not open");
        } catch (Throwable t) {
            reportError("takePhoto failed: " + t.getMessage());
        }
    }

    public void close() {
        try {
            ++generation; // invalidate pending callbacks/runnables
            // Snapshot current resources so a later reopen's resources are untouched.
            final CameraCaptureSession s = session;
            final CameraDevice c = camera;
            final ImageReader y = yuvReader;
            final ImageReader j = jpegReader;
            final MediaRecorder r = recorder;
            final Surface rs = recorderSurface;
            final Surface ps = previewSurface;
            final boolean wasRecording = recording;

            session = null;
            camera = null;
            yuvReader = null;
            jpegReader = null;
            recorder = null;
            recorderSurface = null;
            previewSurface = null;
            recording = false;
            recorderStartPending = false;
            queuedVideoFile = null;
            pendingPhotoListener = null;
            photoInProgress = false;
            photoSessionActive = false;
            sessionConfiguring = false;
            cameraOpening = false;
            characteristics = null;

            HandlerThread t;
            Handler h;
            synchronized (threadLock) {
                t = camThread;
                h = camHandler;
                camThread = null;
                camHandler = null;
            }
            Runnable cleanup = new Runnable() {
                @Override public void run() {
                    closeResources(s, c, y, j, r, rs, ps, wasRecording);
                }
            };
            if (h != null && t != null && t.isAlive()) {
                try { h.post(cleanup); } catch (Throwable ignored) { cleanup.run(); }
                try { t.quitSafely(); } catch (Throwable ignored) { }
            } else {
                cleanup.run();
            }
        } catch (Throwable t) {
            try { Log.w(TAG, "close failed: " + t.getMessage()); } catch (Throwable ignored) { }
        }
    }

    // ------------------------------------------------------------ camera open

    private void openCameraLocked(final int gen) {
        if (gen != generation) return;
        if (camera != null) { buildSession(recorderSurface != null, false); return; }
        if (cameraOpening) return;
        TextureView view = textureView;
        if (view == null || !view.isAvailable()) return;
        CameraManager manager = null;
        try {
            manager = (CameraManager) appContext.getSystemService(Context.CAMERA_SERVICE);
        } catch (Throwable ignored) { }
        if (manager == null) { reportError("Camera service unavailable"); return; }
        try {
            String chosen = null;
            int chosenFacing = CameraCharacteristics.LENS_FACING_BACK;
            String front = null;
            String first = null;
            CameraCharacteristics chosenChars = null, frontChars = null, firstChars = null;
            for (String id : manager.getCameraIdList()) {
                CameraCharacteristics cc = manager.getCameraCharacteristics(id);
                if (first == null) { first = id; firstChars = cc; }
                Integer f = cc.get(CameraCharacteristics.LENS_FACING);
                if (f != null && f == CameraCharacteristics.LENS_FACING_BACK) {
                    chosen = id; chosenFacing = f; chosenChars = cc; break;
                }
                if (f != null && f == CameraCharacteristics.LENS_FACING_FRONT && front == null) {
                    front = id; frontChars = cc;
                }
            }
            if (chosen == null && front != null) { chosen = front; chosenChars = frontChars; chosenFacing = CameraCharacteristics.LENS_FACING_FRONT; }
            if (chosen == null) { chosen = first; chosenChars = firstChars; }
            if (chosen == null || chosenChars == null) { reportError("No camera found"); return; }
            cameraId = chosen;
            characteristics = chosenChars;
            lensFacing = chosenFacing;
            Integer so = chosenChars.get(CameraCharacteristics.SENSOR_ORIENTATION);
            sensorOrientation = so != null ? so : 0;
            try {
                Float mz = chosenChars.get(CameraCharacteristics.SCALER_AVAILABLE_MAX_DIGITAL_ZOOM);
                if (mz != null) maxDigitalZoom = mz;
            } catch (Throwable ignored) { maxDigitalZoom = 1.0f; }
            try {
                android.graphics.Rect aa = chosenChars.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
                if (aa != null) activeArrayRect = aa;
            } catch (Throwable ignored) {}
            computeSizes(chosenChars);
            cameraOpening = true;
            manager.openCamera(chosen, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice device) {
                    if (gen != generation) { try { device.close(); } catch (Throwable ignored) { } return; }
                    cameraOpening = false;
                    camera = device;
                    try {
                        createPreviewSurface();
                        if (lumaListener != null) ensureYuvReader(gen);
                        buildSession(false, false);
                        // A video start queued while opening now proceeds.
                        File q = queuedVideoFile;
                        if (q != null) { queuedVideoFile = null; startVideoInternal(q); }
                    } catch (Throwable t) {
                        reportError("Camera setup failed: " + t.getMessage());
                        closeCameraOnly();
                    }
                }
                @Override public void onDisconnected(CameraDevice device) {
                    if (gen == generation) { cameraOpening = false; reportError("Camera disconnected"); }
                    try { device.close(); } catch (Throwable ignored) { }
                    if (gen == generation && camera == device) { camera = null; closeSessionOnly(); }
                }
                @Override public void onError(CameraDevice device, int error) {
                    if (gen == generation) { cameraOpening = false; reportError("Camera error: " + error); }
                    try { device.close(); } catch (Throwable ignored) { }
                    if (gen == generation && camera == device) { camera = null; closeSessionOnly(); }
                }
            }, handler());
        } catch (SecurityException se) {
            cameraOpening = false;
            reportError("Camera permission missing");
        } catch (Throwable t) {
            cameraOpening = false;
            reportError("openCamera failed: " + t.getMessage());
        }
    }

    private void computeSizes(CameraCharacteristics cc) {
        StreamConfigurationMap map = cc.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        if (map == null) {
            videoSize = new Size(640, 480);
            previewSize = videoSize;
            yuvSize = new Size(640, 480);
            jpegSize = videoSize;
            return;
        }
        // Video: largest <=1280x720, prefer 16:9, else first size.
        Size[] vSizes = null;
        try { vSizes = map.getOutputSizes(MediaRecorder.class); } catch (Throwable ignored) { }
        videoSize = pickVideoSize(vSizes);
        // Preview: largest <=1920x1080 with aspect close to video.
        Size[] pSizes = null;
        try { pSizes = map.getOutputSizes(SurfaceTexture.class); } catch (Throwable ignored) { }
        previewSize = pickPreviewSize(pSizes, videoSize);
        // YUV: closest <=640 wide.
        Size[] ySizes = null;
        try { ySizes = map.getOutputSizes(ImageFormat.YUV_420_888); } catch (Throwable ignored) { }
        yuvSize = pickYuvSize(ySizes);
        // JPEG: largest <=2560 wide.
        Size[] jSizes = null;
        try { jSizes = map.getOutputSizes(ImageFormat.JPEG); } catch (Throwable ignored) { }
        jpegSize = pickJpegSize(jSizes);
    }

    private static long area(Size s) { return (long) s.getWidth() * s.getHeight(); }

    private static Size pickVideoSize(Size[] sizes) {
        if (sizes == null || sizes.length == 0) return new Size(640, 480);
        Size best169 = null, bestAny = null;
        for (Size s : sizes) {
            if (s.getWidth() <= 1280 && s.getHeight() <= 720) {
                if (bestAny == null || area(s) > area(bestAny)) bestAny = s;
                double ar = (double) s.getWidth() / s.getHeight();
                if (Math.abs(ar - 16.0 / 9.0) < 0.02) {
                    if (best169 == null || area(s) > area(best169)) best169 = s;
                }
            }
        }
        if (best169 != null) return best169;
        if (bestAny != null) return bestAny;
        return sizes[0];
    }

    private static Size pickPreviewSize(Size[] sizes, Size video) {
        if (sizes == null || sizes.length == 0) return video != null ? video : new Size(640, 480);
        double target = video != null ? (double) video.getWidth() / video.getHeight() : 16.0 / 9.0;
        Size bestClose = null, bestFallback = null;
        double bestFallbackDiff = Double.MAX_VALUE;
        for (Size s : sizes) {
            if (s.getWidth() <= 1920 && s.getHeight() <= 1080) {
                double diff = Math.abs((double) s.getWidth() / s.getHeight() - target);
                if (diff < 0.02) {
                    if (bestClose == null || area(s) > area(bestClose)) bestClose = s;
                }
                if (diff < bestFallbackDiff - 1e-9
                        || (Math.abs(diff - bestFallbackDiff) < 1e-9 && bestFallback != null && area(s) > area(bestFallback))
                        || bestFallback == null) {
                    if (diff < bestFallbackDiff - 1e-9 || bestFallback == null
                            || area(s) > area(bestFallback)) {
                        bestFallback = s; bestFallbackDiff = diff;
                    }
                }
            }
        }
        if (bestClose != null) return bestClose;
        if (bestFallback != null) return bestFallback;
        return sizes[0];
    }

    private static Size pickYuvSize(Size[] sizes) {
        if (sizes == null || sizes.length == 0) return new Size(640, 480);
        Size best = null;
        for (Size s : sizes) {
            if (s.getWidth() <= 640 && (best == null || area(s) > area(best))) best = s;
        }
        if (best != null) return best;
        Size smallest = sizes[0];
        for (Size s : sizes) if (area(s) < area(smallest)) smallest = s;
        return smallest;
    }

    private static Size pickJpegSize(Size[] sizes) {
        if (sizes == null || sizes.length == 0) return new Size(1280, 720);
        Size best = null, largest = sizes[0];
        for (Size s : sizes) {
            if (area(s) > area(largest)) largest = s;
            if (s.getWidth() <= 2560 && (best == null || area(s) > area(best))) best = s;
        }
        return best != null ? best : largest;
    }

    private void createPreviewSurface() {
        releasePreviewSurface();
        TextureView view = textureView;
        if (view == null) return;
        SurfaceTexture st = view.getSurfaceTexture();
        if (st == null) return;
        Size p = previewSize != null ? previewSize : new Size(640, 480);
        try { st.setDefaultBufferSize(p.getWidth(), p.getHeight()); } catch (Throwable ignored) { }
        previewSurface = new Surface(st);
    }

    private void releasePreviewSurface() {
        if (previewSurface != null) {
            try { previewSurface.release(); } catch (Throwable ignored) { }
            previewSurface = null;
        }
    }

    // ---------------------------------------------------------------- readers

    private void ensureYuvReader(final int gen) {
        if (yuvReader != null) return;
        Size s = yuvSize != null ? yuvSize : new Size(640, 480);
        try {
            ImageReader r = ImageReader.newInstance(s.getWidth(), s.getHeight(), ImageFormat.YUV_420_888, 2);
            r.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
                @Override public void onImageAvailable(ImageReader reader) {
                    if (gen != generation) {
                        Image im = null;
                        try { im = reader.acquireLatestImage(); } catch (Throwable ignored) { }
                        if (im != null) { try { im.close(); } catch (Throwable ignored) { } }
                        return;
                    }
                    handleYuvImage(reader);
                }
            }, handler());
            yuvReader = r;
        } catch (Throwable t) {
            reportError("YUV reader failed: " + t.getMessage());
        }
    }

    private void closeYuvReader() {
        if (yuvReader != null) {
            try { yuvReader.close(); } catch (Throwable ignored) { }
            yuvReader = null;
        }
    }

    private void handleYuvImage(ImageReader reader) {
        Image image = null;
        try {
            image = reader.acquireLatestImage();
            if (image == null) return;
            LumaListener l = lumaListener;
            if (l == null) return;
            long now = SystemClock.elapsedRealtime();
            if (now - lastLumaMs < 100) return; // at most 10 fps
            lastLumaMs = now;
            int w = image.getWidth();
            int h = image.getHeight();
            Image.Plane[] planes = image.getPlanes();
            if (planes == null || planes.length == 0) return;
            Image.Plane yPlane = planes[0];
            ByteBuffer buf = yPlane.getBuffer();
            if (buf == null) return;
            int rowStride = yPlane.getRowStride();
            int pixelStride = yPlane.getPixelStride();
            byte[] packed = new byte[w * h];
            ByteBuffer dup = buf.duplicate();
            if (pixelStride == 1) {
                // Tightly packed copy: strip row padding (old-Android Y planes have pixelStride 1).
                for (int row = 0; row < h; row++) {
                    int srcPos = row * rowStride;
                    if (srcPos >= dup.limit()) break;
                    dup.position(srcPos);
                    int toCopy = Math.min(w, dup.remaining());
                    dup.get(packed, row * w, toCopy);
                }
            } else {
                for (int row = 0; row < h; row++) {
                    for (int col = 0; col < w; col++) {
                        int idx = row * rowStride + col * pixelStride;
                        packed[row * w + col] = idx < dup.limit() ? dup.get(idx) : 0;
                    }
                }
            }
            double[] result;
            try {
                result = NativeCore.nativeLuma(packed, w, h, w);
            } catch (Throwable t) {
                reportError("nativeLuma failed: " + t.getMessage());
                return;
            }
            if (result == null || result.length < 65) return;
            double mean = result[0];
            double[] grid = new double[64];
            System.arraycopy(result, 1, grid, 0, 64);
            LumaListener listener = lumaListener;
            if (listener != null) {
                try { listener.onLuma(mean, grid); } catch (Throwable ignored) { }
            }
        } catch (Throwable t) {
            reportError("YUV frame failed: " + t.getMessage());
        } finally {
            if (image != null) {
                try { image.close(); } catch (Throwable ignored) { }
            }
        }
    }

    private void ensureJpegReader(final int gen) {
        closeJpegReader();
        Size s = jpegSize != null ? jpegSize : new Size(1280, 720);
        ImageReader r = ImageReader.newInstance(s.getWidth(), s.getHeight(), ImageFormat.JPEG, 2);
        r.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
            @Override public void onImageAvailable(ImageReader reader) {
                Image image = null;
                try {
                    image = reader.acquireLatestImage();
                    if (image == null) return;
                    Image.Plane[] planes = image.getPlanes();
                    if (planes == null || planes.length == 0) return;
                    ByteBuffer buf = planes[0].getBuffer();
                    if (buf == null) return;
                    byte[] bytes = new byte[buf.remaining()];
                    buf.get(bytes);
                    PhotoListener l = pendingPhotoListener;
                    pendingPhotoListener = null;
                    photoImageDone = true;
                    if (l != null) {
                        try { l.onPhoto(bytes); } catch (Throwable ignored) { }
                    }
                } catch (Throwable t) {
                    reportError("JPEG read failed: " + t.getMessage());
                    pendingPhotoListener = null;
                    photoImageDone = true;
                } finally {
                    if (image != null) {
                        try { image.close(); } catch (Throwable ignored) { }
                    }
                }
                maybeFinishPhoto();
            }
        }, handler());
        jpegReader = r;
    }

    private void closeJpegReader() {
        if (jpegReader != null) {
            try { jpegReader.close(); } catch (Throwable ignored) { }
            jpegReader = null;
        }
    }

    // ---------------------------------------------------------------- session

    private void closeSessionOnly() {
        if (session != null) {
            try { session.close(); } catch (Throwable ignored) { }
            session = null;
        }
        sessionConfiguring = false;
    }

    private void buildSession(final boolean includeRecorder, final boolean includeJpeg) {
        final int gen = generation;
        if (camera == null || previewSurface == null) return;
        closeSessionOnly();
        final List<Surface> surfaces = new ArrayList<Surface>();
        surfaces.add(previewSurface);
        Surface recSurf = null;
        if (includeRecorder && recorderSurface != null) { recSurf = recorderSurface; surfaces.add(recSurf); }
        if (lumaListener != null && yuvReader != null) {
            try { surfaces.add(yuvReader.getSurface()); } catch (Throwable ignored) { }
        }
        if (includeJpeg && jpegReader != null) {
            try { surfaces.add(jpegReader.getSurface()); } catch (Throwable ignored) { }
        }
        final boolean wantRecorder = recSurf != null;
        final boolean wantJpeg = includeJpeg;
        sessionConfiguring = true;
        try {
            camera.createCaptureSession(surfaces, new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession s) {
                    if (gen != generation) { try { s.close(); } catch (Throwable ignored) { } return; }
                    sessionConfiguring = false;
                    session = s;
                    startRepeating();
                    if (wantRecorder && recorderStartPending && recorder != null) {
                        try {
                            recorder.start();
                            recording = true;
                            recordStartMs = SystemClock.elapsedRealtime();
                        } catch (Throwable t) {
                            reportError("MediaRecorder start failed: " + t.getMessage());
                            releaseRecorder();
                            recorderSurface = null;
                            recording = false;
                            buildSession(false, false);
                            return;
                        } finally {
                            recorderStartPending = false;
                        }
                    }
                    if (wantJpeg && photoInProgress) {
                        doStillCapture();
                    }
                    // Process a queued video start now that no rebuild is in flight.
                    if (!recording && !recorderStartPending && !photoInProgress) {
                        File q = queuedVideoFile;
                        if (q != null) {
                            queuedVideoFile = null;
                            startVideoInternal(q);
                        }
                    }
                }
                @Override public void onConfigureFailed(CameraCaptureSession s) {
                    if (gen != generation) { try { s.close(); } catch (Throwable ignored) { } return; }
                    sessionConfiguring = false;
                    try { s.close(); } catch (Throwable ignored) { }
                    if (session == s) session = null;
                    reportError("Capture session configuration failed");
                    if (recorderStartPending || recorder != null) {
                        releaseRecorder();
                        recorderSurface = null;
                        recorderStartPending = false;
                        recording = false;
                    }
                    if (photoInProgress) {
                        pendingPhotoListener = null;
                        photoInProgress = false;
                        photoSessionActive = false;
                        closeJpegReader();
                    }
                    // Try to fall back to a plain preview session (once, without recorder/jpeg).
                    if (camera != null && previewSurface != null && !wantRecorder && !wantJpeg) {
                        // Already plain; stay clean without looping.
                    } else if (camera != null) {
                        buildSession(false, false);
                    }
                }
            }, handler());
        } catch (Throwable t) {
            sessionConfiguring = false;
            reportError("createCaptureSession failed: " + t.getMessage());
            if (recorder != null) { releaseRecorder(); recorderSurface = null; recorderStartPending = false; }
            if (photoInProgress) {
                pendingPhotoListener = null;
                photoInProgress = false;
                photoSessionActive = false;
                closeJpegReader();
            }
        }
    }

    private void startRepeating() {
        if (session == null || camera == null) return;
        try {
            boolean hasRecorder = recorderSurface != null && recorder != null;
            CaptureRequest.Builder b = camera.createCaptureRequest(
                    hasRecorder ? CameraDevice.TEMPLATE_RECORD : CameraDevice.TEMPLATE_PREVIEW);
            b.addTarget(previewSurface);
            if (hasRecorder) b.addTarget(recorderSurface);
            if (lumaListener != null && yuvReader != null) {
                try { b.addTarget(yuvReader.getSurface()); } catch (Throwable ignored) { }
            }
            b.set(CaptureRequest.CONTROL_AF_MODE, hasRecorder
                    ? CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO
                    : CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            try { b.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON); } catch (Throwable ignored) { }
            applyZoom(b, currentZoom);
            session.setRepeatingRequest(b.build(), null, handler());
        } catch (Throwable t) {
            // A closed session during teardown is not fatal.
            if (camera != null) reportError("Repeating request failed: " + t.getMessage());
        }
    }

    // ------------------------------------------------------------------ video

    private void startVideoInternal(File out) {
        if (recording || recorder != null || recorderStartPending) {
            reportError("startVideo: already recording");
            return;
        }
        if (photoInProgress) { reportError("startVideo: photo in progress"); return; }
        if (camera == null || cameraOpening || sessionConfiguring) {
            if (queuedVideoFile == null) {
                queuedVideoFile = out; // queue until the in-flight rebuild/open completes
            } else {
                reportError("startVideo: a start is already queued");
            }
            return;
        }
        if (previewSurface == null) { reportError("startVideo: preview not ready"); return; }

        boolean audioOn = hasAudioPermission();
        if (!audioOn) reportError("Audio permission missing; recording video-only");

        MediaRecorder mr = new MediaRecorder();
        try {
            mr.setVideoSource(MediaRecorder.VideoSource.SURFACE);
            if (audioOn) {
                try {
                    mr.setAudioSource(MediaRecorder.AudioSource.MIC);
                } catch (Throwable t) {
                    audioOn = false;
                    reportError("Audio source unavailable; recording video-only");
                    // Recreate so a half-configured recorder cannot poison the take.
                    try { mr.reset(); } catch (Throwable ignored) { }
                    try { mr.release(); } catch (Throwable ignored) { }
                    mr = new MediaRecorder();
                    mr.setVideoSource(MediaRecorder.VideoSource.SURFACE);
                }
            }
            mr.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            mr.setOutputFile(out.getAbsolutePath());
            mr.setVideoEncoder(MediaRecorder.VideoEncoder.H264);
            if (audioOn) {
                mr.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            }
            mr.setVideoEncodingBitRate(4_000_000);
            if (audioOn) {
                mr.setAudioEncodingBitRate(128_000);
                mr.setAudioSamplingRate(44_100);
            }
            Size vs = videoSize != null ? videoSize : new Size(640, 480);
            mr.setVideoSize(vs.getWidth(), vs.getHeight());
            mr.setVideoFrameRate(30);
            try { mr.setOrientationHint(computeOrientationHint()); } catch (Throwable ignored) { }
            mr.prepare();
        } catch (Throwable t) {
            reportError("MediaRecorder setup failed: " + t.getMessage());
            try { mr.reset(); } catch (Throwable ignored) { }
            try { mr.release(); } catch (Throwable ignored) { }
            return;
        }
        recorder = mr;
        try {
            recorderSurface = mr.getSurface();
        } catch (Throwable t) {
            reportError("MediaRecorder surface failed: " + t.getMessage());
            releaseRecorder();
            return;
        }
        recorderStartPending = true;
        buildSession(true, false);
        if (!sessionConfiguring && session == null) {
            // buildSession failed synchronously and already cleaned up where possible.
            if (recorder != null) { releaseRecorder(); recorderSurface = null; recorderStartPending = false; }
        }
    }

    private boolean hasAudioPermission() {
        try {
            if (appContext == null) return false;
            // RECORD_AUDIO is a runtime permission (API 23+); minSdk is 29.
            return appContext.checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                    == PackageManager.PERMISSION_GRANTED;
        } catch (Throwable t) {
            return false;
        }
    }

    private void stopVideoInternal() {
        queuedVideoFile = null;
        if (recorder == null && !recording && !recorderStartPending) return;
        // Enforce nothing by delay: stop() may throw if called too early (<700 ms
        // of data is the classic case); catch it and still clean up fully.
        long elapsed = recordStartMs > 0 ? SystemClock.elapsedRealtime() - recordStartMs : Long.MAX_VALUE;
        if (session != null) {
            try { session.stopRepeating(); } catch (Throwable ignored) { }
        }
        if (recorder != null) {
            if (recording) {
                try {
                    recorder.stop();
                } catch (RuntimeException re) {
                    if (elapsed < 700) {
                        try { Log.w(TAG, "recorder.stop() too early; discarding take"); } catch (Throwable ignored) { }
                    } else {
                        reportError("MediaRecorder stop failed: " + re.getMessage());
                    }
                } catch (Throwable t) {
                    reportError("MediaRecorder stop failed: " + t.getMessage());
                }
            }
        }
        releaseRecorder();
        recorderSurface = null;
        recording = false;
        recorderStartPending = false;
        recordStartMs = 0;
        if (camera != null) buildSession(false, false);
    }

    private void releaseRecorder() {
        if (recorder != null) {
            try { recorder.reset(); } catch (Throwable ignored) { }
            try { recorder.release(); } catch (Throwable ignored) { }
            recorder = null;
        }
    }

    private int displayRotationDegrees() {
        try {
            WindowManager wm = (WindowManager) appContext.getSystemService(Context.WINDOW_SERVICE);
            if (wm != null) {
                int rot = wm.getDefaultDisplay().getRotation();
                if (rot == Surface.ROTATION_90) return 90;
                if (rot == Surface.ROTATION_180) return 180;
                if (rot == Surface.ROTATION_270) return 270;
            }
        } catch (Throwable ignored) { }
        return 0;
    }

    private int computeOrientationHint() {
        int device = displayRotationDegrees();
        if (lensFacing == CameraCharacteristics.LENS_FACING_FRONT) {
            return (sensorOrientation + device) % 360;
        }
        return (sensorOrientation - device + 360) % 360;
    }

    // ------------------------------------------------------------------ photo

    private void takePhotoInternal(PhotoListener l) {
        if (recording || recorderStartPending) {
            reportError("takePhoto: photos are for between takes (recording in progress)");
            return;
        }
        if (camera == null) { reportError("takePhoto: camera not open"); return; }
        if (photoInProgress) { reportError("takePhoto: photo already in progress"); return; }
        pendingPhotoListener = l;
        photoInProgress = true;
        photoSessionActive = true;
        photoCaptureDone = false;
        photoImageDone = false;
        try {
            ensureJpegReader(generation);
        } catch (Throwable t) {
            reportError("JPEG reader failed: " + t.getMessage());
            pendingPhotoListener = null;
            photoInProgress = false;
            photoSessionActive = false;
            return;
        }
        buildSession(false, true);
    }

    private void doStillCapture() {
        if (session == null || camera == null || jpegReader == null) {
            reportError("takePhoto: session not ready");
            pendingPhotoListener = null;
            photoInProgress = false;
            photoSessionActive = false;
            closeJpegReader();
            buildSession(false, false);
            return;
        }
        try {
            CaptureRequest.Builder b = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE);
            b.addTarget(jpegReader.getSurface());
            b.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            b.set(CaptureRequest.CONTROL_AF_TRIGGER, CameraMetadata.CONTROL_AF_TRIGGER_START);
            try { b.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON); } catch (Throwable ignored) { }
            try { b.set(CaptureRequest.JPEG_ORIENTATION, computeOrientationHint()); } catch (Throwable ignored) { }
            applyZoom(b, currentZoom);
            session.capture(b.build(), new CameraCaptureSession.CaptureCallback() {
                @Override public void onCaptureCompleted(CameraCaptureSession s,
                                                           CaptureRequest request, TotalCaptureResult result) {
                    photoCaptureDone = true;
                    maybeFinishPhoto();
                }
                @Override public void onCaptureFailed(CameraCaptureSession s,
                                                        CaptureRequest request, CaptureFailure failure) {
                    reportError("Still capture failed: " + (failure != null ? failure.getReason() : -1));
                    pendingPhotoListener = null;
                    photoCaptureDone = true;
                    photoImageDone = true; // do not wait for an image that will not come
                    maybeFinishPhoto();
                }
            }, handler());
        } catch (Throwable t) {
            reportError("Still capture failed: " + t.getMessage());
            pendingPhotoListener = null;
            photoInProgress = false;
            photoSessionActive = false;
            closeJpegReader();
            buildSession(false, false);
        }
    }

    private void maybeFinishPhoto() {
        if (!photoInProgress) return;
        if (!photoCaptureDone || !photoImageDone) return;
        photoInProgress = false;
        photoSessionActive = false;
        closeJpegReader();
        if (camera != null) buildSession(recorderSurface != null, false);
    }

    // ---------------------------------------------------------------- cleanup

    private void closeCameraOnly() {
        try { stopVideoInternalSilent(); } catch (Throwable ignored) { }
        closeSessionOnly();
        closeYuvReader();
        closeJpegReader();
        pendingPhotoListener = null;
        photoInProgress = false;
        photoSessionActive = false;
        if (camera != null) {
            try { camera.close(); } catch (Throwable ignored) { }
            camera = null;
        }
        releasePreviewSurface();
        queuedVideoFile = null;
    }

    private void stopVideoInternalSilent() {
        if (recorder != null) {
            if (session != null) {
                try { session.stopRepeating(); } catch (Throwable ignored) { }
            }
            if (recording) {
                try { recorder.stop(); } catch (Throwable ignored) { }
            }
            releaseRecorder();
        }
        recorderSurface = null;
        recording = false;
        recorderStartPending = false;
        recordStartMs = 0;
    }

    private static void closeResources(CameraCaptureSession s, CameraDevice c,
                                       ImageReader y, ImageReader j,
                                       MediaRecorder r, Surface rs, Surface ps,
                                       boolean wasRecording) {
        if (s != null) {
            try { s.stopRepeating(); } catch (Throwable ignored) { }
            try { s.close(); } catch (Throwable ignored) { }
        }
        if (r != null) {
            if (wasRecording) {
                try { r.stop(); } catch (Throwable ignored) { }
            }
            try { r.reset(); } catch (Throwable ignored) { }
            try { r.release(); } catch (Throwable ignored) { }
        }
        if (y != null) { try { y.close(); } catch (Throwable ignored) { } }
        if (j != null) { try { j.close(); } catch (Throwable ignored) { } }
        if (c != null) { try { c.close(); } catch (Throwable ignored) { } }
        // recorderSurface is owned by MediaRecorder; do not release separately after release().
        if (ps != null) { try { ps.release(); } catch (Throwable ignored) { } }
    }
}
