#include <stdio.h>
#include "core.h"
int helper(void);

int main(void) {
    printf("one=%d two=%d helper=%d\n", core_one(), core_two(), helper());
    return 0;
}
