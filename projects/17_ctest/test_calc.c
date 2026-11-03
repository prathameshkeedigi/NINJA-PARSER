#include <stdio.h>
#include "calc.h"

int main(void) {
    int ok = square(3) == 9 && square(-2) == 4;
    printf("test %s\n", ok ? "passed" : "FAILED");
    return ok ? 0 : 1;
}
