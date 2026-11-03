#include <stdio.h>
const char *greeting(void);
int version(void);

int main(void) {
    printf("%s, version %d\n", greeting(), version());
    return 0;
}
