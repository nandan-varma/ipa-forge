// CopyText.m — long-press to copy captions / description text.
//
// IGCoreTextView in 442.0.0 no longer exposes a plain `text` property — the
// caption lives in `styledString` (IGStyledString, verified) as an attributed
// string. Long-press copies its plain-text form to the pasteboard.
#import "IGModHook.h"

// Gesture target: holds a weak reference to the text view and copies its
// styledString's attributed string when the long-press fires.
@interface IGTextViewCopyTarget : NSObject
- (instancetype)initWithView:(UIView *)view;
- (void)copyAction:(UILongPressGestureRecognizer *)sender;
@end

@implementation IGTextViewCopyTarget {
    __weak UIView *_view;
}
- (instancetype)initWithView:(UIView *)view { self = [super init]; _view = view; return self; }
- (void)copyAction:(UILongPressGestureRecognizer *)sender {
    if (sender.state != UIGestureRecognizerStateBegan || !_view) return;
    id styled = igObj(_view, NSSelectorFromString(@"styledString"));
    NSAttributedString *attr = igObj(styled, NSSelectorFromString(@"attributedString"));
    NSString *text = attr.string ?: @"";
    // Trim trailing hashtags the way SCInsta does, then copy.
    NSRegularExpression *regex = [NSRegularExpression
        regularExpressionWithPattern:@"\\s*(?:#[^\\s]+\\s*)+$" options:0 error:nil];
    NSString *result = [regex stringByReplacingMatchesInString:text options:0
        range:NSMakeRange(0, text.length)
        withTemplate:@""];
    result = [result stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!result.length) return;
    [UIPasteboard generalPasteboard].string = result;
    igShowToast(@"Copied caption");
}
@end

void IGCopyTextInit(void) {
    Class coreTextCls = NSClassFromString(@"IGCoreTextView");
    if (!coreTextCls || !igEnabled(kIGCopyCaptions)) return;

    __block IMP orig = NULL;
    orig = igHookInstance(coreTextCls, @selector(didMoveToSuperview),
        ^void(id self) {
            if (orig) ((void (*)(id, SEL))orig)(self, @selector(didMoveToSuperview));
            for (UIGestureRecognizer *g in ((UIView *)self).gestureRecognizers) {
                if ([g isKindOfClass:UILongPressGestureRecognizer.class]) return; // one per view
            }
            IGTextViewCopyTarget *target = [[IGTextViewCopyTarget alloc] initWithView:self];
            UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc]
                initWithTarget:target action:@selector(copyAction:)];
            lp.minimumPressDuration = 0.5;
            [((UIView *)self) addGestureRecognizer:lp];
        });
}
