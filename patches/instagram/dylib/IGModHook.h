// IGModHook.h — shared header for the Instagram mod dylib (plain ObjC-runtime
// swizzling, no substrate, no Logos, no Swift). Loaded via LC_LOAD_DYLIB; the
// constructor runs after the ObjC runtime has mapped all images.
//
// Every hook target in this file's feature files was verified present in the
// Instagram 442.0.0 binary (main executable) with `forge hooks extract` /
// `forge hooks verify` before being ported. The SCInsta/BHInstagram lineage
// targets ~418.x; the drift to 442.0.0 is documented in SOURCES.md.
#ifndef IGMODHOOK_H
#define IGMODHOOK_H

#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <os/log.h>
#import <UIKit/UIKit.h>

// Mod version — shown in the settings About row and matched against the IPA
// file name (IGMod_<version>.ipa). Bump together with the IPA on each pass.
#define IGMOD_VERSION "0.0.1"

static inline os_log_t igLog(void) {
    static os_log_t log;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        log = os_log_create("com.nandan.igmod", "hook");
    });
    return log;
}

// Replace an instance method's IMP with a block IMP; returns the original.
// No-op (NULL) when the class/method is absent — safe against version drift.
static inline IMP igHookInstance(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        os_log(igLog(), "IGMod: inst %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel, imp_implementationWithBlock(block), method_getTypeEncoding(m));
    os_log(igLog(), "IGMod: hooked -[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

static inline IMP igHookClass(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getClassMethod(cls, sel);
    if (!m) {
        os_log(igLog(), "IGMod: class %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(object_getClass(cls), sel, imp_implementationWithBlock(block),
                        method_getTypeEncoding(m));
    os_log(igLog(), "IGMod: hooked +[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

// Feature init entry points (one per feature file).
void IGAdBlockInit(void);
void IGStoryPrivacyInit(void);
void IGMediaDownloadInit(void);
void IGCopyTextInit(void);
void IGSafeModeInit(void);
void IGSettingsInit(void);

// --- settings keys ----------------------------------------------------------
// Canonical key spellings. Every key is declared exactly once, here, and
// referenced by the defaults registration (IGModHook.m), the settings UI
// (SettingsUI.m) and the feature hooks. Never write a key string inline
// anywhere else.
#define kIGHideAds              @"IGModHideAds"
#define kIGHideStoryTray        @"IGModHideStoryTray"
#define kIGNoSuggestedPosts     @"IGModNoSuggestedPosts"
#define kIGNoSuggestedReels     @"IGModNoSuggestedReels"
#define kIGNoSuggestedAccounts  @"IGModNoSuggestedAccounts"
#define kIGNoStorySeen          @"IGModNoStorySeen"
#define kIGNoTypingStatus       @"IGModNoTypingStatus"
#define kIGNoScreenshotAlerts   @"IGModNoScreenshotAlerts"
#define kIGFeedDownload         @"IGModFeedDownload"
#define kIGStoryDownload        @"IGModStoryDownload"
#define kIGProfilePicDownload   @"IGModProfilePicDownload"
#define kIGCopyCaptions         @"IGModCopyCaptions"
#define kIGDisableSafeMode      @"IGModDisableSafeMode"
#define kIGSettingsShortcut     @"IGModSettingsShortcut"   // long-press home tab
#define kIGSettingsFourFinger   @"IGModSettingsFourFinger" // 4-finger hold anywhere

// Read a switch key; defaults to ON when unset (registration happens at
// launch from the defaults list, so "unset" only occurs pre-launch).
static inline BOOL igEnabled(NSString *key) {
    NSNumber *v = [[NSUserDefaults standardUserDefaults] objectForKey:key];
    return v ? [v boolValue] : YES;
}

// --- helpers shared by the feature files ------------------------------------

// Call a selector returning id on an object without compile-time linkage to
// Instagram classes (plain ObjC-runtime: the dylib never imports app headers).
static inline id igObj(id object, SEL sel) {
    if (!object || ![object respondsToSelector:sel]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(object, sel);
}

// Call a selector returning BOOL on an object; NO when it can't be called.
static inline BOOL igBool(id object, SEL sel) {
    if (!object || ![object respondsToSelector:sel]) return NO;
    return ((BOOL (*)(id, SEL))objc_msgSend)(object, sel);
}

// The top-most presented view controller of the app.
UIViewController *igTopMostViewController(void);

// Non-blocking toast with an activity spinner ("Saving media…").
void igShowToast(NSString *message);

// Download a remote URL to a temp file, then present the share sheet with
// the local file so Save Image / Save Video work reliably.
void igShareRemoteURL(NSURL *url, NSString *toastMessage);

#endif
