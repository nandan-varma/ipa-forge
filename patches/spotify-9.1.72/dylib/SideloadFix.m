// SideloadFix.m — sideload compat shim, ported from EeveeSpotify's
// zxPluginsInject (GPL). Plain-ObjC equivalent of the YouTube set's
// SignInFix: makes a re-signed (AltStore) Spotify behave like the original.
//
//  1. SecItem* rebind — Spotify hard-codes its entitled keychain access
//     group (e.g. "<TEAMID>.com.spotify.client.X"); after resigning with a
//     different team that group is invalid and every keychain query fails.
//     fishhook rebinds SecItemCopyMatching/Add/Update/Delete to rewrite the
//     kSecAttrAccessGroup to the group the current profile actually has.
//  2. App-group container URL never nil — without a real app-groups
//     entitlement, containerURLForSecurityApplicationGroupIdentifier: returns
//     nil and Spotify crashes inside `hasPrefix:` of the result. Fall back to
//     a sandboxed path instead.
//  3. CloudKit neutered — no iCloud entitlements on a free sideload account;
//     CKContainer/CKEntitlements lookups would assert. Return nil / strip.

#import "SpotifyHook.h"
#import <Security/Security.h>
#import <objc/message.h>
#import "fishhook.h"

static NSString *spotAccessGroupID(void) {
    NSDictionary *query = @{
        (__bridge NSString *)kSecClass: (__bridge NSString *)kSecClassGenericPassword,
        (__bridge NSString *)kSecAttrAccount: @"bundleSeedID",
        (__bridge NSString *)kSecAttrService: @"",
        (__bridge NSString *)kSecReturnAttributes: @YES,
    };
    CFTypeRef result = NULL;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
    if (status == errSecItemNotFound) {
        status = SecItemAdd((__bridge CFDictionaryRef)query, &result);
        if (status != errSecSuccess) return nil;
    }
    NSDictionary *attrs = (__bridge_transfer NSDictionary *)result;
    return attrs[(__bridge NSString *)kSecAttrAccessGroup];
}

// --- SecItem rebind --------------------------------------------------------

static OSStatus (*orig_SecItemCopyMatching)(CFDictionaryRef, CFTypeRef *);
static OSStatus (*orig_SecItemAdd)(CFDictionaryRef, CFTypeRef *);
static OSStatus (*orig_SecItemUpdate)(CFDictionaryRef, CFDictionaryRef);
static OSStatus (*orig_SecItemDelete)(CFDictionaryRef);

static CFDictionaryRef spotRewriteGroup(CFDictionaryRef query) {
    NSString *realGroup = spotAccessGroupID();
    if (!realGroup) return query;
    NSMutableDictionary *mutable = [(__bridge NSDictionary *)query mutableCopy];
    for (NSString *key in @[ (__bridge NSString *)kSecAttrAccessGroup ]) {
        id value = mutable[key];
        if ([value isKindOfClass:[NSString class]] && [value hasPrefix:@"com.spotify.client"])
            mutable[key] = realGroup;
    }
    return (__bridge CFDictionaryRef)mutable;
}

static OSStatus spot_SecItemCopyMatching(CFDictionaryRef query, CFTypeRef *result) {
    CFDictionaryRef rewritten = spotRewriteGroup(query);
    OSStatus status = orig_SecItemCopyMatching(rewritten, result);
    if (rewritten != query) CFRelease(rewritten);
    return status;
}

static OSStatus spot_SecItemAdd(CFDictionaryRef attributes, CFTypeRef *result) {
    CFDictionaryRef rewritten = spotRewriteGroup(attributes);
    OSStatus status = orig_SecItemAdd(rewritten, result);
    if (rewritten != attributes) CFRelease(rewritten);
    return status;
}

static OSStatus spot_SecItemUpdate(CFDictionaryRef query, CFDictionaryRef attrs) {
    CFDictionaryRef rewrittenQuery = spotRewriteGroup(query);
    CFDictionaryRef rewrittenAttrs = spotRewriteGroup(attrs);
    OSStatus status = orig_SecItemUpdate(rewrittenQuery, rewrittenAttrs);
    if (rewrittenQuery != query) CFRelease(rewrittenQuery);
    if (rewrittenAttrs != attrs) CFRelease(rewrittenAttrs);
    return status;
}

static OSStatus spot_SecItemDelete(CFDictionaryRef query) {
    CFDictionaryRef rewritten = spotRewriteGroup(query);
    OSStatus status = orig_SecItemDelete(rewritten);
    if (rewritten != query) CFRelease(rewritten);
    return status;
}

static void rebindSecItem(void) {
    rebind_symbols((struct rebinding[4]) {
        {"SecItemCopyMatching", (void *)spot_SecItemCopyMatching, (void **)&orig_SecItemCopyMatching},
        {"SecItemAdd", (void *)spot_SecItemAdd, (void **)&orig_SecItemAdd},
        {"SecItemUpdate", (void *)spot_SecItemUpdate, (void **)&orig_SecItemUpdate},
        {"SecItemDelete", (void *)spot_SecItemDelete, (void **)&orig_SecItemDelete},
    }, 4);
    os_log(spotLog(), "SpotifyMod: SecItem rebound (access group -> %@)", spotAccessGroupID() ?: @"?");
}

// --- app-group container ----------------------------------------------------

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

// --- CloudKit neuter -------------------------------------------------------

static void neuterCloudKit(void) {
    // CKContainer's initializer path asserts without iCloud entitlements.
    Class container = NSClassFromString(@"CKContainer");
    if (!container) return;
    SEL sel = sel_registerName("initWithContainerIdentifier:");
    Method m = class_getInstanceMethod(container, sel);
    if (m) {
        class_replaceMethod(container, sel,
            imp_implementationWithBlock(^id(id self, id identifier) { return nil; }),
            method_getTypeEncoding(m));
    }
    // CKEntitlements/container lookup used by CloudKit internals.
    Class entitlements = NSClassFromString(@"CKEntitlements");
    if (entitlements) {
        for (NSString *selName in @[ @"containerIdentifier", @"applicationContainerIdentifier" ]) {
            SEL s = NSSelectorFromString(selName);
            Method em = class_getInstanceMethod(entitlements, s);
            if (em) {
                class_replaceMethod(entitlements, s,
                    imp_implementationWithBlock(^id(id self) { return nil; }),
                    method_getTypeEncoding(em));
            }
        }
    }
}

void SpotifySideloadFixInit(void) {
    rebindSecItem();
    fixAppGroupContainer();
    neuterCloudKit();
}
