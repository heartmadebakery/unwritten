package com.heartmadebakery.unwritten;

public final class NativeCore {

    static {
        System.loadLibrary("uwcore");
    }

    private NativeCore() {
    }

    public static native long nativeStartWav(String path);

    public static native boolean nativeStopWav(long handle);

    public static native double nativeWavRms(long handle);

    public static native long nativeWavDurationMs(long handle);

    public static native double[] nativeLuma(byte[] yPlane, int width, int height, int rowStride);

    public static native long nativeFlashCreate();

    public static native boolean nativeFlashFeed(long handle, double mean, long nowMs);

    public static native void nativeFlashDestroy(long handle);
}
