// SafeMode.m — disable Instagram's crash-loop safe mode.
//
// IGSafeModeChecker (verified in 442.0.0) resets user defaults and can
// disable tweak features after repeated crashes. Killing the checker and
// zeroing the crash count keeps the app from ever entering that state.
#import "IGModHook.h"

void IGSafeModeInit(void) {
    if (!igEnabled(kIGDisableSafeMode)) return;
    Class cls = NSClassFromString(@"IGSafeModeChecker");
    if (!cls) return;

    __block IMP origInit = NULL;
    origInit = igHookInstance(cls, @selector(initWithInstacrashCounterProvider:crashThreshold:),
        ^id(id self, id provider, unsigned long long threshold) {
            (void)self; (void)provider; (void)threshold;
            return nil;
        });
    __block IMP origCount = NULL;
    origCount = igHookInstance(cls, @selector(crashCount),
        ^unsigned long long(id self) {
            if (igEnabled(kIGDisableSafeMode)) return 0;
            return origCount ? ((unsigned long long (*)(id, SEL))origCount)(self, @selector(crashCount)) : 0;
        });
}
