// libYTHook.m — YouTube 21.32.4 hook dylib (from scratch, no substrate).
//
// Two feature groups, all plain ObjC-runtime swizzling loaded via an
// __attribute__((constructor)):
//
// 1) Player ad removal ("YTFreedom")
//    Targets were located by static analysis of the 21.32.4 binary
//    (objc_classlist/methlist walk; see the yt_inventory tooling):
//      - YTAdBreakResponseReceivedOpportunityAdapterV2
//          didReceiveAdBreakResponse:fromAdBreakSlot:
//          (modern "ads control flow v2" entry point where an ad-break
//           response is turned into scheduled ad slots)
//      - YTAdBreakRendererAdapter createAds
//          (classic renderer path that materializes the ad list for a break)
//    Both swizzles are conservative: the response flow still runs, the break
//    still resolves, it just contains no ads.
//
// 2) Sideload sign-in fix ("YTFreedom SignIn")
//    AltStore installs the app under a changed bundle id
//    (com.google.ios.youtube.<teamID>), which breaks Google's SSO/GAIA flow:
//      - the OAuth page refuses with "You can't sign in to this app because
//        Google can't confirm that it's safe." (SSORPCService appends device
//        fingerprint query params — system_version/app_version/kdlc/kss/
//        lib_ver/device_model — and Google's risk engine rejects the
//        modified build; stripping them fixes it, per therealFoxster's
//        YTSideloadSignInFix / AhmedBafkir's gist)
//      - SSO token keychain storage uses access groups that no longer match
//        the re-signed app (SSOKeychain*/GULKeychainStorage/
//        GNPEncryptionConfiguration/FIRInstallationsStore/CHMConfiguration)
//      - Google frameworks see the wrong bundle id / app name
//        (IAmYouTube set: YTVersionUtils/GCKBUtils/GPCDeviceInfo/OGLBundle/
//        GVROverlayView/SSOClientLogin/SSOConfiguration + NSBundle spoof +
//        GULAppEnvironmentUtil isFromAppStore + APMAEU isFAS + YTHotConfig)
//    The hook set is the union of YouMod's Sideloading.x (itself adapted
//    from YTLite + uYouEnhanced) and YTSideloadSignInFix. All hook classes
//    and selectors were verified present in the 21.32.4 binary.

#import <Foundation/Foundation.h>
#import <Security/Security.h>
#import <objc/runtime.h>
#import <os/log.h>

#define YT_BUNDLE_ID @"com.google.ios.youtube"
#define YT_NAME @"YouTube"

static os_log_t ytlog(void) {
    static os_log_t log;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        log = os_log_create("com.nandan.ytfreedom", "hook");
    });
    return log;
}

// --- hook plumbing ---------------------------------------------------------

// Replace an instance method's IMP with a block IMP; returns the original
// IMP so the block can chain to it. No-op (returns NULL) when the method
// is absent, so hooks are safe against class drift across app versions.
static IMP hookInstance(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        os_log(ytlog(), "YTFreedom: instance method %s not found on %s",
               sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    IMP newImp = imp_implementationWithBlock(block);
    class_replaceMethod(cls, sel, newImp, method_getTypeEncoding(m));
    os_log(ytlog(), "YTFreedom: hooked -[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

// Same for class methods (replacement lands on the metaclass, so an
// inherited implementation is overridden only for this class).
static IMP hookClass(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getClassMethod(cls, sel);
    if (!m) {
        os_log(ytlog(), "YTFreedom: class method %s not found on %s",
               sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    IMP newImp = imp_implementationWithBlock(block);
    class_replaceMethod(object_getClass(cls), sel, newImp, method_getTypeEncoding(m));
    os_log(ytlog(), "YTFreedom: hooked +[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

// --- ad removal (existing) -------------------------------------------------

static void swizzleVoid(id self, id arg1, id arg2) {
    // do nothing: drop the ad-break response. Break resolves empty.
    os_log(ytlog(), "YTFreedom: dropped ad-break response (%@, slot=%@)",
           arg1, arg2);
}

static id swizzleCreateAds(id self) {
    os_log(ytlog(), "YTFreedom: createAds -> empty");
    return @[];
}

// --- sign-in fix -----------------------------------------------------------

// The real keychain access group of this (re-signed) install. Google's SSO
// classes ask for groups like "com.google.ios.youtube" which no longer
// exist after AltStore changed the bundle id; the actual group (derived
// from the signing team prefix) is discoverable via the bundleSeedID
// generic-password item.
static NSString *accessGroupID(void) {
    NSDictionary *query = [NSDictionary dictionaryWithObjectsAndKeys:
                           (__bridge NSString *)kSecClassGenericPassword, (__bridge NSString *)kSecClass,
                           @"bundleSeedID", kSecAttrAccount,
                           @"", kSecAttrService,
                           (id)kCFBooleanTrue, kSecReturnAttributes,
                           nil];
    CFDictionaryRef result = nil;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, (CFTypeRef *)&result);
    if (status == errSecItemNotFound) {
        status = SecItemAdd((__bridge CFDictionaryRef)query, (CFTypeRef *)&result);
        if (status != errSecSuccess)
            return nil;
    }
    NSString *accessGroup = [(__bridge NSDictionary *)result objectForKey:(__bridge NSString *)kSecAttrAccessGroup];
    return accessGroup;
}

// THE fix for "Google can't confirm that it's safe": the SSO RPC layer
// decorates the sign-in URL with device-fingerprint query params; Google's
// risk engine uses them to detect the modified build. Strip them so the
// request is indistinguishable from the stock app's. (AhmedBafkir gist /
// therealFoxster YTSideloadSignInFix.)
static void fixSSORPCService(void) {
    static IMP orig_URLFromURL;
    orig_URLFromURL = hookClass(NSClassFromString(@"SSORPCService"),
        @selector(URLFromURL:withAdditionalFragmentParameters:),
        ^id(id cls, NSURL *url, NSDictionary *params) {
            NSURL *origURL = ((id(*)(id, SEL, id, id))orig_URLFromURL)(
                cls, @selector(URLFromURL:withAdditionalFragmentParameters:), url, params);
            if (!origURL) return origURL;
            NSURLComponents *components = [[NSURLComponents alloc] initWithURL:origURL
                                                       resolvingAgainstBaseURL:NO];
            NSArray<NSString *> *strip = @[@"system_version", @"app_version",
                                           @"kdlc", @"kss", @"lib_ver", @"device_model"];
            NSMutableArray<NSURLQueryItem *> *kept = [NSMutableArray array];
            for (NSURLQueryItem *item in components.queryItems) {
                if (![strip containsObject:item.name])
                    [kept addObject:item];
            }
            components.queryItems = kept;
            os_log(ytlog(), "YTFreedom: stripped SSO fingerprint params from sign-in URL");
            return components.URL;
        });
    (void)orig_URLFromURL;
}

// Make Google frameworks see the stock bundle id / app name. (IAmYouTube,
// PoomSmart; extended by YTLite/YouMod with SSOClientLogin + YTHotConfig.)
static void fixBundleIdentity(void) {
    static IMP orig_defaultSourceString;
    orig_defaultSourceString = hookClass(NSClassFromString(@"SSOClientLogin"),
        @selector(defaultSourceString),
        ^id(id cls) {
            return YT_BUNDLE_ID;
        });
    (void)orig_defaultSourceString;

    static IMP orig_appName;
    orig_appName = hookClass(NSClassFromString(@"YTVersionUtils"),
        @selector(appName),
        ^id(id cls) { return YT_NAME; });
    (void)orig_appName;

    static IMP orig_appID;
    orig_appID = hookClass(NSClassFromString(@"YTVersionUtils"),
        @selector(appID),
        ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_appID;

    static IMP orig_appIdentifier;
    orig_appIdentifier = hookClass(NSClassFromString(@"GCKBUtils"),
        @selector(appIdentifier),
        ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_appIdentifier;

    static IMP orig_bundleId;
    orig_bundleId = hookClass(NSClassFromString(@"GPCDeviceInfo"),
        @selector(bundleId),
        ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_bundleId;

    static IMP orig_shortAppName;
    orig_shortAppName = hookClass(NSClassFromString(@"OGLBundle"),
        @selector(shortAppName),
        ^id(id cls) { return YT_NAME; });
    (void)orig_shortAppName;

    static IMP orig_overlayAppName;
    orig_overlayAppName = hookClass(NSClassFromString(@"GVROverlayView"),
        @selector(appName),
        ^id(id cls) { return YT_NAME; });
    (void)orig_overlayAppName;

    static IMP orig_isFromAppStore;
    orig_isFromAppStore = hookClass(NSClassFromString(@"GULAppEnvironmentUtil"),
        @selector(isFromAppStore),
        ^BOOL(id cls) { return YES; });
    (void)orig_isFromAppStore;

    static IMP orig_isFAS;
    orig_isFAS = hookClass(NSClassFromString(@"APMAEU"),
        @selector(isFAS),
        ^BOOL(id cls) { return YES; });
    (void)orig_isFAS;

    static IMP orig_fillingHacks;
    orig_fillingHacks = hookClass(NSClassFromString(@"YTHotConfig"),
        @selector(clientInfraClientConfigIosEnableFillingEncodedHacksInnertubeContext),
        ^BOOL(id self) { return NO; });
    (void)orig_fillingHacks;

    static IMP orig_ssoConfig;
    orig_ssoConfig = hookInstance(NSClassFromString(@"SSOConfiguration"),
        @selector(initWithClientID:supportedAccountServices:),
        ^id(id self, id clientID, id services) {
            self = ((id(*)(id, SEL, id, id))orig_ssoConfig)(
                self, @selector(initWithClientID:supportedAccountServices:), clientID, services);
            if (self) {
                [self setValue:YT_NAME forKey:@"_shortAppName"];
                [self setValue:YT_BUNDLE_ID forKey:@"_applicationIdentifier"];
            }
            return self;
        });
    (void)orig_ssoConfig;

    // NSBundle spoof: the whole process (incl. Google SDKs) sees the stock
    // bundle identity for the main bundle. Scope-checked like YouMod:
    // only mainBundle is affected; other bundles and system callers
    // (whose NSBundle isn't mainBundle) fall through to %orig.
    static IMP orig_bundleWithIdentifier;
    orig_bundleWithIdentifier = hookClass([NSBundle class],
        @selector(bundleWithIdentifier:),
        ^id(id cls, NSString *identifier) {
            if ([identifier isEqualToString:YT_BUNDLE_ID])
                return [NSBundle mainBundle];
            return ((id(*)(id, SEL, id))orig_bundleWithIdentifier)(
                cls, @selector(bundleWithIdentifier:), identifier);
        });
    (void)orig_bundleWithIdentifier;

    static IMP orig_bundleIdentifier;
    orig_bundleIdentifier = hookInstance([NSBundle class],
        @selector(bundleIdentifier),
        ^id(id self) {
            if ([self isEqual:[NSBundle mainBundle]])
                return YT_BUNDLE_ID;
            return ((id(*)(id, SEL))orig_bundleIdentifier)(self, @selector(bundleIdentifier));
        });
    (void)orig_bundleIdentifier;

    static IMP orig_infoDictionary;
    orig_infoDictionary = hookInstance([NSBundle class],
        @selector(infoDictionary),
        ^id(id self) {
            NSDictionary *dict = ((id(*)(id, SEL))orig_infoDictionary)(self, @selector(infoDictionary));
            if (![self isEqual:[NSBundle mainBundle]])
                return dict;
            NSMutableDictionary *info = [dict mutableCopy];
            if (info[@"CFBundleIdentifier"]) info[@"CFBundleIdentifier"] = YT_BUNDLE_ID;
            if (info[@"CFBundleDisplayName"]) info[@"CFBundleDisplayName"] = YT_NAME;
            if (info[@"CFBundleName"]) info[@"CFBundleName"] = YT_NAME;
            return info;
        });
    (void)orig_infoDictionary;

    static IMP orig_objectForKey;
    orig_objectForKey = hookInstance([NSBundle class],
        @selector(objectForInfoDictionaryKey:),
        ^id(id self, NSString *key) {
            if (![self isEqual:[NSBundle mainBundle]])
                return ((id(*)(id, SEL, id))orig_objectForKey)(self, @selector(objectForInfoDictionaryKey:), key);
            if ([key isEqualToString:@"CFBundleIdentifier"])
                return YT_BUNDLE_ID;
            if ([key isEqualToString:@"CFBundleDisplayName"] || [key isEqualToString:@"CFBundleName"])
                return YT_NAME;
            return ((id(*)(id, SEL, id))orig_objectForKey)(self, @selector(objectForInfoDictionaryKey:), key);
        });
    (void)orig_objectForKey;
}

// Route every Google keychain class to the real access group so SSO tokens
// persist across launches. (BandarHL fixYouTubeLogin gist, extended by
// YouMod with GULKeychainStorage/GNPEncryptionConfiguration/
// FIRInstallationsStore/CHMConfiguration.)
static void fixKeychainAccessGroups(void) {
    // Class methods: accessGroup / sharedAccessGroup.
    static IMP orig_kc_accessGroup, orig_kc_sharedAccessGroup;
    NSArray<Class> *keychainClasses = @[
        NSClassFromString(@"SSOKeychainHelper"),
        NSClassFromString(@"SSOKeychainCore"),
        NSClassFromString(@"SSOKeychain"),
    ];
    for (Class cls in keychainClasses) {
        orig_kc_accessGroup = hookClass(cls, @selector(accessGroup),
            ^id(id c) { return accessGroupID(); });
        orig_kc_sharedAccessGroup = hookClass(cls, @selector(sharedAccessGroup),
            ^id(id c) { return accessGroupID(); });
    }
    (void)orig_kc_accessGroup;
    (void)orig_kc_sharedAccessGroup;

    // Instance method on SSOFolsomKeychainUtils.
    static IMP orig_folsom_group;
    orig_folsom_group = hookInstance(NSClassFromString(@"SSOFolsomKeychainUtils"),
        @selector(sharedAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_folsom_group;

    // GULKeychainStorage: swap the accessGroup argument on every entry
    // point before chaining to the original implementation.
    static IMP orig_getObjectForKey;
    orig_getObjectForKey = hookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(getObjectForKey:objectClass:accessGroup:completionHandler:),
        ^void(id self, id key, id objectClass, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_getObjectForKey)(
                self, @selector(getObjectForKey:objectClass:accessGroup:completionHandler:),
                key, objectClass, accessGroupID(), handler);
        });
    (void)orig_getObjectForKey;

    static IMP orig_getObjectFromKeychain;
    orig_getObjectFromKeychain = hookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(getObjectFromKeychainForKey:objectClass:accessGroup:completionHandler:),
        ^void(id self, id key, id objectClass, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_getObjectFromKeychain)(
                self, @selector(getObjectFromKeychainForKey:objectClass:accessGroup:completionHandler:),
                key, objectClass, accessGroupID(), handler);
        });
    (void)orig_getObjectFromKeychain;

    static IMP orig_setObject;
    orig_setObject = hookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(setObject:forKey:accessGroup:completionHandler:),
        ^void(id self, id object, id key, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_setObject)(
                self, @selector(setObject:forKey:accessGroup:completionHandler:),
                object, key, accessGroupID(), handler);
        });
    (void)orig_setObject;

    static IMP orig_removeObjectForKey;
    orig_removeObjectForKey = hookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(removeObjectForKey:accessGroup:completionHandler:),
        ^void(id self, id key, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id))orig_removeObjectForKey)(
                self, @selector(removeObjectForKey:accessGroup:completionHandler:),
                key, accessGroupID(), handler);
        });
    (void)orig_removeObjectForKey;

    static IMP orig_keychainQuery;
    orig_keychainQuery = hookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(keychainQueryWithKey:accessGroup:),
        ^id(id self, id key, id accessGroup) {
            return ((id(*)(id, SEL, id, id))orig_keychainQuery)(
                self, @selector(keychainQueryWithKey:accessGroup:), key, accessGroupID());
        });
    (void)orig_keychainQuery;

    // GNPEncryptionConfiguration (Google Network Pack).
    static IMP orig_gnp_init;
    orig_gnp_init = hookInstance(NSClassFromString(@"GNPEncryptionConfiguration"),
        @selector(initWithKeychainAccessGroup:),
        ^id(id self, id group) {
            return ((id(*)(id, SEL, id))orig_gnp_init)(
                self, @selector(initWithKeychainAccessGroup:), accessGroupID());
        });
    (void)orig_gnp_init;

    static IMP orig_gnp_group;
    orig_gnp_group = hookInstance(NSClassFromString(@"GNPEncryptionConfiguration"),
        @selector(keychainAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_gnp_group;

    // FIRInstallationsStore (Firebase Installations).
    static IMP orig_fir_init;
    orig_fir_init = hookInstance(NSClassFromString(@"FIRInstallationsStore"),
        @selector(initWithSecureStorage:accessGroup:),
        ^id(id self, id storage, id group) {
            return ((id(*)(id, SEL, id, id))orig_fir_init)(
                self, @selector(initWithSecureStorage:accessGroup:), storage, accessGroupID());
        });
    (void)orig_fir_init;

    static IMP orig_fir_group;
    orig_fir_group = hookInstance(NSClassFromString(@"FIRInstallationsStore"),
        @selector(accessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_fir_group;

    // CHMConfiguration (Chrome Mobile).
    static IMP orig_chm_set;
    orig_chm_set = hookInstance(NSClassFromString(@"CHMConfiguration"),
        @selector(setKeychainAccessGroup:),
        ^void(id self, id group) {
            ((void(*)(id, SEL, id))orig_chm_set)(
                self, @selector(setKeychainAccessGroup:), accessGroupID());
        });
    (void)orig_chm_set;

    static IMP orig_chm_group;
    orig_chm_group = hookInstance(NSClassFromString(@"CHMConfiguration"),
        @selector(keychainAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_chm_group;
}

// App group container URL: the app's group ids don't exist under the
// re-signed bundle, so redirect container lookups into Documents/AppGroup
// (same trick as YTLite/YouMod — avoids nil-container failures).
static void fixAppGroupContainer(void) {
    static IMP orig_containerURL;
    orig_containerURL = hookInstance([NSFileManager class],
        @selector(containerURLForSecurityApplicationGroupIdentifier:),
        ^id(id self, NSString *groupIdentifier) {
            if (groupIdentifier != nil) {
                NSArray *paths = [[NSFileManager defaultManager]
                    URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
                NSURL *documentsURL = [paths lastObject];
                return [documentsURL URLByAppendingPathComponent:@"AppGroup"];
            }
            return ((id(*)(id, SEL, id))orig_containerURL)(
                self, @selector(containerURLForSecurityApplicationGroupIdentifier:), groupIdentifier);
        });
    (void)orig_containerURL;
}

__attribute__((constructor))
static void ytfreedom_init(void) {
    // --- ad removal ---
    hookInstance(NSClassFromString(@"YTAdBreakResponseReceivedOpportunityAdapterV2"),
                 sel_registerName("didReceiveAdBreakResponse:fromAdBreakSlot:"),
                 ^(id self, id response, id slot) {
                     swizzleVoid(self, response, slot);
                 });
    hookInstance(NSClassFromString(@"YTAdBreakRendererAdapter"),
                 sel_registerName("createAds"),
                 ^(id self) {
                     return swizzleCreateAds(self);
                 });

    // --- sign-in fix ---
    fixSSORPCService();
    fixBundleIdentity();
    fixKeychainAccessGroups();
    fixAppGroupContainer();

    os_log(ytlog(), "YTFreedom: init complete (adblock + sign-in fix)");
}
