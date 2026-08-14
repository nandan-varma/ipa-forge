// SignInFix.m — sideload sign-in fix for AltStore re-signed YouTube.
//
// AltStore installs the app under a changed bundle id
// (com.google.ios.youtube.<teamID>), which breaks Google's SSO/GAIA flow:
//   - the OAuth page refuses with "You can't sign in to this app because
//     Google can't confirm that it's safe." (SSORPCService appends device
//     fingerprint query params — system_version/app_version/kdlc/kss/
//     lib_ver/device_model — and Google's risk engine rejects the
//     modified build; stripping them fixes it, per therealFoxster's
//     YTSideloadSignInFix / AhmedBafkir's gist)
//   - SSO token keychain storage uses access groups that no longer match
//     the re-signed app (SSOKeychain*/GULKeychainStorage/
//     GNPEncryptionConfiguration/FIRInstallationsStore/CHMConfiguration)
//   - Google frameworks see the wrong bundle id / app name
//     (IAmYouTube set: YTVersionUtils/GCKBUtils/GPCDeviceInfo/OGLBundle/
//     GVROverlayView/SSOClientLogin/SSOConfiguration + NSBundle spoof +
//     GULAppEnvironmentUtil isFromAppStore + APMAEU isFAS + YTHotConfig)
// Hook set is the union of YouMod's Sideloading.x (adapted from YTLite +
// uYouEnhanced) and YTSideloadSignInFix; every class/selector verified in
// the 21.32.4 binary.

#import "YTFreedom.h"
#import <Security/Security.h>

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

// THE fix for "Google can't confirm that it's safe": strip the SSO RPC
// device-fingerprint query params so the sign-in request is
// indistinguishable from the stock app's.
static void fixSSORPCService(void) {
    static IMP orig_URLFromURL;
    orig_URLFromURL = ytfHookClass(NSClassFromString(@"SSORPCService"),
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
            os_log(ytfLog(), "YTFreedom: stripped SSO fingerprint params from sign-in URL");
            return components.URL;
        });
    (void)orig_URLFromURL;
}

// Make Google frameworks see the stock bundle id / app name.
static void fixBundleIdentity(void) {
    static IMP orig_defaultSourceString;
    orig_defaultSourceString = ytfHookClass(NSClassFromString(@"SSOClientLogin"),
        @selector(defaultSourceString), ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_defaultSourceString;

    static IMP orig_appName;
    orig_appName = ytfHookClass(NSClassFromString(@"YTVersionUtils"),
        @selector(appName), ^id(id cls) { return YT_NAME; });
    (void)orig_appName;

    static IMP orig_appID;
    orig_appID = ytfHookClass(NSClassFromString(@"YTVersionUtils"),
        @selector(appID), ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_appID;

    static IMP orig_appIdentifier;
    orig_appIdentifier = ytfHookClass(NSClassFromString(@"GCKBUtils"),
        @selector(appIdentifier), ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_appIdentifier;

    static IMP orig_bundleId;
    orig_bundleId = ytfHookClass(NSClassFromString(@"GPCDeviceInfo"),
        @selector(bundleId), ^id(id cls) { return YT_BUNDLE_ID; });
    (void)orig_bundleId;

    static IMP orig_shortAppName;
    orig_shortAppName = ytfHookClass(NSClassFromString(@"OGLBundle"),
        @selector(shortAppName), ^id(id cls) { return YT_NAME; });
    (void)orig_shortAppName;

    static IMP orig_overlayAppName;
    orig_overlayAppName = ytfHookClass(NSClassFromString(@"GVROverlayView"),
        @selector(appName), ^id(id cls) { return YT_NAME; });
    (void)orig_overlayAppName;

    static IMP orig_isFromAppStore;
    orig_isFromAppStore = ytfHookClass(NSClassFromString(@"GULAppEnvironmentUtil"),
        @selector(isFromAppStore), ^BOOL(id cls) { return YES; });
    (void)orig_isFromAppStore;

    static IMP orig_isFAS;
    orig_isFAS = ytfHookClass(NSClassFromString(@"APMAEU"),
        @selector(isFAS), ^BOOL(id cls) { return YES; });
    (void)orig_isFAS;

    static IMP orig_fillingHacks;
    orig_fillingHacks = ytfHookClass(NSClassFromString(@"YTHotConfig"),
        @selector(clientInfraClientConfigIosEnableFillingEncodedHacksInnertubeContext),
        ^BOOL(id self) { return NO; });
    (void)orig_fillingHacks;

    static IMP orig_ssoConfig;
    orig_ssoConfig = ytfHookInstance(NSClassFromString(@"SSOConfiguration"),
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

    // NSBundle spoof: only mainBundle is affected; other bundles and system
    // callers fall through to %orig.
    static IMP orig_bundleWithIdentifier;
    orig_bundleWithIdentifier = ytfHookClass([NSBundle class],
        @selector(bundleWithIdentifier:),
        ^id(id cls, NSString *identifier) {
            if ([identifier isEqualToString:YT_BUNDLE_ID])
                return [NSBundle mainBundle];
            return ((id(*)(id, SEL, id))orig_bundleWithIdentifier)(
                cls, @selector(bundleWithIdentifier:), identifier);
        });
    (void)orig_bundleWithIdentifier;

    static IMP orig_bundleIdentifier;
    orig_bundleIdentifier = ytfHookInstance([NSBundle class],
        @selector(bundleIdentifier),
        ^id(id self) {
            if ([self isEqual:[NSBundle mainBundle]])
                return YT_BUNDLE_ID;
            return ((id(*)(id, SEL))orig_bundleIdentifier)(self, @selector(bundleIdentifier));
        });
    (void)orig_bundleIdentifier;

    static IMP orig_infoDictionary;
    orig_infoDictionary = ytfHookInstance([NSBundle class],
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
    orig_objectForKey = ytfHookInstance([NSBundle class],
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
// persist across launches.
static void fixKeychainAccessGroups(void) {
    static IMP orig_kc_accessGroup, orig_kc_sharedAccessGroup;
    NSArray<Class> *keychainClasses = @[
        NSClassFromString(@"SSOKeychainHelper"),
        NSClassFromString(@"SSOKeychainCore"),
        NSClassFromString(@"SSOKeychain"),
    ];
    for (Class cls in keychainClasses) {
        orig_kc_accessGroup = ytfHookClass(cls, @selector(accessGroup),
            ^id(id c) { return accessGroupID(); });
        orig_kc_sharedAccessGroup = ytfHookClass(cls, @selector(sharedAccessGroup),
            ^id(id c) { return accessGroupID(); });
    }
    (void)orig_kc_accessGroup;
    (void)orig_kc_sharedAccessGroup;

    static IMP orig_folsom_group;
    orig_folsom_group = ytfHookInstance(NSClassFromString(@"SSOFolsomKeychainUtils"),
        @selector(sharedAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_folsom_group;

    static IMP orig_getObjectForKey;
    orig_getObjectForKey = ytfHookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(getObjectForKey:objectClass:accessGroup:completionHandler:),
        ^void(id self, id key, id objectClass, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_getObjectForKey)(
                self, @selector(getObjectForKey:objectClass:accessGroup:completionHandler:),
                key, objectClass, accessGroupID(), handler);
        });
    (void)orig_getObjectForKey;

    static IMP orig_getObjectFromKeychain;
    orig_getObjectFromKeychain = ytfHookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(getObjectFromKeychainForKey:objectClass:accessGroup:completionHandler:),
        ^void(id self, id key, id objectClass, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_getObjectFromKeychain)(
                self, @selector(getObjectFromKeychainForKey:objectClass:accessGroup:completionHandler:),
                key, objectClass, accessGroupID(), handler);
        });
    (void)orig_getObjectFromKeychain;

    static IMP orig_setObject;
    orig_setObject = ytfHookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(setObject:forKey:accessGroup:completionHandler:),
        ^void(id self, id object, id key, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id, id))orig_setObject)(
                self, @selector(setObject:forKey:accessGroup:completionHandler:),
                object, key, accessGroupID(), handler);
        });
    (void)orig_setObject;

    static IMP orig_removeObjectForKey;
    orig_removeObjectForKey = ytfHookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(removeObjectForKey:accessGroup:completionHandler:),
        ^void(id self, id key, id accessGroup, id handler) {
            ((void(*)(id, SEL, id, id, id))orig_removeObjectForKey)(
                self, @selector(removeObjectForKey:accessGroup:completionHandler:),
                key, accessGroupID(), handler);
        });
    (void)orig_removeObjectForKey;

    static IMP orig_keychainQuery;
    orig_keychainQuery = ytfHookInstance(NSClassFromString(@"GULKeychainStorage"),
        @selector(keychainQueryWithKey:accessGroup:),
        ^id(id self, id key, id accessGroup) {
            return ((id(*)(id, SEL, id, id))orig_keychainQuery)(
                self, @selector(keychainQueryWithKey:accessGroup:), key, accessGroupID());
        });
    (void)orig_keychainQuery;

    static IMP orig_gnp_init;
    orig_gnp_init = ytfHookInstance(NSClassFromString(@"GNPEncryptionConfiguration"),
        @selector(initWithKeychainAccessGroup:),
        ^id(id self, id group) {
            return ((id(*)(id, SEL, id))orig_gnp_init)(
                self, @selector(initWithKeychainAccessGroup:), accessGroupID());
        });
    (void)orig_gnp_init;

    static IMP orig_gnp_group;
    orig_gnp_group = ytfHookInstance(NSClassFromString(@"GNPEncryptionConfiguration"),
        @selector(keychainAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_gnp_group;

    static IMP orig_fir_init;
    orig_fir_init = ytfHookInstance(NSClassFromString(@"FIRInstallationsStore"),
        @selector(initWithSecureStorage:accessGroup:),
        ^id(id self, id storage, id group) {
            return ((id(*)(id, SEL, id, id))orig_fir_init)(
                self, @selector(initWithSecureStorage:accessGroup:), storage, accessGroupID());
        });
    (void)orig_fir_init;

    static IMP orig_fir_group;
    orig_fir_group = ytfHookInstance(NSClassFromString(@"FIRInstallationsStore"),
        @selector(accessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_fir_group;

    static IMP orig_chm_set;
    orig_chm_set = ytfHookInstance(NSClassFromString(@"CHMConfiguration"),
        @selector(setKeychainAccessGroup:),
        ^void(id self, id group) {
            ((void(*)(id, SEL, id))orig_chm_set)(
                self, @selector(setKeychainAccessGroup:), accessGroupID());
        });
    (void)orig_chm_set;

    static IMP orig_chm_group;
    orig_chm_group = ytfHookInstance(NSClassFromString(@"CHMConfiguration"),
        @selector(keychainAccessGroup),
        ^id(id self) { return accessGroupID(); });
    (void)orig_chm_group;
}

// App group container URL: the app's group ids don't exist under the
// re-signed bundle; redirect container lookups into Documents/AppGroup.
static void fixAppGroupContainer(void) {
    static IMP orig_containerURL;
    orig_containerURL = ytfHookInstance([NSFileManager class],
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

void YTFreedomSignInFixInit(void) {
    fixSSORPCService();
    fixBundleIdentity();
    fixKeychainAccessGroups();
    fixAppGroupContainer();
}
