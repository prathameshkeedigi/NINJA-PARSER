#include <stdio.h>

/* Writes a .c file and a .h file in one run, like the lemon parser generator. */
int main(int argc, char **argv) {
    FILE *c = fopen(argv[1], "w"), *h = fopen(argv[2], "w");
    if (!c || !h) return 1;
    fprintf(h, "int parse(int tokens);\n");
    fprintf(c, "#include \"parse.h\"\nint parse(int tokens) { return tokens * 3; }\n");
    return fclose(c) | fclose(h);
}
