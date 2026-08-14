// AdBlock.m — HUB JSON ad-component filter. Ported from EeveeSpotify's
// HubsAdBlocker (GPL). HUB (HubFramework) pages are JSON trees; ad cards
// (display-ad-card, sponsored shelves, marquee, etc.) are components whose
// namespace/name/id/type/metadata match ad keywords. Hook
// HUBViewModelBuilderImplementation addJSONDictionary: to strip them before
// the view model builds. Pure ObjC; no feature flags involved.

#import "SpotifyHook.h"

static NSArray<NSString *> *adKeywords(void) {
    return @[
        @"ad", @"ads", @"sponsored", @"upsell", @"campaign", @"promoted",
        @"premium-upsell", @"merch", @"ticket", @"billboard", @"banner",
        @"interstitial", @"overlay", @"marquee", @"leavebehind", @"leave-behind",
        @"displayad", @"display-ad", @"fullbleed", @"full-bleed", @"leaderboard",
        @"advertisement", @"sponsor", @"promo", @"native-ad", @"mobile-ads",
        @"on-surface", @"onsurface", @"search-ad", @"home-ad", @"sponsored-content",
        @"sponsored-ad", @"ad-card", @"native-ad-home-shelf", @"sponsored-shelf",
        @"sponsored-row", @"ad-shelf", @"ad-row", @"sponsored-item", @"ad-item",
        @"merchandising", @"upgrade-component", @"offer", @"marketing",
        @"mobile-display-ad-card", @"mobile-ads-display-ad-element",
    ];
}

static BOOL containsAdKeyword(NSString *str) {
    NSString *lower = str.lowercaseString;
    for (NSString *kw in adKeywords()) {
        if ([lower containsString:kw]) return YES;
    }
    return NO;
}

static BOOL isAdComponent(NSDictionary *component) {
    // "component": {"namespace": ..., "name": ...} or a plain "mobile:display-ad-card"
    id comp = component[@"component"];
    if ([comp isKindOfClass:[NSDictionary class]]) {
        NSString *ns = comp[@"namespace"];
        NSString *name = comp[@"name"];
        if ([ns isKindOfClass:[NSString class]] && containsAdKeyword(ns)) return YES;
        if ([name isKindOfClass:[NSString class]] && containsAdKeyword(name)) return YES;
    } else if ([comp isKindOfClass:[NSString class]]) {
        if (containsAdKeyword((NSString *)comp)) return YES;
    }
    for (NSString *key in @[ @"id", @"type", @"title", @"subtitle", @"header" ]) {
        id value = component[key];
        if ([value isKindOfClass:[NSString class]] && containsAdKeyword((NSString *)value)) return YES;
    }
    for (NSString *dictKey in @[ @"metadata", @"logging", @"custom" ]) {
        id dict = component[dictKey];
        if ([dict isKindOfClass:[NSDictionary class]]) {
            if ([dict[@"ad"] boolValue] || [dict[@"is_ad"] boolValue] || [dict[@"is_sponsored"] boolValue])
                return YES;
            for (NSString *k in [dict allKeys])
                if (containsAdKeyword(k)) return YES;
            for (id v in [dict allValues])
                if ([v isKindOfClass:[NSString class]] && containsAdKeyword(v)) return YES;
        }
    }
    id text = component[@"text"];
    if ([text isKindOfClass:[NSDictionary class]]) {
        for (id v in [text allValues]) {
            if ([v isKindOfClass:[NSString class]] && containsAdKeyword(v)) return YES;
            if ([v isKindOfClass:[NSDictionary class]]) {
                for (id v2 in [v allValues])
                    if ([v2 isKindOfClass:[NSString class]] && containsAdKeyword(v2)) return YES;
            }
        }
    }
    return NO;
}

static NSArray *filterComponents(NSArray *components) {
    NSMutableArray *result = [NSMutableArray array];
    for (id raw in components) {
        if (![raw isKindOfClass:[NSDictionary class]]) { [result addObject:raw]; continue; }
        NSMutableDictionary *component = [raw mutableCopy];
        if (isAdComponent(component)) continue;
        for (NSString *key in @[ @"children", @"rows", @"body", @"overlays", @"sections" ]) {
            id nested = component[key];
            if ([nested isKindOfClass:[NSArray class]]) component[key] = filterComponents(nested);
        }
        [result addObject:component];
    }
    return result;
}

static void fixHUBAdFilter(void) {
    static IMP orig_addJSONDictionary;
    orig_addJSONDictionary = sptHookInstance(
        NSClassFromString(@"HUBViewModelBuilderImplementation"),
        @selector(addJSONDictionary:),
        ^void(id self, NSDictionary *dictionary) {
            if (![dictionary isKindOfClass:[NSDictionary class]]) {
                ((void(*)(id, SEL, id))orig_addJSONDictionary)(
                    self, @selector(addJSONDictionary:), dictionary);
                return;
            }
            NSMutableDictionary *mutable = [dictionary mutableCopy];
            for (NSString *key in @[ @"body", @"overlays", @"sections", @"children", @"rows" ]) {
                id nested = mutable[key];
                if ([nested isKindOfClass:[NSArray class]]) mutable[key] = filterComponents(nested);
            }
            if ([mutable[@"header"] isKindOfClass:[NSDictionary class]]) {
                NSMutableDictionary *header = [mutable[@"header"] mutableCopy];
                if (isAdComponent(header)) {
                    [mutable removeObjectForKey:@"header"];
                } else if ([header[@"children"] isKindOfClass:[NSArray class]]) {
                    header[@"children"] = filterComponents(header[@"children"]);
                    mutable[@"header"] = header;
                }
            }
            ((void(*)(id, SEL, id))orig_addJSONDictionary)(
                self, @selector(addJSONDictionary:), mutable);
        });
    (void)orig_addJSONDictionary;
}

void SpotifyAdBlockInit(void) {
    fixHUBAdFilter();
}
