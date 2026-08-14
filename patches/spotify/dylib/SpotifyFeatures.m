// SpotifyFeatures.m - the SpotifyMod feature catalog. SINGLE SOURCE OF TRUTH.
//
// Every setting the dylib exposes is declared exactly once, here. The table
// drives:
//   1. NSUserDefaults registration  (SpotifyHook.m registerDefaults:)
//   2. The in-app settings screen   (SettingsUI.m: sections, rows, kinds,
//                                    restart hints)
// Hooks read the same keys via smEnabled(<key>) / smIntVal(<key>) using the
// kSM* macros from SpotifyHook.h - the macro is the single canonical key
// spelling, and SMFeatureSpec.choices is the single canonical definition of
// a choice's stored values.
//
// Adding a feature: add one row here (title/detail/group/kind/default/
// restart), then implement its hooks. Removing a feature: delete the row and
// its hooks. Not-yet-implemented features stay here as SMFeatureDisabled
// rows - they render greyed out in the Future section and are never read.
//
// Group order in kGroups = section order in the settings screen. Frequently
// used settings ("essentials") come first; rarely-changed settings live in
// "advanced" at the bottom so they stay out of the way. Row order inside a
// group = catalog order here.
//
// Binary truth: every selector/identifier the dylib hooks is verified against
// com.spotify.client 9.1.72 (forge hooks verify + strings; see README.md).

#import "SpotifyHook.h"

@implementation SMFeatureSpec
+ (instancetype)switchSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                    group:(NSString *)group defaultValue:(BOOL)dv restart:(BOOL)restart {
    SMFeatureSpec *s = [self new];
    s.key = key; s.title = title; s.detail = detail; s.group = group;
    s.kind = SMFeatureSwitch; s.defaultValue = dv; s.restartRequired = restart;
    return s;
}
+ (instancetype)choiceSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                    group:(NSString *)group defaultValue:(NSInteger)dv
                  choices:(NSArray<NSArray *> *)choices restart:(BOOL)restart {
    SMFeatureSpec *s = [self new];
    s.key = key; s.title = title; s.detail = detail; s.group = group;
    s.kind = SMFeatureChoice; s.choiceDefault = dv; s.choices = choices;
    s.restartRequired = restart;
    return s;
}
+ (instancetype)disabledSpec:(NSString *)title detail:(NSString *)detail group:(NSString *)group {
    SMFeatureSpec *s = [self new];
    s.key = nil; s.title = title; s.detail = detail; s.group = group;
    s.kind = SMFeatureDisabled; s.restartRequired = NO;
    return s;
}
@end

@implementation SMGroupSpec
+ (instancetype)group:(NSString *)g title:(NSString *)title detail:(NSString *)detail {
    SMGroupSpec *s = [self new];
    s.group = g; s.title = title; s.detail = detail;
    return s;
}
@end

// --- Groups (order = settings-screen section order) --------------------------
static NSArray<SMGroupSpec *> *kGroups(void) {
    static NSArray *groups;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        groups = @[
            [SMGroupSpec group:@"essentials" title:@"Essentials"
                        detail:@"The core mod features. Changes apply on relaunch."],
            [SMGroupSpec group:@"interface" title:@"Interface"
                        detail:@"Bottom-bar appearance - opt-in, changes apply on relaunch."],
            [SMGroupSpec group:@"advanced" title:@"Advanced"
                        detail:@"Rarely changed - only touch these when something misbehaves."],
            [SMGroupSpec group:@"future" title:@"Future"
                        detail:@"Not yet implemented - kept here as a roadmap. Disabled by design."],
        ];
    });
    return groups;
}

// --- The catalog. Order within a group = settings-row order. ----------------
static NSArray<SMFeatureSpec *> *kFeatures(void) {
    static NSArray *features;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        features = @[
            // ---- Essentials (what a regular user touches) ----
            [SMFeatureSpec switchSpec:kSMPremium title:@"Premium unlock"
                              detail:@"Unlimited skips, on-demand playback, high quality"
                               group:@"essentials" defaultValue:YES restart:YES],
            [SMFeatureSpec switchSpec:kSMAdBlock title:@"Ad blocker"
                              detail:@"Hides ad cards and stops ad delivery"
                               group:@"essentials" defaultValue:YES restart:YES],
            [SMFeatureSpec switchSpec:kSMSession title:@"Session protection"
                              detail:@"Stops forced logout and account resets"
                               group:@"essentials" defaultValue:YES restart:YES],

            // ---- Interface (bottom bar - opt-in) ----
            [SMFeatureSpec switchSpec:kSMHideExtraTabs title:@"Hide Premium & Create tabs"
                              detail:@"Remove the Premium upsell and Create (+) tabs from the bottom bar"
                               group:@"interface" defaultValue:NO restart:YES],

            // ---- Advanced (rarely changed) ----
            [SMFeatureSpec switchSpec:kSMAppGroup title:@"App-group fix"
                              detail:@"Container fallback for re-signed installs"
                               group:@"advanced" defaultValue:YES restart:YES],
            [SMFeatureSpec choiceSpec:kSMAdBlockMode title:@"Ad blocking strength"
                              detail:@"Aggressive also stops free-tier re-fetch"
                               group:@"advanced" defaultValue:1
                              choices:@[ @[@"Standard", @0], @[@"Aggressive", @1] ]
                              restart:YES],

            // ---- Future (not implemented - disabled rows) ----
            [SMFeatureSpec disabledSpec:@"Downloads unlock"
                                detail:@"Offline downloads for any account" group:@"future"],
            [SMFeatureSpec disabledSpec:@"Audio quality selector"
                                detail:@"Force Very High streaming" group:@"future"],
            [SMFeatureSpec disabledSpec:@"Startup tab"
                                detail:@"Choose Home / Search / Library on launch" group:@"future"],
            [SMFeatureSpec disabledSpec:@"Settings import / export"
                                detail:@"Back up and restore your mod settings" group:@"future"],
        ];
    });
    return features;
}

NSArray<SMFeatureSpec *> *smFeatureSpecs(void) { return kFeatures(); }
NSArray<SMGroupSpec *> *smGroupSpecs(void) { return kGroups(); }

NSArray<SMFeatureSpec *> *smFeaturesInGroup(NSString *group) {
    NSMutableArray *result = [NSMutableArray array];
    for (SMFeatureSpec *spec in kFeatures())
        if ([spec.group isEqualToString:group]) [result addObject:spec];
    return result;
}

SMFeatureSpec *smFeatureForKey(NSString *key) {
    for (SMFeatureSpec *spec in kFeatures())
        if (spec.key && [spec.key isEqualToString:key]) return spec;
    return nil;
}
