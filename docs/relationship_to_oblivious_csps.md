# Relationship to `singerng/oblivious-csps`

This artifact is organized in the same spirit as Noah Singer's
`oblivious-csps` repository for Max-\(k\)AND oblivious algorithms:

- keep the mathematical LP/certificate logic in small Python scripts;
- provide an `examples.py` entry point for reproducible commands;
- separate installation notes from the mathematical explanation;
- make the artifact easy to attach to a paper or arXiv submission.

The mathematical objects are different.

Singer's repository studies factor-revealing LPs for Max-\(k\)AND oblivious
rounding algorithms.  Its code builds and solves LPs for bias patterns of
Max-\(k\)AND.

This repository verifies a fixed rational certificate for a Max-\(k\)SAT
snapshot bound.  The proof uses:

- weighted signed biases for clauses of length one, two, and three;
- a pairwise-decomposable lower score for ternary clauses;
- exact independent-rounding scores for unary and binary clauses;
- a deterministic rounding floor for clauses of length at least four.

The most important distinction is proof status:

```text
scripts/search_lp_certificate.py
```

is a floating-point LP search aid, analogous in spirit to search code in
oblivious-algorithm artifacts.

```text
scripts/verify_certificate.py
```

is the formal verifier.  It checks the final rational certificate exactly over
\(\mathbb Q\).  This is the script that should be cited by the paper.
