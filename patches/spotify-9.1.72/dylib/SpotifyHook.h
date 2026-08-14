// SpotifyHook.h — shared header for the Spotify mod dylib (plain ObjC-runtime
// swizzling, no substrate, no Swift). Loaded via LC_LOAD_DYLIB; the
// constructor runs after the ObjC runtime has mapped all images.
#ifndef SPOTIFYHOOK_H
#define SPOTIFYHOOK_H

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <os/log.h>

static inline os_log_t spotLog(void) {
    static os_log_t log;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        log = os_log_create("com.nandan.spotifymod", "hook");
    });
    return log;
}

// Replace an instance method's IMP with a block IMP; returns the original.
// No-op (NULL) when the class/method is absent — safe against version drift.
static inline IMP sptHookInstance(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        os_log(spotLog(), "SpotifyMod: inst %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel, imp_implementationWithBlock(block), method_getTypeEncoding(m));
    os_log(spotLog(), "SpotifyMod: hooked -[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

static inline IMP sptHookClass(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getClassMethod(cls, sel);
    if (!m) {
        os_log(spotLog(), "SpotifyMod: class %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(object_getClass(cls), sel, imp_implementationWithBlock(block),
                        method_getTypeEncoding(m));
    os_log(spotLog(), "SpotifyMod: hooked +[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

void SpotifySideloadFixInit(void);
void SpotifySessionProtectionInit(void);
void SpotifyPremiumPatchInit(void);
void SpotifyAdBlockInit(void);

#endif
