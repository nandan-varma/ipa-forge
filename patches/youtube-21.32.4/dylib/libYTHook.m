// libYTHook.m — YouTube 21.32.4 hook dylib (from scratch, no substrate).
//
// Two feature groups, all plain ObjC-runtime swizzling loaded via an
// __attribute__((constructor)):
//
// 1) Player + feed ad removal
//    The stock "classic" hook points of older tweaks (YTIPlayerResponse
//    isMonetized:, YTDataUtils spamSignalsDictionary:, YTISectionList-
//    ViewController loadWithModel:) are absent from 21.32.4; the rewrite
//    follows YouMod's Ads.x (built for exactly 21.32.4) and covers every
//    layer of the modern ads pipeline:
//      - data:    YTPlayerResponse +playerAdsArray/+adSlotsArray added as
//                 empty-array methods; YTIClientMdxGlobalConfig
//                 +enableSkippableAd
//      - playback: YTLocalPlaybackController createAdsPlaybackCoordinator
//                 -> nil; MDXSessionImpl adPlaying: no-op; existing
//                 YTAdBreakResponseReceivedOpportunityAdapterV2 +
//                 YTAdBreakRendererAdapter hooks kept as backstop
//      - request: YTAdsInnerTubeContextDecorator /
//                 YTAccountScopedAdsInnerTubeContextDecorator
//                 decorateContext: with nil; YTAdShieldUtils
//                 spamSignalsDictionary* -> empty
//      - feed:    YTInnerTubeCollectionViewController section filtering by
//                 YTIElementRenderer ad detection; _ASDisplayView hiding
//                 of in-player ad overlays; player product-in-video overlay
//                 dropped; Shorts ad reels filtered
//    Every class and selector below was verified present in the 21.32.4
//    binary with yt_inventory.py.
//
// 2) Sideload sign-in fix
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
//    Hook set is the union of YouMod's Sideloading.x (itself adapted
//    from YTLite + uYouEnhanced) and YTSideloadSignInFix.

#import <Foundation/Foundation.h>
#import <Security/Security.h>
#import <UIKit/UIKit.h>
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

// Add a method that does not exist yet (logos' %new). encoding is the
// ObjC type encoding of the method, e.g. "@@:" for id(id,SEL) or "B@:"
// for BOOL(id,SEL).
static void addInstanceMethod(Class cls, SEL sel, id block, const char *encoding) {
    if (!cls) return;
    if (!class_getInstanceMethod(cls, sel)) {
        class_addMethod(cls, sel, imp_implementationWithBlock(block), encoding);
        os_log(ytlog(), "YTFreedom: added -[%s %s]", class_getName(cls), sel_getName(sel));
    }
}

// Selectors that exist on YouTube's classes but aren't declared in any
// SDK header. Declared here so clang allows dynamic dispatch on `id`
// receivers; presence is always guarded with respondsToSelector: first.
@protocol YTFreedomAdHooks <NSObject>
@optional
- (BOOL)hasCompatibilityOptions;
- (id)compatibilityOptions;
- (BOOL)hasAdLoggingData;
- (NSString *)overlayIdentifier;
- (BOOL)isAdVideo;
@end

// --- ad removal ------------------------------------------------------------

// Feed-section ad detection (YouMod Ads.x): an element renderer is an ad
// when it carries ad-logging compatibility data, or its description
// matches a known ad layout string.
static NSArray<NSString *> *ytAdStrings(void) {
    return @[
        @"brand_promo",
        @"carousel_footered_layout",
        @"carousel_headered_layout",
        @"eml.expandable_metadata",
        @"feed_ad_metadata",
        @"full_width_portrait_image_layout",
        @"full_width_square_image_layout",
        @"landscape_image_wide_button_layout",
        @"post_shelf",
        @"product_carousel",
        @"product_engagement_panel",
        @"product_item",
        @"shopping_carousel",
        @"shopping_item_card_list",
        @"statement_banner",
        @"square_image_layout",
        @"text_image_button_layout",
        @"text_search_ad",
        @"video_display_full_layout",
        @"video_display_full_buttoned_layout",
    ];
}

static BOOL isAdElementRenderer(id elementRenderer) {
    if (!elementRenderer) return NO;
    id<YTFreedomAdHooks> renderer = elementRenderer;
    if ([renderer respondsToSelector:@selector(hasCompatibilityOptions)]
        && [renderer hasCompatibilityOptions]) {
        id<YTFreedomAdHooks> compat = [renderer compatibilityOptions];
        if (compat && [compat respondsToSelector:@selector(hasAdLoggingData)]
            && [compat hasAdLoggingData]) {
            return YES;
        }
    }
    NSString *description = [elementRenderer description];
    for (NSString *adStr in ytAdStrings()) {
        if ([description containsString:adStr]) return YES;
    }
    return NO;
}

// Drop ad sections/cards from a collection view's section-renderer array.
// Mirrors YouMod's filteredArray: shelf items, section contents, and
// section headers are each checked for embedded ad renderers.
static NSArray *filteredAdSections(NSArray *array) {
    if (![array isKindOfClass:[NSArray class]]) return array;
    static Class shelfCls, itemSectionCls;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        shelfCls = NSClassFromString(@"YTIShelfRenderer");
        itemSectionCls = NSClassFromString(@"YTIItemSectionRenderer");
    });

    NSMutableArray *newArray = [array mutableCopy];
    NSIndexSet *removeIndexes = [newArray indexesOfObjectsPassingTest:
        ^BOOL(id sectionRenderer, NSUInteger idx, BOOL *stop) {
            // Shelf: filter horizontal-list items.
            if ([sectionRenderer isKindOfClass:shelfCls]) {
                id content = [sectionRenderer valueForKey:@"content"];
                id horizontalList = [content valueForKey:@"horizontalListRenderer"];
                NSMutableArray *itemsArray = [horizontalList valueForKey:@"itemsArray"];
                if ([itemsArray isKindOfClass:[NSMutableArray class]]) {
                    NSIndexSet *removeItems = [itemsArray indexesOfObjectsPassingTest:
                        ^BOOL(id item, NSUInteger i2, BOOL *s2) {
                            return isAdElementRenderer([item valueForKey:@"elementRenderer"]);
                        }];
                    if (removeItems.count > 0) [itemsArray removeObjectsAtIndexes:removeItems];
                }
            }
            if (![sectionRenderer isKindOfClass:itemSectionCls])
                return NO;
            NSMutableArray *contentsArray = [sectionRenderer valueForKey:@"contentsArray"];
            if (![contentsArray isKindOfClass:[NSMutableArray class]])
                return NO;
            if (contentsArray.count > 1) {
                NSIndexSet *removeContents = [contentsArray indexesOfObjectsPassingTest:
                    ^BOOL(id item, NSUInteger i2, BOOL *s2) {
                        return isAdElementRenderer([item valueForKey:@"elementRenderer"]);
                    }];
                if (removeContents.count > 0) [contentsArray removeObjectsAtIndexes:removeContents];
            }
            id firstObject = [contentsArray firstObject];
            return isAdElementRenderer([firstObject valueForKey:@"elementRenderer"]);
        }];
    if (removeIndexes.count > 0) [newArray removeObjectsAtIndexes:removeIndexes];
    return newArray;
}

static BOOL sectionRenderersIvarExists(Class cls) {
    static void *key = &key;
    NSNumber *cached = objc_getAssociatedObject(cls, key);
    if (cached) return cached.boolValue;
    BOOL found = NO;
    unsigned int count = 0;
    Ivar *ivars = class_copyIvarList(cls, &count);
    for (unsigned int i = 0; i < count; i++) {
        if (!strcmp(ivar_getName(ivars[i]), "_sectionRenderers")) { found = YES; break; }
    }
    free(ivars);
    objc_setAssociatedObject(cls, key, @(found), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return found;
}

static void fixPlayerResponseAds(void) {
    // %new on YTPlayerResponse: the ads pipeline queries these arrays on
    // the response wrapper; empty arrays mean "no placements, no slots".
    Class playerResponse = NSClassFromString(@"YTPlayerResponse");
    addInstanceMethod(playerResponse, sel_registerName("playerAdsArray"),
                      ^id(id self) { return [NSMutableArray array]; }, "@@:");
    addInstanceMethod(playerResponse, sel_registerName("adSlotsArray"),
                      ^id(id self) { return [NSMutableArray array]; }, "@@:");

    // %new on YTIClientMdxGlobalConfig.
    addInstanceMethod(NSClassFromString(@"YTIClientMdxGlobalConfig"),
                      sel_registerName("enableSkippableAd"),
                      ^BOOL(id self) { return YES; }, "B@:");

    // No ads playback coordinator -> nothing to play ads with.
    static IMP orig_createAdsPlaybackCoordinator;
    orig_createAdsPlaybackCoordinator = hookInstance(
        NSClassFromString(@"YTLocalPlaybackController"),
        @selector(createAdsPlaybackCoordinator),
        ^id(id self) { return nil; });
    (void)orig_createAdsPlaybackCoordinator;

    // Ad "spam signals" (ad targeting/risk context) -> empty.
    static IMP orig_spamSignals, orig_spamSignalsNoIDFA;
    orig_spamSignals = hookClass(NSClassFromString(@"YTAdShieldUtils"),
        @selector(spamSignalsDictionary),
        ^id(id cls) { return @{}; });
    orig_spamSignalsNoIDFA = hookClass(NSClassFromString(@"YTAdShieldUtils"),
        @selector(spamSignalsDictionaryWithoutIDFA),
        ^id(id cls) { return @{}; });
    (void)orig_spamSignals;
    (void)orig_spamSignalsNoIDFA;

    // InnerTube request context never gets ad decoration (nil is a safe
    // message target in ObjC, matching YouMod's %orig(nil)).
    static IMP orig_decorateContext;
    orig_decorateContext = hookInstance(
        NSClassFromString(@"YTAdsInnerTubeContextDecorator"),
        @selector(decorateContext:),
        ^void(id self, id context) {
            ((void(*)(id, SEL, id))orig_decorateContext)(self, @selector(decorateContext:), nil);
        });
    (void)orig_decorateContext;

    static IMP orig_decorateContextScoped;
    orig_decorateContextScoped = hookInstance(
        NSClassFromString(@"YTAccountScopedAdsInnerTubeContextDecorator"),
        @selector(decorateContext:),
        ^void(id self, id context) {
            ((void(*)(id, SEL, id))orig_decorateContextScoped)(self, @selector(decorateContext:), nil);
        });
    (void)orig_decorateContextScoped;

    // Casting: ad playback progress callbacks -> no-op.
    static IMP orig_adPlaying;
    orig_adPlaying = hookInstance(NSClassFromString(@"MDXSessionImpl"),
        @selector(adPlaying:),
        ^void(id self, id ad) {});
    (void)orig_adPlaying;

    // In-player shopping overlay (product-in-video) never inserted.
    static IMP orig_didInsertOverlay;
    orig_didInsertOverlay = hookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(playerOverlayProvider:didInsertPlayerOverlay:),
        ^void(id self, id provider, id overlay) {
            id<YTFreedomAdHooks> overlayHooks = overlay;
            NSString *identifier = [overlayHooks respondsToSelector:@selector(overlayIdentifier)]
                ? [overlayHooks overlayIdentifier] : nil;
            if ([identifier isEqualToString:@"player_overlay_product_in_video"])
                return;
            ((void(*)(id, SEL, id, id))orig_didInsertOverlay)(
                self, @selector(playerOverlayProvider:didInsertPlayerOverlay:), provider, overlay);
        });
    (void)orig_didInsertOverlay;

    // Ad break response + renderer backstops (from the first iteration).
    hookInstance(NSClassFromString(@"YTAdBreakResponseReceivedOpportunityAdapterV2"),
                 sel_registerName("didReceiveAdBreakResponse:fromAdBreakSlot:"),
                 ^void(id self, id response, id slot) {
                     os_log(ytlog(), "YTFreedom: dropped ad-break response (%@, slot=%@)",
                            response, slot);
                 });
    hookInstance(NSClassFromString(@"YTAdBreakRendererAdapter"),
                 sel_registerName("createAds"),
                 ^id(id self) {
                     os_log(ytlog(), "YTFreedom: createAds -> empty");
                     return @[];
                 });
}

static void fixFeedAds(void) {
    Class collectionVC = NSClassFromString(@"YTInnerTubeCollectionViewController");

    static IMP orig_displaySections;
    orig_displaySections = hookInstance(collectionVC,
        @selector(displaySectionsWithReloadingSectionControllerByRenderer:),
        ^void(id self, id renderer) {
            if (sectionRenderersIvarExists([self class])) {
                NSMutableArray *sections = [self valueForKey:@"_sectionRenderers"];
                if ([sections isKindOfClass:[NSArray class]])
                    [self setValue:filteredAdSections(sections) forKey:@"_sectionRenderers"];
            }
            ((void(*)(id, SEL, id))orig_displaySections)(
                self, @selector(displaySectionsWithReloadingSectionControllerByRenderer:), renderer);
        });
    (void)orig_displaySections;

    static IMP orig_addSections;
    orig_addSections = hookInstance(collectionVC,
        @selector(addSectionsFromArray:),
        ^void(id self, NSArray *array) {
            ((void(*)(id, SEL, id))orig_addSections)(
                self, @selector(addSectionsFromArray:), filteredAdSections(array));
        });
    (void)orig_addSections;

    // In-player ad overlay elements: remove the "expandable metadata"
    // (ad-info bar) and hide ad-layout containers.
    static IMP orig_didMoveToWindow;
    orig_didMoveToWindow = hookInstance(NSClassFromString(@"_ASDisplayView"),
        @selector(didMoveToWindow),
        ^void(id self) {
            ((void(*)(id, SEL))orig_didMoveToWindow)(self, @selector(didMoveToWindow));
            NSString *aid = [(UIView *)self accessibilityIdentifier];
            if ([aid isEqualToString:@"eml.expandable_metadata.vpp"]) {
                [self removeFromSuperview];
            } else if ([aid hasPrefix:@"eml.ad_layout."]) {
                [(UIView *)self setHidden:YES];
            }
        });
    (void)orig_didMoveToWindow;
}

static void fixReelAds(void) {
    // YTReelModel isAdVideo marks ad reels in Shorts.
    static BOOL (^isAdReel)(id) = ^BOOL(id model) {
        if (!model || ![model respondsToSelector:@selector(isAdVideo)]) return NO;
        return [(id<YTFreedomAdHooks>)model isAdVideo] == YES;
    };

    static IMP orig_setReels;
    orig_setReels = hookInstance(NSClassFromString(@"YTReelDataSource"),
        @selector(setReels:),
        ^void(id self, id reels) {
            if ([reels respondsToSelector:@selector(indexesOfObjectsPassingTest:)]) {
                NSIndexSet *remove = [reels indexesOfObjectsPassingTest:
                    ^BOOL(id obj, NSUInteger idx, BOOL *stop) { return isAdReel(obj); }];
                if (remove.count > 0) [reels removeObjectsAtIndexes:remove];
            }
            ((void(*)(id, SEL, id))orig_setReels)(self, @selector(setReels:), reels);
        });
    (void)orig_setReels;

    static IMP orig_insertContentModel;
    orig_insertContentModel = hookInstance(NSClassFromString(@"YTReelDataSource"),
        @selector(insertContentModel:atIndex:),
        ^void(id self, id model, NSInteger index) {
            if (isAdReel(model)) return;
            ((void(*)(id, SEL, id, NSInteger))orig_insertContentModel)(
                self, @selector(insertContentModel:atIndex:), model, index);
        });
    (void)orig_insertContentModel;
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
    fixPlayerResponseAds();
    fixFeedAds();
    fixReelAds();

    // --- sign-in fix ---
    fixSSORPCService();
    fixBundleIdentity();
    fixKeychainAccessGroups();
    fixAppGroupContainer();

    os_log(ytlog(), "YTFreedom: init complete (adblock + sign-in fix)");
}
