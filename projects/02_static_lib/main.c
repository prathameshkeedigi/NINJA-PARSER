#include <stdio.h>
#include "textutil.h"

int main(void) {
    char word[] = "banana";
    int a = count_char(word, 'a');
    to_upper(word);
    printf("%s has %d a's\n", word, a);
    return 0;
}
