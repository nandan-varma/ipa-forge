// libYTHook.m — YouTube 21.32.4 ad-removal hook dylib (from scratch).
//
// Targets were located by static analysis of the 21.32.4 binary
// (objc_classlist/methlist walk; see the yt_inventory tooling):
//   - YTAdBreakResponseReceivedOpportunityAdapterV2
//       didReceiveAdBreakResponse:fromAdBreakSlot:
//       (modern "ads control flow v2" entry point where an ad-break
//        response is turned into scheduled ad slots)
//   - YTAdBreakRendererAdapter createAds
//       (classic renderer path that materializes the ad list for a break)
//
// Both swizzles are conservative: the response flow still runs, the break
// still resolves, it just contains no ads. No substrate/ellekit dependency —
// plain ObjC runtime swizzling, so this loads via a plain LC_LOAD_DYLIB.

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <os/log.h>

static os_log_t ytlog(void) {
    static os_log_t log;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        log = os_log_create("com.nandan.ytfreedom", "hook");
    });
    return log;
}

static void swizzleVoid(id self, id arg1, id arg2) {
    // do nothing: drop the ad-break response. Break resolves empty.
    os_log(ytlog(), "YTFreedom: dropped ad-break response (%@, slot=%@)",
           arg1, arg2);
}

static id swizzleCreateAds(id self) {
    os_log(ytlog(), "YTFreedom: createAds -> empty");
    return @[];
}

static void installHook(Class cls, SEL selector, IMP newImpl) {
    if (!cls) {
        os_log(ytlog(), "YTFreedom: class not found for %s",
               sel_getName(selector));
        return;
    }
    Method m = class_getInstanceMethod(cls, selector);
    if (!m) {
        os_log(ytlog(), "YTFreedom: method %s not found on %s",
               sel_getName(selector), class_getName(cls));
        return;
    }
    class_replaceMethod(cls, selector, newImpl,
                        method_getTypeEncoding(m));
    os_log(ytlog(), "YTFreedom: hooked %s %s",
           class_getName(cls), sel_getName(selector));
}

__attribute__((constructor))
static void ytfreedom_init(void) {
    installHook(objc_getClass("YTAdBreakResponseReceivedOpportunityAdapterV2"),
                sel_registerName("didReceiveAdBreakResponse:fromAdBreakSlot:"),
                imp_implementationWithBlock(^(id self, id response, id slot) {
                    swizzleVoid(self, response, slot);
                }));

    installHook(objc_getClass("YTAdBreakRendererAdapter"),
                sel_registerName("createAds"),
                imp_implementationWithBlock(^(id self) {
                    return swizzleCreateAds(self);
                }));
}
