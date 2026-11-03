#include <stdio.h>
const char *info(void);
int feature(void);

int main(void) {
    printf("%s feature_x=%d\n", info(), feature());
    return 0;
}
