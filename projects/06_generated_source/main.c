#include <stdio.h>
#include "parse.h"
int lex(void);

int main(void) {
    printf("tokens=%d parsed=%d\n", lex(), parse(lex()));
    return 0;
}
