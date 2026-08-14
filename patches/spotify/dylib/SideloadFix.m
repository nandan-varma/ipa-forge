// SideloadFix.m — minimal sideload shim: app-group container fallback only.
//
// v5: the fishhook SecItem access-group rebind and CloudKit neuter are
// REMOVED — they were the only C-level memory-touching code in the dylib and
// are the prime crash suspect (a segfault there isn't caught by @try, and
// they were present in every crashing build). Pure ObjC-runtime swizzling
// only, matching the proven minimal-test dylib.
//
// The app-group hook is defensive: containerURLForSecurityApplicationGroup-
// Identifier: returns a sandboxed path instead of nil when the re-signed app
// has no real app-groups entitlement (Spotify crashes inside hasPrefix: of a
// nil container).

#import "SpotifyHook.h"
#import <Foundation/Foundation.h>

static void fixAppGroupContainer(void) {
    static IMP orig_containerURL;
    orig_containerURL = sptHookInstance([NSFileManager class],
        @selector(containerURLForSecurityApplicationGroupIdentifier:),
        ^id(id self, NSString *groupIdentifier) {
            if (groupIdentifier != nil) {
                NSArray *paths = [[NSFileManager defaultManager]
                    URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
                NSURL *documentsURL = [paths lastObject];
                NSURL *dir = [documentsURL URLByAppendingPathComponent:@"AppGroup"];
                [[NSFileManager defaultManager] createDirectoryAtURL:dir
                                          withIntermediateDirectories:YES attributes:nil error:nil];
                return dir;
            }
            return ((id(*)(id, SEL, id))orig_containerURL)(
                self, @selector(containerURLForSecurityApplicationGroupIdentifier:), groupIdentifier);
        });
    (void)orig_containerURL;
}

void SpotifySideloadFixInit(void) {
    if (!smEnabled(kSMAppGroup)) { os_log(spotLog(), "SpotifyMod: app-group fix disabled"); return; }
    fixAppGroupContainer();
}
