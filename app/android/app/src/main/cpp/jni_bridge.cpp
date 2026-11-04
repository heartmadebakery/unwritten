#include <jni.h>

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "uwcore.h"

// ---------------------------------------------------------------------------
// WavRecorder
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jlong JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeStartWav(JNIEnv* env, jclass /*clazz*/,
                                                   jstring path) {
    try {
        if (env == nullptr || path == nullptr) {
            return 0;
        }
        const char* chars = env->GetStringUTFChars(path, nullptr);
        if (chars == nullptr) {
            return 0;
        }
        std::string pathStr(chars);
        env->ReleaseStringUTFChars(path, chars);

        auto* recorder = new uwcore::WavRecorder();
        if (!recorder->Start(pathStr)) {
            delete recorder;
            return 0;
        }
        return static_cast<jlong>(reinterpret_cast<intptr_t>(recorder));
    } catch (...) {
        return 0;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeStopWav(JNIEnv* /*env*/, jclass /*clazz*/,
                                                  jlong handle) {
    try {
        if (handle == 0) {
            return JNI_FALSE;
        }
        auto* recorder =
                reinterpret_cast<uwcore::WavRecorder*>(static_cast<intptr_t>(handle));
        const bool ok = recorder->Stop();
        delete recorder;
        return ok ? JNI_TRUE : JNI_FALSE;
    } catch (...) {
        return JNI_FALSE;
    }
}

extern "C" JNIEXPORT jdouble JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeWavRms(JNIEnv* /*env*/, jclass /*clazz*/,
                                                 jlong handle) {
    try {
        if (handle == 0) {
            return 0.0;
        }
        auto* recorder =
                reinterpret_cast<uwcore::WavRecorder*>(static_cast<intptr_t>(handle));
        return static_cast<jdouble>(recorder->GetRms());
    } catch (...) {
        return 0.0;
    }
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeWavDurationMs(JNIEnv* /*env*/,
                                                        jclass /*clazz*/,
                                                        jlong handle) {
    try {
        if (handle == 0) {
            return 0;
        }
        auto* recorder =
                reinterpret_cast<uwcore::WavRecorder*>(static_cast<intptr_t>(handle));
        return static_cast<jlong>(recorder->GetDurationMs());
    } catch (...) {
        return 0;
    }
}

// ---------------------------------------------------------------------------
// Luma
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeLuma(JNIEnv* env, jclass /*clazz*/,
                                               jbyteArray yPlane, jint width,
                                               jint height, jint rowStride) {
    try {
        jdoubleArray result = env->NewDoubleArray(65);
        if (result == nullptr) {
            return nullptr;
        }
        double out[65] = {0.0};
        if (env == nullptr || yPlane == nullptr || width <= 0 || height <= 0 ||
            rowStride < width) {
            env->SetDoubleArrayRegion(result, 0, 65, out);
            return result;
        }
        const jsize len = env->GetArrayLength(yPlane);
        if (len <= 0) {
            env->SetDoubleArrayRegion(result, 0, 65, out);
            return result;
        }
        std::vector<uint8_t> buffer(static_cast<size_t>(len));
        env->GetByteArrayRegion(yPlane, 0, len,
                                reinterpret_cast<jbyte*>(buffer.data()));
        if (env->ExceptionCheck()) {
            env->ExceptionClear();
            env->SetDoubleArrayRegion(result, 0, 65, out);
            return result;
        }
        double mean = 0.0;
        double grid[64] = {0.0};
        const size_t needed =
                static_cast<size_t>(rowStride) * static_cast<size_t>(height - 1) +
                static_cast<size_t>(width);
        if (buffer.size() < needed) {
            env->SetDoubleArrayRegion(result, 0, 65, out);
            return result;
        }
        uwcore::ComputeLumaStats(buffer.data(), static_cast<int>(width),
                                 static_cast<int>(height),
                                 static_cast<int>(rowStride), &mean, grid);
        out[0] = mean;
        for (int i = 0; i < 64; ++i) {
            out[1 + i] = grid[i];
        }
        env->SetDoubleArrayRegion(result, 0, 65, out);
        return result;
    } catch (...) {
        // Best effort: return zeroed array if we can.
        try {
            if (env != nullptr) {
                jdoubleArray result = env->NewDoubleArray(65);
                if (result != nullptr) {
                    double out[65] = {0.0};
                    env->SetDoubleArrayRegion(result, 0, 65, out);
                    return result;
                }
            }
        } catch (...) {
        }
        return nullptr;
    }
}

// ---------------------------------------------------------------------------
// FlashDetector
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jlong JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeFlashCreate(JNIEnv* /*env*/,
                                                      jclass /*clazz*/) {
    try {
        auto* detector = new uwcore::FlashDetector();
        return static_cast<jlong>(reinterpret_cast<intptr_t>(detector));
    } catch (...) {
        return 0;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeFlashFeed(JNIEnv* /*env*/,
                                                    jclass /*clazz*/,
                                                    jlong handle, jdouble mean,
                                                    jlong nowMs) {
    try {
        if (handle == 0) {
            return JNI_FALSE;
        }
        auto* detector = reinterpret_cast<uwcore::FlashDetector*>(
                static_cast<intptr_t>(handle));
        const bool fired = detector->Feed(static_cast<double>(mean),
                                          static_cast<int64_t>(nowMs));
        return fired ? JNI_TRUE : JNI_FALSE;
    } catch (...) {
        return JNI_FALSE;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_heartmadebakery_unwritten_NativeCore_nativeFlashDestroy(JNIEnv* /*env*/,
                                                       jclass /*clazz*/,
                                                       jlong handle) {
    try {
        if (handle == 0) {
            return;
        }
        auto* detector = reinterpret_cast<uwcore::FlashDetector*>(
                static_cast<intptr_t>(handle));
        delete detector;
    } catch (...) {
        // Never throw across JNI.
    }
}
