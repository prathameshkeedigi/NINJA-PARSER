#include "textutil.h"
int count_char(const char *s, char c) {
    int n = 0;
    for (; *s; s++) n += (*s == c);
    return n;
}
