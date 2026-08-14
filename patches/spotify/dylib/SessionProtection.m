// SessionProtection.m — stop Spotify from detecting and logging out the
// non-premium account, and block the network calls that drive it. Ported
// from-scratch: blocks forced logout and the network calls that drive it
// targets, verified present in the 9.1.72 binary.
//
// URL blocking is split into three tiers so each settings toggle owns
// exactly the behavior its name promises (values come from the feature
// catalog in SpotifyFeatures.m — the single source of truth):
//   tier 1  forced-logout calls      -> kSMSession (Session protection)
//   tier 2  ad-delivery endpoints    -> kSMAdBlock (Ad blocker)
//   tier 3  free-tier re-fetch       -> kSMAdBlock + kSMAdBlockMode==Aggressive
//
// The aggressive tier (3) waits out a startup grace so a fresh login/signup
// is never disturbed.

#import "SpotifyHook.h"
#import <UIKit/UIKit.h>

static const NSTimeInterval kStartupGrace = 30.0; // allow fresh login/signup
static NSTimeInterval bootTime(void) {
    static NSTimeInterval t;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ t = [NSDate timeIntervalSinceReferenceDate]; });
    return t;
}

// Ad blocking strength — stored values are catalog-defined (see
// kSMAdBlockMode choices in SpotifyFeatures.m).
typedef NS_ENUM(NSInteger, SMAdBlockStrength) { SMAdBlockStandard = 0, SMAdBlockAggressive = 1 };

// --- SPTAuthSessionImplementation -------------------------------------------

static void fixAuthSession(void) {
    Class cls = NSClassFromString(@"SPTAuthSessionImplementation");
    NSArray<NSString *> *blocked = @[
        @"logout",
        @"logoutWithReason:",
        @"callSessionDidLogoutOnDelegateWithReason:",
        @"logWillLogoutEventWithLogoutReason:",
        @"destroy",
    ];
    for (NSString *selName in blocked) {
        SEL sel = NSSelectorFromString(selName);
        Method m = class_getInstanceMethod(cls, sel);
        if (!m) continue;
        class_replaceMethod(cls, sel,
            imp_implementationWithBlock(^void(id self) {
                os_log(spotLog(), "SpotifyMod: blocked %@ on %s", selName, class_getName(cls));
            }),
            method_getTypeEncoding(m));
    }
}

// --- SPTAuthLegacyLoginControllerImplementation -----------------------------

static void fixLegacyLogin(void) {
    Class cls = NSClassFromString(@"SPTAuthLegacyLoginControllerImplementation");
    NSArray<NSString *> *blocked = @[
        @"sessionDidLogout:withReason:",
        @"destroySession",
        @"forgetStoredCredentials",
        @"invalidate",
    ];
    for (NSString *selName in blocked) {
        SEL sel = NSSelectorFromString(selName);
        Method m = class_getInstanceMethod(cls, sel);
        if (!m) continue;
        class_replaceMethod(cls, sel,
            imp_implementationWithBlock(^void(id self) {
                os_log(spotLog(), "SpotifyMod: blocked %@ on %s", selName, class_getName(cls));
            }),
            method_getTypeEncoding(m));
    }
}

// --- NSURLSessionTask.resume: block logout/ad-driver requests ----------------
// Tiers are evaluated in the resume hook; each tier is gated on its owning
// setting (see the header comment).

// Tier 1: explicit session destroy / token delete (forced logout).
static BOOL spotShouldBlockLogout(NSURL *url) {
    NSString *path = url.path.lowercaseString ?: @"";
    return [path containsString:@"DeleteToken"]
        || [path containsString:@"token/revoke"]
        || [path containsString:@"session/purge"]
        || [path containsString:@"logout"]
        || [path containsString:@"sign-out"]
        || [path containsString:@"auth/expire"];
}

// Tier 2: ad-delivery endpoints (Ad on App Open banner, /ads/*, ad-logic,
// DAC, Esperanto slots, sponsored/promoted/upsell/campaign paths...).
static BOOL spotShouldBlockAdDelivery(NSURL *url) {
    NSString *path = url.path.lowercaseString ?: @"";
    NSString *host = url.host.lowercaseString ?: @"";
    if ([path containsString:@"/ad-on-app-open"]
        || [path containsString:@"/ads/"]
        || [path containsString:@"/ad-logic/"]
        || [path containsString:@"/dac/view/v1/"]
        || ([path containsString:@"/esperanto/"] && ([path containsString:@"ad"] || [path containsString:@"slot"]))
        || [path containsString:@"/ad-slot/"]
        || [path containsString:@"/ad-inventory/"]
        || [path containsString:@"/sponsored/"]
        || [path containsString:@"/promoted/"]
        || [path containsString:@"/upsell/"]
        || [path containsString:@"/campaign/"]
        || [path containsString:@"/billboard/"]
        || [path containsString:@"/banner/"]
        || [path containsString:@"/interstitial/"]
        || [path containsString:@"/marquee/"]
        || [path containsString:@"/leavebehind/"]
        || [path containsString:@"/display-ad/"]
        || [path containsString:@"/fullbleed/"]
        || [path containsString:@"/sponsored-shelf/"]
        || [path containsString:@"/native-ad/"]
        || [path containsString:@"/home-ads/"]
        || [path containsString:@"/search-ads/"]) {
        return YES;
    }
    if ([host containsString:@"doubleclick"] || [host containsString:@"googlesyndication"]
        || [host hasPrefix:@"aet."] || [host hasSuffix:@".aet.spotify.com"]) {
        return YES;
    }
    return NO;
}

// Tier 3: free-tier re-fetch / re-assertion (only in Aggressive mode, after
// the startup grace). Blocking these stops the server from re-enabling
// free-tier behavior mid-session.
static BOOL spotShouldBlockRefetch(NSURL *url) {
    NSString *path = url.path.lowercaseString ?: @"";
    return [path containsString:@"signup/public"]
        || [path containsString:@"apresolve"]
        || [path containsString:@"pses/screenconfig"]
        || [path containsString:@"bootstrap/v1/bootstrap"]
        || [path containsString:@"v1/customize"]
        || [path containsString:@"trials-facade/start-trial"]
        || [path containsString:@"premium-marketing/upsellOffer"]
        || [path containsString:@"select-ondemand-set"];
}

static void fixURLSessionTaskResume(void) {
    static IMP orig_resume;
    orig_resume = sptHookInstance(NSClassFromString(@"NSURLSessionTask"),
        @selector(resume),
        ^void(id self) {
            NSURLSessionTask *task = self;
            NSURL *url = task.currentRequest.URL ?: task.originalRequest.URL;
            BOOL sessionOn = smEnabled(kSMSession);
            BOOL adBlockOn = smEnabled(kSMAdBlock);
            if (url) {
                if (sessionOn && spotShouldBlockLogout(url)) {
                    os_log(spotLog(), "SpotifyMod: blocked logout %@", url.absoluteString);
                    [task cancel];
                    return;
                }
                if (adBlockOn && spotShouldBlockAdDelivery(url)) {
                    os_log(spotLog(), "SpotifyMod: cancelled ad %@", url.absoluteString);
                    [task cancel];
                    return;
                }
                if (adBlockOn
                    && smIntVal(kSMAdBlockMode) == SMAdBlockAggressive
                    && [NSDate timeIntervalSinceReferenceDate] - bootTime() > kStartupGrace
                    && spotShouldBlockRefetch(url)) {
                    os_log(spotLog(), "SpotifyMod: cancelled refetch %@", url.absoluteString);
                    [task cancel];
                    return;
                }
            }
            ((void(*)(id, SEL))orig_resume)(self, @selector(resume));
        });
    (void)orig_resume;
}

void SpotifySessionProtectionInit(void) {
    if (!smEnabled(kSMSession) && !smEnabled(kSMAdBlock)) {
        os_log(spotLog(), "SpotifyMod: session protection + ad blocking disabled");
        return;
    }
    if (smEnabled(kSMSession)) {
        fixAuthSession();
        fixLegacyLogin();
    }
    if (smEnabled(kSMSession) || smEnabled(kSMAdBlock)) {
        fixURLSessionTaskResume(); // tiers consult their own toggles per call
    }
}
