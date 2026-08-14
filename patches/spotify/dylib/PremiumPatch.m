// PremiumPatch.m — the premium unlock: intercept the bootstrap and /v1/customize
// responses, rewrite the UcsResponse protobuf (account attributes -> premium,
// assigned feature values -> ads off), and replay the patched bytes. Also
// answers the premium-plan/DAC endpoints with canned responses.
//
// From-scratch implementation: the wire schema was derived by analyzing
// the Spotify binary's protobuf responses; editing uses our generic editor
// (PBProto) so the whole dylib stays plain ObjC — no Swift runtime, no
// SwiftProtobuf dependency (the Swift/Orion build was the launch-crash cause).

#import "SpotifyHook.h"
#import "PBProto.h"

// --- URL predicates ---------------------------------------------------------

static BOOL urlIsBootstrap(NSURL *url) { return [url.path containsString:@"bootstrap/v1/bootstrap"]; }
static BOOL urlIsCustomize(NSURL *url) { return [url.path containsString:@"v1/customize"]; }
static BOOL urlIsDAC(NSURL *url) { return [url.path containsString:@"/dac/view/v1/"]; }
static BOOL urlIsAccountValidate(NSURL *url) { return [url.path containsString:@"signup/public"]; }
static BOOL urlIsTrialsFacade(NSURL *url) { return [url.path containsString:@"trials-facade/start-trial"]; }
static BOOL urlIsPremiumMarketing(NSURL *url) { return [url.path containsString:@"premium-marketing/upsellOffer"]; }
static BOOL urlIsScreenConfig(NSURL *url) { return [url.path containsString:@"pses/screenconfig"]; }
static BOOL urlIsPlanRow(NSURL *url) { return [url.path containsString:@"v1/GetPremiumPlanRow"]; }
static BOOL urlIsPlanBadge(NSURL *url) { return [url.path containsString:@"GetYourPremiumBadge"]; }
static BOOL urlIsPlanOverview(NSURL *url) { return [url.path containsString:@"GetPlanOverview"]; }
static BOOL urlIsSessionInvalidation(NSURL *url) {
    NSString *p = url.path;
    return [p containsString:@"session/purge"] || [p containsString:@"token/revoke"]
        || [p containsString:@"DeleteToken"] || [p containsString:@"logout"]
        || [p containsString:@"sign-out"] || [p containsString:@"signup/public"]
        || [p containsString:@"auth/expire"];
}
static BOOL urlNeedsPatching(NSURL *url) { return urlIsBootstrap(url) || urlIsCustomize(url); }
static BOOL urlNeedsCannedResponse(NSURL *url) {
    return urlIsDAC(url) || urlIsAccountValidate(url) || urlIsTrialsFacade(url)
        || urlIsPremiumMarketing(url) || urlIsScreenConfig(url) || urlIsSessionInvalidation(url)
        || urlIsPlanRow(url) || urlIsPlanBadge(url) || urlIsPlanOverview(url);
}

// --- UcsResponse navigation -------------------------------------------------

// UcsResponse signature: contains field-1 (resolve, message) and field-3
// (attributes, message) whose children include a field-1 length-delimited
// (the accountAttributes map). Search the tree for that shape.
static NSMutableArray<PBNode *> *findUcsResponse(NSMutableArray<PBNode *> *fields) {
    for (PBNode *node in fields) {
        if (node.wireType != PBWireLen || !node.children.count) continue;
        // candidate: field 1 msg + field 3 msg with a field-1 len child
        PBNode *resolve = nil, *attrs = nil;
        for (PBNode *sub in node.children) {
            if (sub.fieldNumber == 1 && sub.wireType == PBWireLen && sub.children.count) resolve = sub;
            if (sub.fieldNumber == 3 && sub.wireType == PBWireLen && sub.children.count) attrs = sub;
        }
        if (resolve && attrs) {
            BOOL attrsHasMap = NO;
            for (PBNode *mapField in attrs.children) {
                if (mapField.fieldNumber == 1 && mapField.wireType == PBWireLen) { attrsHasMap = YES; break; }
            }
            if (attrsHasMap) return node.children;
        }
        // recurse
        for (PBNode *sub in node.children) {
            NSMutableArray *found = findUcsResponse(sub.children);
            if (found) return found;
        }
    }
    return nil;
}

// --- account attributes (modifyAttributes) ----------------------------------

static NSDateFormatter *spotISOFormatter(void) {
    static NSDateFormatter *fmt;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        fmt = [NSDateFormatter new];
        fmt.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
        fmt.timeZone = [NSTimeZone timeZoneWithAbbreviation:@"UTC"];
        fmt.dateFormat = @"yyyy-MM-dd'T'HH:mm:ss'Z'";
    });
    return fmt;
}

static NSString *spotOneYearFromNow(void) {
    NSDate *d = [[NSDate date] dateByAddingTimeInterval:365 * 24 * 60 * 60];
    return [spotISOFormatter() stringFromDate:d];
}

typedef struct { const char *key; BOOL isString; const char *stringValue; BOOL boolValue; } AttrRule;

static const AttrRule kAccountAttributeRules[] = {
    {"ads", 0, NULL, false},
    {"allow-advertising-id-transmission", 0, NULL, false},
    {"restrict-advertising-id-transmission", 0, NULL, true},
    {"can_use_superbird", 0, NULL, true},
    {"is-eligible-premium-unboxing", 0, NULL, true},
    {"offline", 0, NULL, true},
    {"on-demand", 0, NULL, true},
    {"shuffle-eligible", 0, NULL, true},
    {"social-session", 0, NULL, true},
    {"social-session-free-tier", 0, NULL, false},
    {"unrestricted", 0, NULL, true},
    {"high-bitrate", 0, NULL, true},
    {"pick-and-shuffle", 0, NULL, false},
    {"lyrics-offline", 0, NULL, true},
    {"your-library-tags", 0, NULL, true},
    {"libspotify", 0, NULL, true},
    {"mobile", 0, NULL, true},
    {"ab-ad-player-targeting", 1, "0", false},
    {"enable-crossfade-product-state", 1, "1", false},
    {"enable-gapless-product-state", 1, "1", false},
    {"catalogue", 1, "premium", false},
    {"financial-product", 1, "pr:premium,tc:0", false},
    {"name", 1, "Spotify Premium", false},
    {"nft-disabled", 1, "1", false},
    {"payments-initial-campaign", 1, "default", false},
    {"player-license", 1, "premium", false},
    {"player-license-v2", 1, "premium", false},
    {"streaming-rules", 1, "", false},
    {"type", 1, "premium", false},
    {"loudness-levels", 1, "1:-5.0,0.0,3.0:-2.0", false},
    {"offline-backup", 1, "UNRESTRICTED", false},
    {"mixing-tools", 1, "EDIT", false},
    {"jam-social-session", 1, "EXPANDED", false},
};

static const char *kAccountAttributeRemovals[] = {
    "payment-state", "last-premium-activation-date", "on-demand-trial",
    "on-demand-trial-in-progress", "smart-shuffle", "at-signal",
    "feature-set-id-masked", "strider-key", "is-eligible-for-trial",
    "is-eligible-for-upsell", "upsell-state", "ad-session-persistence",
    "ad-formats-preroll-video", "is-premium-eligible",
};

static void modifyAccountAttributes(NSMutableArray<PBNode *> *ucsFields) {
    PBNode *attrs = [PBProto messageField:ucsFields field:3];
    if (!attrs) {
        [PBProto setMessageField:ucsFields field:3 builder:^{ return @[]; } remove:NO];
        attrs = [PBProto messageField:ucsFields field:3];
    }
    NSMutableArray *map = [PBProto repeatedField:attrs.children field:1];
    if (!map.count) {
        [attrs.children addObject:[PBProto messageFieldBuilder:1 fields:@[]]];
        map = [PBProto repeatedField:attrs.children field:1];
    }

    for (size_t i = 0; i < sizeof(kAccountAttributeRules) / sizeof(kAccountAttributeRules[0]); i++) {
        const AttrRule *rule = &kAccountAttributeRules[i];
        NSString *key = [NSString stringWithUTF8String:rule->key];
        if (rule->isString) {
            NSString *value = rule->stringValue ? [NSString stringWithUTF8String:rule->stringValue] : @"";
            if ([key isEqualToString:@"product-expiry"] || [key isEqualToString:@"subscription-enddate"])
                value = spotOneYearFromNow();
            [PBProto setMapEntry:map key:key valueBuilder:^{
                return @[ [PBProto stringField:4 value:value] ];
            }];
        } else {
            [PBProto setMapEntry:map key:key valueBuilder:^{
                return @[ [PBProto varintField:2 value:rule->boolValue ? 1 : 0] ];
            }];
        }
    }
    for (size_t i = 0; i < sizeof(kAccountAttributeRemovals) / sizeof(kAccountAttributeRemovals[0]); i++) {
        [PBProto removeMapEntry:map key:[NSString stringWithUTF8String:kAccountAttributeRemovals[i]]];
    }
    for (int v = 1; v <= 100; v++) {
        [PBProto removeMapEntry:map key:[NSString stringWithFormat:@"is-premium-eligible-v%d", v]];
    }
}

// --- assigned values (propertyReplacements — essential set) -----------------

typedef enum { PVRemove, PVSetBool, PVSetEnum, PVForceBool } PVOp;

typedef struct {
    const char *name;      // NULL = any
    const char *scope;     // NULL = any
    PVOp op;
    BOOL boolValue;
    const char *enumValue;
} PVRule;

static const PVRule kPropertyRules[] = {
    // capping removal
    {"enable_common_capping", NULL, PVRemove, 0, NULL},
    {"enable_pns_common_capping", NULL, PVRemove, 0, NULL},
    {"enable_pick_and_shuffle_common_capping", NULL, PVRemove, 0, NULL},
    {"enable_pick_and_shuffle_dynamic_cap", NULL, PVRemove, 0, NULL},
    {"pick_and_shuffle_timecap", NULL, PVRemove, 0, NULL},
    {NULL, "ios-feature-queue", PVRemove, 0, NULL},
    {"enable_free_on_demand_experiment", NULL, PVRemove, 0, NULL},
    {"enable_mft_plus_queue", NULL, PVRemove, 0, NULL},
    {"enable_playback_timeout_service", NULL, PVSetBool, 0, NULL},
    {"enable_playback_timeout_error_ui", NULL, PVSetBool, 0, NULL},
    {"playback_timeout_action", NULL, PVSetEnum, 0, "Nothing"},
    // ads: master + per-surface
    {"ads", NULL, PVSetBool, 0, NULL},
    {"enable_ads", NULL, PVSetBool, 0, NULL},
    {"enable_audio_ads", NULL, PVSetBool, 0, NULL},
    {"enable_display_ads", NULL, PVSetBool, 0, NULL},
    {"enable_video_ads", NULL, PVSetBool, 0, NULL},
    {"enable_premium_upsell", NULL, PVSetBool, 0, NULL},
    {"enable_upsell", NULL, PVSetBool, 0, NULL},
    {"show_upsell", NULL, PVSetBool, 0, NULL},
    {"show_premium_upsell", NULL, PVSetBool, 0, NULL},
    {"enable_campaigns", NULL, PVSetBool, 0, NULL},
    {"enable_promotions", NULL, PVSetBool, 0, NULL},
    {"enable_search_ad", NULL, PVSetBool, 0, NULL},
    {"enable_search_ads", NULL, PVSetBool, 0, NULL},
    {"enable_search_banner_ad", NULL, PVSetBool, 0, NULL},
    {"enable_search_sponsored_ad", NULL, PVSetBool, 0, NULL},
    {"enable_home_ad", NULL, PVSetBool, 0, NULL},
    {"enable_home_ads", NULL, PVSetBool, 0, NULL},
    {"enable_home_banner_ad", NULL, PVSetBool, 0, NULL},
    {"enable_home_sponsored_ad", NULL, PVSetBool, 0, NULL},
    {"enable_now_playing_ad", NULL, PVSetBool, 0, NULL},
    {"enable_now_playing_ads", NULL, PVSetBool, 0, NULL},
    {"enable_now_playing_banner_ad", NULL, PVSetBool, 0, NULL},
    {"enable_now_playing_sponsored_ad", NULL, PVSetBool, 0, NULL},
    {"enable_artist_ad", NULL, PVSetBool, 0, NULL},
    {"enable_artist_ads", NULL, PVSetBool, 0, NULL},
    {"enable_playlist_ad", NULL, PVSetBool, 0, NULL},
    {"enable_playlist_ads", NULL, PVSetBool, 0, NULL},
    {"enable_album_ad", NULL, PVSetBool, 0, NULL},
    {"enable_album_ads", NULL, PVSetBool, 0, NULL},
    {"enable_library_ad", NULL, PVSetBool, 0, NULL},
    {"enable_library_ads", NULL, PVSetBool, 0, NULL},
    {"enable_audiobook_ad", NULL, PVSetBool, 0, NULL},
    {"enable_audiobook_ads", NULL, PVSetBool, 0, NULL},
    {"enable_podcast_ad", NULL, PVSetBool, 0, NULL},
    {"enable_podcast_ads", NULL, PVSetBool, 0, NULL},
    {"enable_sponsored_content", NULL, PVSetBool, 0, NULL},
    {"enable_sponsored_playlists", NULL, PVSetBool, 0, NULL},
    {"enable_sponsored_sessions", NULL, PVSetBool, 0, NULL},
    {"enable_sponsored_stories", NULL, PVSetBool, 0, NULL},
    {"enable_sponsored_videos", NULL, PVSetBool, 0, NULL},
    {"enable_popups", NULL, PVSetBool, 0, NULL},
    {"enable_interstitials", NULL, PVSetBool, 0, NULL},
    {"enable_overlays", NULL, PVSetBool, 0, NULL},
    {"enable_billboard", NULL, PVSetBool, 0, NULL},
    {"enable_billboards", NULL, PVSetBool, 0, NULL},
    {"enable_audio_ads_player", NULL, PVSetBool, 0, NULL},
    {"enable_display_ads_player", NULL, PVSetBool, 0, NULL},
    {"enable_video_ads_player", NULL, PVSetBool, 0, NULL},
    // ad scopes (remove whole scope)
    {NULL, "ios-ad-on-app-open", PVRemove, 0, NULL},
    {NULL, "ios-feature-adonappopen", PVRemove, 0, NULL},
    {NULL, "marquee", PVRemove, 0, NULL},
    {NULL, "ios-feature-marquee", PVRemove, 0, NULL},
    {NULL, "leavebehindadsbase", PVRemove, 0, NULL},
    {NULL, "ios-feature-leavebehindadsbase", PVRemove, 0, NULL},
    {NULL, "ios-feature-instreamads", PVRemove, 0, NULL},
    {NULL, "ios-feature-adsswift", PVRemove, 0, NULL},
    {NULL, "ios-feature-adsidentitytracking", PVRemove, 0, NULL},
    {"ad_on_app_open_enabled", NULL, PVSetBool, 0, NULL},
    {"is_ad_on_app_open_enabled", NULL, PVSetBool, 0, NULL},
    {"enable_leave_behind_ads_card_element", NULL, PVSetBool, 0, NULL},
    {"music_npv_leavebehinds_enabled", NULL, PVSetBool, 0, NULL},
    // lyrics share (premium-gated)
    {"enable_lyrics_share", NULL, PVForceBool, 1, NULL},
    {"lyrics_share_enabled", NULL, PVForceBool, 1, NULL},
    {"lyrics_shareable", NULL, PVForceBool, 1, NULL},
    {"enable_sharing_v2", NULL, PVForceBool, 1, NULL},
    {"enable_share_link_preview_uploads", NULL, PVForceBool, 1, NULL},
    // misc
    {"should_nova_scroll_use_scrollsita", NULL, PVRemove, 0, NULL},
};

static void modifyAssignedValues(NSMutableArray<PBNode *> *ucsFields) {
    PBNode *resolve = [PBProto messageField:ucsFields field:1];
    if (!resolve) return;
    PBNode *configuration = [PBProto messageField:resolve.children field:1];
    if (!configuration) return;
    NSMutableArray *values = [PBProto repeatedField:configuration.children field:3];
    if (!values.count) return;

    for (size_t i = 0; i < sizeof(kPropertyRules) / sizeof(kPropertyRules[0]); i++) {
        const PVRule *rule = &kPropertyRules[i];
        NSString *ruleName = rule->name ? [NSString stringWithUTF8String:rule->name] : nil;
        NSString *ruleScope = rule->scope ? [NSString stringWithUTF8String:rule->scope] : nil;

        // match indices
        NSMutableIndexSet *matches = [NSMutableIndexSet indexSet];
        [values enumerateObjectsUsingBlock:^(PBNode *value, NSUInteger idx, BOOL *stop) {
            PBNode *propID = [PBProto messageField:value.children field:1];
            NSString *scope = nil, *name = nil;
            if (propID) {
                scope = [PBProto stringValue:[PBProto messageField:propID.children field:1]];
                name = [PBProto stringValue:[PBProto messageField:propID.children field:2]];
            }
            BOOL nameOK = !ruleName || [name isEqualToString:ruleName];
            BOOL scopeOK = !ruleScope || [scope isEqualToString:ruleScope];
            if (nameOK && scopeOK) [matches addIndex:idx];
        }];

        if (matches.count == 0 && rule->op == PVForceBool) {
            // append a new AssignedValue
            NSMutableArray *propFields = [NSMutableArray array];
            if (ruleScope) [propFields addObject:[PBProto stringField:1 value:ruleScope]];
            if (ruleName) [propFields addObject:[PBProto stringField:2 value:ruleName]];
            [values addObject:[PBProto messageFieldBuilder:3 fields:@[
                [PBProto messageFieldBuilder:1 fields:propFields],
                [PBProto messageFieldBuilder:3 fields:@[ [PBProto varintField:1 value:rule->boolValue ? 1 : 0] ]],
            ]]];
            continue;
        }

        [matches enumerateIndexesWithOptions:NSEnumerationReverse usingBlock:^(NSUInteger idx, BOOL *stop) {
            PBNode *value = values[idx];
            switch (rule->op) {
                case PVRemove: {
                    [values removeObjectAtIndex:idx];
                    break;
                }
                case PVSetBool:
                case PVForceBool: {
                    // replace oneof value with boolValue (field 3)
                    [PBProto removeField:value.children field:3];
                    [PBProto removeField:value.children field:4];
                    [PBProto removeField:value.children field:5];
                    [value.children addObject:[PBProto messageFieldBuilder:3 fields:@[
                        [PBProto varintField:1 value:rule->boolValue ? 1 : 0]
                    ]]];
                    break;
                }
                case PVSetEnum: {
                    [PBProto removeField:value.children field:3];
                    [PBProto removeField:value.children field:4];
                    [PBProto removeField:value.children field:5];
                    [value.children addObject:[PBProto messageFieldBuilder:4 fields:@[
                        [PBProto stringField:1 value:[NSString stringWithUTF8String:rule->enumValue]]
                    ]]];
                    break;
                }
            }
        }];
    }
}

static NSData *spotPatchUcsData(NSData *data) {
    NSMutableArray *top = [PBProto parse:data];
    NSMutableArray *ucsFields = nil;

    // Bootstrap: wrapper(2) -> oneMoreWrapper(1) -> message(1) -> CustomizeMessage
    PBNode *wrapper = [PBProto messageField:top field:2];
    if (wrapper) {
        PBNode *oneMore = [PBProto messageField:wrapper.children field:1];
        if (oneMore) {
            PBNode *message = [PBProto messageField:oneMore.children field:1];
            if (message) ucsFields = findUcsResponse(message.children);
        }
    }
    if (!ucsFields) ucsFields = findUcsResponse(top); // customize: response at top level

    if (!ucsFields) {
        os_log(spotLog(), "SpotifyMod: could not locate UcsResponse (%lu bytes)", (unsigned long)data.length);
        return data;
    }

    modifyAccountAttributes(ucsFields);
    modifyAssignedValues(ucsFields);
    NSData *patched = [PBProto serialize:top];
    os_log(spotLog(), "SpotifyMod: patched bootstrap/customize (%lu -> %lu bytes)", (unsigned long)data.length, (unsigned long)patched.length);
    return patched;
}

// --- canned responses -------------------------------------------------------

// PremiumPlanRow: {3: planName, 18: planIdentifier, 4: colorCode}
static NSData *spotPlanRowData(void) {
    NSArray *fields = @[
        [PBProto stringField:3 value:@"SpotifyMod"],
        [PBProto stringField:18 value:@"SpotifyMod"],
        [PBProto stringField:4 value:@"#FFD2D7"],
    ];
    return [PBProto serialize:fields];
}

// YourPremiumBadge: {1: name, 2: version, 3: colorCode}
static NSData *spotPlanBadgeData(void) {
    NSArray *fields = @[
        [PBProto stringField:1 value:@"SpotifyMod"],
        [PBProto varintField:2 value:2],
        [PBProto stringField:3 value:@"#FFD2D7"],
    ];
    return [PBProto serialize:fields];
}

// SpotifyPlan: {1: subscription, 2: notice}
static NSData *spotPlanOverviewData(void) {
    NSArray *features = @[
        [PBProto messageFieldBuilder:20 fields:@[
            [PBProto varintField:1 value:1], // icon = check
            [PBProto stringField:2 value:@"Ad-free music listening"],
            [PBProto stringField:4 value:@"#1ED760"],
        ]],
        [PBProto messageFieldBuilder:20 fields:@[
            [PBProto varintField:1 value:1],
            [PBProto stringField:2 value:@"Play songs in any order"],
            [PBProto stringField:4 value:@"#1ED760"],
        ]],
        [PBProto messageFieldBuilder:20 fields:@[
            [PBProto varintField:1 value:1],
            [PBProto stringField:2 value:@"Organize your listening queue"],
            [PBProto stringField:4 value:@"#1ED760"],
        ]],
    ];
    NSArray *subscription = @[
        [PBProto varintField:2 value:2],
        [PBProto stringField:3 value:@"SpotifyMod"],
        [PBProto stringField:4 value:@"SpotifyMod"],
        [PBProto stringField:5 value:@"#FFD2D7"],
    ];
    NSArray *notice = @[
        [PBProto stringField:1 value:@"You are on the SpotifyMod plan"],
        [PBProto varintField:7 value:2], // subscription status
    ];
    NSArray *top = @[
        [PBProto messageFieldBuilder:1 fields:subscription],
        [PBProto messageFieldBuilder:2 fields:notice],
    ];
    // features belong inside subscription (field 20), not top-level
    NSMutableArray *subWithFeatures = [subscription mutableCopy];
    [subWithFeatures addObjectsFromArray:features];
    return [PBProto serialize:@[
        [PBProto messageFieldBuilder:1 fields:subWithFeatures],
        [PBProto messageFieldBuilder:2 fields:notice],
    ]];
    (void)top;
}

static NSData *spotCannedResponse(NSURL *url) {
    if (urlIsDAC(url)) return [NSData data]; // "no ad to render"
    if (urlIsAccountValidate(url))
        return [@"{\"status\":1,\"country\":\"US\",\"is_country_launched\":true}" dataUsingEncoding:NSUTF8StringEncoding];
    if (urlIsTrialsFacade(url))
        return [@"{\"result\":\"NOT_ELIGIBLE\"}" dataUsingEncoding:NSUTF8StringEncoding];
    if (urlIsPremiumMarketing(url) || urlIsScreenConfig(url))
        return [@"{}" dataUsingEncoding:NSUTF8StringEncoding];
    if (urlIsSessionInvalidation(url))
        return [@"{\"status\":\"OK\"}" dataUsingEncoding:NSUTF8StringEncoding];
    if (urlIsPlanRow(url)) return spotPlanRowData();
    if (urlIsPlanBadge(url)) return spotPlanBadgeData();
    if (urlIsPlanOverview(url)) return spotPlanOverviewData();
    return nil;
}

// --- URLSession interception ------------------------------------------------

static const void *kBufferKey = &kBufferKey;
static NSMutableDictionary<NSNumber *, NSData *> *sptBufferCache(void) {
    static NSMutableDictionary *cache;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ cache = [NSMutableDictionary dictionary]; });
    return cache;
}

// Installs the intercept on a URLSession data-delegate class.
static void hookURLSessionDelegate(Class cls) {
    if (!cls) return;

    __block IMP orig_didReceiveData = NULL;
    orig_didReceiveData = sptHookInstance(cls,
        @selector(URLSession:dataTask:didReceiveData:),
        ^void(id self, NSURLSession *session, NSURLSessionDataTask *task, NSData *data) {
            if (!orig_didReceiveData) return;
            NSURL *url = task.currentRequest.URL ?: task.originalRequest.URL;
            if (urlNeedsPatching(url)) {
                @synchronized (sptBufferCache()) {
                    NSData *cached = sptBufferCache()[@(task.taskIdentifier)];
                    NSMutableData *buffer = (NSMutableData *)cached;
                    if (!buffer) { buffer = [NSMutableData data]; sptBufferCache()[@(task.taskIdentifier)] = buffer; }
                    [buffer appendData:data];
                }
                return; // hold the response until completion
            }
            if (urlNeedsCannedResponse(url)) {
                NSData *canned = spotCannedResponse(url);
                if (canned) {
                    ((void(*)(id, SEL, id, id, id))orig_didReceiveData)(
                        self, @selector(URLSession:dataTask:didReceiveData:), session, task, canned);
                    return;
                }
            }
            ((void(*)(id, SEL, id, id, id))orig_didReceiveData)(
                self, @selector(URLSession:dataTask:didReceiveData:), session, task, data);
        });

    __block IMP orig_didComplete = NULL;
    orig_didComplete = sptHookInstance(cls,
        @selector(URLSession:task:didCompleteWithError:),
        ^void(id self, NSURLSession *session, NSURLSessionDataTask *task, NSError *error) {
            if (!orig_didComplete || !orig_didReceiveData) return;
            NSURL *url = task.currentRequest.URL ?: task.originalRequest.URL;
            if (urlNeedsPatching(url)) {
                NSData *buffer;
                @synchronized (sptBufferCache()) {
                    buffer = sptBufferCache()[@(task.taskIdentifier)];
                    [sptBufferCache() removeObjectForKey:@(task.taskIdentifier)];
                }
                if (buffer && !error) {
                    NSData *patched = spotPatchUcsData(buffer);
                    ((void(*)(id, SEL, id, id, id))orig_didReceiveData)(
                        self, @selector(URLSession:dataTask:didReceiveData:), session, task, patched);
                }
                ((void(*)(id, SEL, id, id, id))orig_didComplete)(
                    self, @selector(URLSession:task:didCompleteWithError:), session, task, nil);
                return;
            }
            ((void(*)(id, SEL, id, id, id))orig_didComplete)(
                self, @selector(URLSession:task:didCompleteWithError:), session, task, error);
        });
}

void SpotifyPremiumPatchInit(void) {
    if (!smEnabled(kSMPremium)) { os_log(spotLog(), "SpotifyMod: premium patch disabled"); return; }
    // The bootstrap/customize traffic flows through one of these (SPTDataLoaderService
    // lives in SpotifyShared.framework; SPTCoreURLSessionDataDelegate is the
    // 9.1.x core path). Hook both — the active one wins.
    hookURLSessionDelegate(NSClassFromString(@"SPTDataLoaderService"));
    hookURLSessionDelegate(NSClassFromString(@"SPTCoreURLSessionDataDelegate"));
}
