// SettingsCleaner.m — hide sections from the app's Settings screen.
//
// YTSettingsSectionItemManager builds each settings section with an
// update<Name>SectionWithEntry: method (the same class that hosts our
// YTFreedom section). No-op the ones the user hides (uYouPlus approach; all
// selectors verified present in 21.32.4). Selector names are literal via
// sel_registerName so the hooks manifest generator can verify them.

#import "YTFreedom.h"

void YTFreedomSettingsCleanerInit(void) {
    if (IS_ENABLED(KHideSAccountSection)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateAccountSwitcherSectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSAutoplaySection)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateAutoplaySectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSTryNewFeatures)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updatePremiumEarlyAccessSectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSVideoQualityPrefs)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateVideoQualitySectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSNotifications)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateNotificationSectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSManageHistory)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateHistorySectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSYourData)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateYourDataSectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSPrivacy)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updatePrivacySectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
    if (IS_ENABLED(KHideSLiveChat)) {
        static IMP orig;
        orig = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
            sel_registerName("updateLiveChatSectionWithEntry:"),
            ^void(id self, id entry) { /* hidden */ });
        (void)orig;
    }
}
