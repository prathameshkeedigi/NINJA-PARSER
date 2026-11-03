#include <stdio.h>

/* Writes a header file, like SQLite's mkkeywordhash. */
int main(int argc, char **argv) {
    FILE *f = fopen(argv[1], "w");
    if (!f) return 1;
    fprintf(f, "#define KEYWORD_COUNT 42\n");
    return fclose(f);
}
