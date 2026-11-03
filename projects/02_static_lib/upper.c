#include "textutil.h"
void to_upper(char *s) {
    for (; *s; s++)
        if (*s >= 'a' && *s <= 'z') *s -= 32;
}
