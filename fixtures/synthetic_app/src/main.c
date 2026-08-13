extern int test_framework_function(void);

/* The byte sequence returned here is the binary_replace target in
 * fixtures/patches/example.yaml -- it must appear exactly once in the
 * compiled executable for the example patch's expected_matches: 1 to hold. */
static const unsigned char marker[16] = {
    0xCA, 0xFE, 0xF0, 0x0D, 0xDE, 0xAD, 0xBE, 0xEF,
    0x13, 0x37, 0xC0, 0xDE, 0xAB, 0xCD, 0xEF, 0x01,
};

int check_marker(void) {
    return marker[0] == 0xCA;
}

int main(void) {
    return test_framework_function() + check_marker();
}
