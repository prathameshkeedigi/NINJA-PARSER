# Negative control: a deliberately broken parser must FAIL the checks

Each row uses a copy of `tools/ninja_parse.py` with ONE bug put in on purpose. `FAIL` or `ERROR` in a cell means the proof caught that bug in that project. `PASS` means that project does not contain the build.ninja feature the bug breaks.

| Bug | What the bug does | 01_basic_exe | 03_shared_lib | 05_generated_header | 16_spaces_in_paths |
|---|---|---|---|---|---|
| B1 undefined variable kept | an undefined variable becomes the text $NAME instead of empty text | FAIL check 2,4 | FAIL check 2,4 | FAIL check 2,4 | FAIL check 2,4 |
| B2 escaped space not understood | the escape '$ ' (a space inside a path) is not recognised | PASS | PASS | PASS | ERROR (build.ninja:47: bad $-escape: '$ ') |
| B3 implicit outputs dropped | outputs after '\|' on a build line are thrown away | PASS | PASS | FAIL check 1 | PASS |
| B4 order-only inputs dropped | inputs after '\|\|' on a build line are thrown away | FAIL check 1 | FAIL check 1 | FAIL check 1,2,4 | FAIL check 1 |
| B5 waiting arrows from explicit inputs only | a task waits only for producers of its explicit inputs, not of its \| and \|\| inputs | PASS | PASS | FAIL check 4 | PASS |

**5 of 5 deliberate bugs were caught by at least one project.**
