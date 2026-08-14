// Helpers.m — shared UI helpers: top-most VC lookup, toast, share sheet.
#import "IGModHook.h"

UIViewController *igTopMostViewController(void) {
    UIWindow *window = nil;
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if ([scene isKindOfClass:UIWindowScene.class] && scene.activationState == UISceneActivationStateForegroundActive) {
            window = ((UIWindowScene *)scene).windows.firstObject;
            if (window) break;
        }
    }
    if (!window) return nil;
    UIViewController *top = window.rootViewController;
    while (top.presentedViewController) top = top.presentedViewController;
    if ([top isKindOfClass:UINavigationController.class]) {
        UIViewController *visible = ((UINavigationController *)top).visibleViewController;
        if (visible) top = visible;
    }
    return top;
}

// --- toast --------------------------------------------------------------------

static UILabel *igToastLabel(void) {
    static UILabel *label;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        label = [UILabel new];
        label.font = [UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
        label.textColor = UIColor.whiteColor;
        label.textAlignment = NSTextAlignmentCenter;
        label.numberOfLines = 0;
    });
    return label;
}

void igShowToast(NSString *message) {
    dispatch_async(dispatch_get_main_queue(), ^{
        UIViewController *top = igTopMostViewController();
        UIView *host = top.view;
        if (!host) return;
        UIView *toast = [UIView new];
        toast.backgroundColor = [UIColor colorWithWhite:0.1 alpha:0.92];
        toast.layer.cornerRadius = 12;
        toast.layer.masksToBounds = YES;
        UIActivityIndicatorView *spinner =
            [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
        spinner.color = UIColor.whiteColor;
        [spinner startAnimating];
        UILabel *label = igToastLabel();
        label.text = message;
        [toast addSubview:spinner];
        [toast addSubview:label];
        [host addSubview:toast];
        toast.translatesAutoresizingMaskIntoConstraints = NO;
        [NSLayoutConstraint activateConstraints:@[
            [toast.centerXAnchor constraintEqualToAnchor:host.centerXAnchor],
            [toast.centerYAnchor constraintEqualToAnchor:host.centerYAnchor constant:-40],
            [toast.widthAnchor constraintLessThanOrEqualToConstant:260],
        ]];
        spinner.translatesAutoresizingMaskIntoConstraints = NO;
        label.translatesAutoresizingMaskIntoConstraints = NO;
        [NSLayoutConstraint activateConstraints:@[
            [spinner.leadingAnchor constraintEqualToAnchor:toast.leadingAnchor constant:16],
            [spinner.centerYAnchor constraintEqualToAnchor:toast.centerYAnchor],
            [label.leadingAnchor constraintEqualToAnchor:spinner.trailingAnchor constant:10],
            [label.trailingAnchor constraintEqualToAnchor:toast.trailingAnchor constant:-16],
            [label.topAnchor constraintEqualToAnchor:toast.topAnchor constant:12],
            [label.bottomAnchor constraintEqualToAnchor:toast.bottomAnchor constant:-12],
        ]];
        [UIView animateWithDuration:0.2 animations:^{ toast.alpha = 1; }];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.2 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            [UIView animateWithDuration:0.3 animations:^{ toast.alpha = 0; }
                             completion:^(BOOL fin) { if (fin) [toast removeFromSuperview]; }];
        });
    });
}

// --- share --------------------------------------------------------------------

void igShareRemoteURL(NSURL *url, NSString *toastMessage) {
    if (!url) { igShowToast(@"Could not resolve media URL"); return; }
    igShowToast(toastMessage);
    NSURLSessionDownloadTask *task = [[NSURLSession sharedSession] downloadTaskWithURL:url
        completionHandler:^(NSURL *location, NSURLResponse *response, NSError *error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                UIViewController *top = igTopMostViewController();
                if (error || !location) {
                    // Fall back to sharing the remote URL itself (Copy Link
                    // still works without a download).
                    UIActivityViewController *vc = [[UIActivityViewController alloc]
                        initWithActivityItems:@[url] applicationActivities:nil];
                    if (top) [top presentViewController:vc animated:YES completion:nil];
                    return;
                }
                NSString *ext = [[url lastPathComponent] pathExtension].length
                    ? [[url lastPathComponent] pathExtension] : (response.suggestedFilename.pathExtension.length
                        ? response.suggestedFilename.pathExtension : @"jpg");
                NSString *tmp = [NSTemporaryDirectory()
                    stringByAppendingPathComponent:[NSString stringWithFormat:@"igmod-%@.%@",
                        [[NSProcessInfo processInfo] globallyUniqueString], ext]];
                NSError *copyErr = nil;
                [[NSFileManager defaultManager] moveItemAtURL:location toURL:[NSURL fileURLWithPath:tmp] error:&copyErr];
                UIActivityViewController *vc = [[UIActivityViewController alloc]
                    initWithActivityItems:@[[NSURL fileURLWithPath:tmp]] applicationActivities:nil];
                if (top) {
                    vc.popoverPresentationController.sourceView = top.view;
                    vc.popoverPresentationController.sourceRect = CGRectMake(top.view.bounds.size.width / 2,
                        top.view.bounds.size.height / 2, 1, 1);
                    [top presentViewController:vc animated:YES completion:nil];
                }
            });
        }];
    [task resume];
}
