// SessionProtection.m — stop Spotify from detecting and logging out the
// non-premium account, and block the network calls that drive it. Ported
// from-scratch: blocks forced logout and the network calls that drive it
// targets, verified present in the 9.1.72 binary.

#import "SpotifyHook.h"
#import <UIKit/UIKit.h>

static const NSTimeInterval kStartupGrace = 30.0; // allow fresh login/signup
static NSTimeInterval bootTime(void) {
    static NSTimeInterval t;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ t = [NSDate timeIntervalSinceReferenceDate]; });
    return t;
}

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

static BOOL spotShouldBlockURL(NSURL *url) {
    NSString *path = url.path.lowercaseString ?: @"";
    NSString *host = url.host.lowercaseString ?: @"";

    // Always block explicit session destroy / token delete.
    if ([path containsString:@"DeleteToken"]
        || [path containsString:@"token/revoke"]
        || [path containsString:@"session/purge"]
        || [path containsString:@"logout"]
        || [path containsString:@"sign-out"]
        || [path containsString:@"auth/expire"]) {
        return YES;
    }

    // Ad-delivery endpoints (Ad on App Open banner, /ads/*, ad-logic, DAC,
    // Esperanto slots, sponsored/promoted/upsell/campaign paths...).
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

    // After the startup grace window, block the re-fetch/ad-support endpoints
    // that would re-enable free-tier behavior or log the session out.
    if ([NSDate timeIntervalSinceReferenceDate] - bootTime() > kStartupGrace) {
        if ([path containsString:@"signup/public"]
            || [path containsString:@"apresolve"]
            || [path containsString:@"pses/screenconfig"]
            || [path containsString:@"bootstrap/v1/bootstrap"]
            || [path containsString:@"v1/customize"]
            || [path containsString:@"trials-facade/start-trial"]
            || [path containsString:@"premium-marketing/upsellOffer"]
            || [path containsString:@"select-ondemand-set"]) {
            return YES;
        }
    }
    (void)host;
    return NO;
}

static void fixURLSessionTaskResume(void) {
    static IMP orig_resume;
    orig_resume = sptHookInstance(NSClassFromString(@"NSURLSessionTask"),
        @selector(resume),
        ^void(id self) {
            NSURLSessionTask *task = self;
            NSURL *url = task.currentRequest.URL ?: task.originalRequest.URL;
            if (url && spotShouldBlockURL(url)) {
                os_log(spotLog(), "SpotifyMod: cancelled %@", url.absoluteString);
                [task cancel];
                return;
            }
            ((void(*)(id, SEL))orig_resume)(self, @selector(resume));
        });
    (void)orig_resume;
}

void SpotifySessionProtectionInit(void) {
    if (!smEnabled(kSMSession)) { os_log(spotLog(), "SpotifyMod: session protection disabled"); return; }
    fixAuthSession();
    fixLegacyLogin();
    fixURLSessionTaskResume();
}
