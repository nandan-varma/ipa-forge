/* Standalone dylib, never referenced by TestApp's load commands -- the
 * clean, unsigned Phase 4 dylib-injection target. */
int hook_function(void) {
    return 99;
}
