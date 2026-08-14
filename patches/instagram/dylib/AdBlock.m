// AdBlock.m — ad + distraction removal.
//
// Two layers, both verified against the 442.0.0 binary:
//   1. Kill the ad response parsers at the source (return nil) — the same
//      approach SCInsta proved on IGStoryAdsResponseParser /
//      IGSundialAdsResponseParser; 442.0.0 has a whole intent-aware family.
//   2. Filter the rendered feed list (IGMainFeedListAdapterDataSource
//      -objectsForListAdapter:) for anything that slipped through:
//      IGAdItem / IGMedia.isMediaAd, suggested posts (explorePostInFeed),
//      suggested reels carousels, suggested accounts, and the story tray
//      (IGStoryDataController, the opt-in "hide story tray").
#import "IGModHook.h"

static Class igClass(const char *name) { return NSClassFromString(@(name)); }

// --- list filtering ----------------------------------------------------------

static NSArray *igFilterFeedList(NSArray *items) {
    if (![items isKindOfClass:NSArray.class] || !items.count) return items;
    BOOL hideAds = igEnabled(kIGHideAds);
    BOOL hideTray = igEnabled(kIGHideStoryTray);
    BOOL noPosts = igEnabled(kIGNoSuggestedPosts);
    BOOL noReels = igEnabled(kIGNoSuggestedReels);
    BOOL noAccounts = igEnabled(kIGNoSuggestedAccounts);
    if (!hideAds && !hideTray && !noPosts && !noReels && !noAccounts) return items;

    Class adItemCls = igClass("IGAdItem");
    Class mediaCls = igClass("IGMedia");
    Class storyDataCls = igClass("IGStoryDataController");
    Class clipsCls = igClass("IGFeedScrollableClipsModel");
    Class aymfCls = igClass("IGHScrollAYMFModel");
    SEL isMediaAd = NSSelectorFromString(@"isMediaAd");
    SEL explorePost = NSSelectorFromString(@"explorePostInFeed");

    NSMutableArray *kept = [NSMutableArray arrayWithCapacity:items.count];
    for (id obj in items) {
        BOOL drop = NO;
        if (hideAds && adItemCls && [obj isKindOfClass:adItemCls]) drop = YES;
        if (!drop && hideAds && mediaCls && [obj isKindOfClass:mediaCls] && igBool(obj, isMediaAd)) drop = YES;
        if (!drop && noPosts && mediaCls && [obj isKindOfClass:mediaCls]
            && [igObj(obj, explorePost) isEqual:@YES]) drop = YES;
        if (!drop && noReels && clipsCls && [obj isKindOfClass:clipsCls]) drop = YES;
        if (!drop && noAccounts && aymfCls && [obj isKindOfClass:aymfCls]) drop = YES;
        if (!drop && hideTray && storyDataCls && [obj isKindOfClass:storyDataCls]) drop = YES;
        if (!drop) [kept addObject:obj];
    }
    if (kept.count == items.count) return items;
    os_log(igLog(), "IGMod: filtered %lu -> %lu feed items", (unsigned long)items.count, (unsigned long)kept.count);
    return kept;
}

static void hookFeedListAdapter(Class cls) {
    if (!cls) return;
    __block IMP orig = NULL;
    orig = igHookInstance(cls, @selector(objectsForListAdapter:),
        ^id(id self, id adapter) {
            NSArray *items = orig ? ((id (*)(id, SEL, id))orig)(self, @selector(objectsForListAdapter:), adapter) : @[];
            return igFilterFeedList(items);
        });
}

// --- response-parser kill switches -------------------------------------------
// Returning nil means "no ad payload" — the pattern SCInsta shipped for the
// story/sundial parsers. The feed UI then renders no ad slots for that
// response.

static void hookParserNil(Class cls) {
    if (!cls) return;
    __block IMP orig = NULL;
    orig = igHookInstance(cls, @selector(parsedObjectFromResponse:),
        ^id(id self, id response) {
            if (igEnabled(kIGHideAds)) return nil;
            return orig ? ((id (*)(id, SEL, id))orig)(self, @selector(parsedObjectFromResponse:), response) : nil;
        });
}

void IGAdBlockInit(void) {
    // Feed rendering (main feed list adapter — the only list adapter that
    // still parses in 442.0.0; the reels/explore/chaining adapters from
    // SCInsta are gone and covered by the parser hooks below).
    hookFeedListAdapter(igClass("IGMainFeedListAdapterDataSource"));

    // Ads at the source: every *AdsResponseParser in the 442.0.0 binary.
    const char *parsers[] = {
        "IGStoryAdsResponseParser",
        "IGSundialAdsResponseParser",
        "IGIntentAwareFeedAdsResponseParser",
        "IGIntentAwareStoryAdsResponseParser",
        "IGIntentAwareSundialAdsResponseParser",
        "IGExploreAdsResponseParser",
        "IGSearchFeedAdsResponseParser",
        "IGProfileAdsResponseParser",
        "IGHighIntentDiscoveryStoryAdsResponseParser",
    };
    for (size_t i = 0; i < sizeof(parsers) / sizeof(parsers[0]); i++) {
        hookParserNil(igClass(parsers[i]));
    }
}
