// SpotifyHook.h — shared header for the Spotify mod dylib (plain ObjC-runtime
// swizzling, no substrate, no Swift). Loaded via LC_LOAD_DYLIB; the
// constructor runs after the ObjC runtime has mapped all images.
#ifndef SPOTIFYHOOK_H
#define SPOTIFYHOOK_H

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <os/log.h>

// Mod version — shown in Settings → About and matched against the IPA file
// name (SpotifyMod_v<version>.ipa). Bump together with the IPA on each pass.
#define SPOTIFYMOD_VERSION "0.0.9"

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
void SpotifyTabBarFixInit(void);
void SpotifySettingsInit(void);

// --- settings keys ----------------------------------------------------------
// The canonical key spellings. Every key is declared exactly once, here, and
// referenced by the feature catalog (SpotifyFeatures.m — the single source
// of truth), the settings UI (SettingsUI.m) and the hooks. Never write a key
// string inline anywhere else.
#define kSMPremium     @"SpotifyModPremium"
#define kSMAdBlock     @"SpotifyModAdBlock"
#define kSMSession     @"SpotifyModSessionProtection"
#define kSMAppGroup    @"SpotifyModAppGroup"
#define kSMAdBlockMode @"SpotifyModAdBlockMode" // 0 = Standard, 1 = Aggressive
#define kSMHideExtraTabs @"SpotifyModHideExtraTabs" // hides Premium + Create bottom-bar tabs

// Read a switch key; defaults to ON when unset (registration happens at
// launch from the catalog defaults, so "unset" only occurs pre-launch).
static inline BOOL smEnabled(NSString *key) {
    NSNumber *v = [[NSUserDefaults standardUserDefaults] objectForKey:key];
    return v ? [v boolValue] : YES;
}

// Read a choice key as an integer (values are catalog-defined, see
// SMFeatureSpec.choices in SpotifyFeatures.m).
static inline NSInteger smIntVal(NSString *key) {
    NSNumber *v = [[NSUserDefaults standardUserDefaults] objectForKey:key];
    return v ? [v integerValue] : 0;
}

// --- feature catalog (single source of truth) -------------------------------
// The catalog in SpotifyFeatures.m declares every setting exactly once.
// Those declarations drive NSUserDefaults registration (SpotifyHook.m),
// the settings screen (SettingsUI.m) and the restart hints. Kinds:
//   SMFeatureSwitch   — on/off toggle (smEnabled)
//   SMFeatureChoice   — pick one value from a list (smIntVal); the choice
//                       {title, value} pairs live on the spec, here, so the
//                       stored values are defined in exactly one place
//   SMFeatureDisabled — not yet implemented; rendered greyed out in the
//                       Future section and never read by any hook
typedef NS_ENUM(NSInteger, SMFeatureKind) {
    SMFeatureSwitch,
    SMFeatureChoice,
    SMFeatureDisabled,
};

@interface SMFeatureSpec : NSObject
@property (nonatomic, copy) NSString *key;
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSString *detail;
@property (nonatomic, copy) NSString *group;       // group id, see smGroupSpecs()
@property (nonatomic) SMFeatureKind kind;
@property (nonatomic) BOOL defaultValue;           // SMFeatureSwitch
@property (nonatomic) NSInteger choiceDefault;     // SMFeatureChoice
@property (nonatomic, strong) NSArray<NSArray *> *choices; // SMFeatureChoice: {title, value} pairs
@property (nonatomic) BOOL restartRequired;        // needs relaunch to take effect

+ (instancetype)switchSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                    group:(NSString *)group defaultValue:(BOOL)dv restart:(BOOL)restart;
+ (instancetype)choiceSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                    group:(NSString *)group defaultValue:(NSInteger)dv
                  choices:(NSArray<NSArray *> *)choices restart:(BOOL)restart;
+ (instancetype)disabledSpec:(NSString *)title detail:(NSString *)detail group:(NSString *)group;
@end

@interface SMGroupSpec : NSObject
@property (nonatomic, copy) NSString *group;
@property (nonatomic, copy) NSString *title;       // section header
@property (nonatomic, copy) NSString *detail;      // section footer
+ (instancetype)group:(NSString *)g title:(NSString *)title detail:(NSString *)detail;
@end

// Catalog accessors — order of smGroupSpecs() = section order in the UI;
// order of smFeaturesInGroup() = row order within a section.
NSArray<SMFeatureSpec *> *smFeatureSpecs(void);
NSArray<SMGroupSpec *> *smGroupSpecs(void);
NSArray<SMFeatureSpec *> *smFeaturesInGroup(NSString *group);
SMFeatureSpec *smFeatureForKey(NSString *key);

#endif
