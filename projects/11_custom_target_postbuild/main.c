#include <stdio.h>
int x(void);
int y(void);

int main(void) {
    printf("x+y=%d\n", x() + y());
    return 0;
}
