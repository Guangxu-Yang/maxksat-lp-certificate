# Max-kSAT LP Certificate

This repository contains the exact rational verifier for the finite
factor-revealing LP certificate used in the Max-\(k\)SAT quantum streaming
upper bound.

The layout follows the lightweight artifact style of
[`singerng/oblivious-csps`](https://github.com/singerng/oblivious-csps):
there is a small exact verifier, an optional LP-search script, examples, and
installation notes.  The mathematical certificate here is for Max-\(k\)SAT,
rather than Singer's Max-\(k\)AND setting.

The certificate proves the short-clause snapshot inequality

```text
L_{\le 3}(Snap_{\le 3}(\Psi)) >= rho * OPT(\Psi)
```

for all Max-\(k\)SAT instances whose clauses have length at most three, where

```text
rho = 28691 / 40000 = 0.717275.
```

Clauses of length at least four are handled separately by a uniform rounding
floor.  The verifier checks all certificate inequalities exactly over the
rationals using Python's `fractions.Fraction`.

## Repository Layout

```text
.
├── INSTALLING
├── examples.py
├── scripts/
│   ├── verify_certificate.py
│   ├── verify_max2sat_certificate.py
│   └── search_lp_certificate.py
├── artifacts/
│   └── max2sat/
├── docs/
│   ├── lp_certificate.md
│   └── relationship_to_oblivious_csps.md
├── tests/
│   └── test_verify_certificate.py
├── .github/workflows/
│   └── verify.yml
├── pyproject.toml
└── README.md
```

## Quick Start

Run all proof-relevant checks:

```bash
python3 examples.py
```

Run the exact verifier:

```bash
python3 scripts/verify_certificate.py
```

Run the Max-2SAT companion verifier for the 450-bucket, 9-profile snapshot
certificate.  Its default exact target is
`18563/25000 = 0.74252`, which implies the stated `0.7425` guarantee with a
small rational margin:

```bash
python3 scripts/verify_max2sat_certificate.py
```

Expected output:

```text
ratio rho: 28691/40000 = 0.717275000
long-clause floor: ... = 0.717306925420
upper constraints verified: 4096; minimum upper slack: ...
atom inequalities verified: 33824; minimum certificate slack: ...
nonzero H components: 659
nonzero dual multipliers: 14
```

Run the smoke test:

```bash
python3 -m unittest discover -s tests
```

No third-party Python packages are required for verification.

Optional: rerun the floating-point LP search that motivates the rational
certificate:

```bash
python3 -m pip install ".[search]"
python3 examples.py search
```

Optional: regenerate the Max-2SAT exact witness from the fixed 9-profile curve
bundle:

```bash
python3 scripts/max2sat_multi_rounding_certificate_search.py \
  --curves-json artifacts/max2sat/multirounding_L450_9_rounding_curves.json \
  --output-json artifacts/max2sat/multirounding_L450_exact_witness.json
```

This search script is not part of the formal proof; it uses floating point
linear programming.  The proof-relevant step is `verify_certificate.py`.

## What Is Verified?

The script verifies three finite rational statements.

1. **Long-clause floor.**  The rounding vector ensures every literal is
   satisfied with probability at least `27083/100000`, hence every clause of
   length at least four is satisfied with probability strictly larger than
   `rho`.

2. **Ternary upper constraints.**  The pairwise-decomposable ternary surrogate
   \(H\) is pointwise at most the true independent-rounding satisfaction
   probability on every endpoint-label triple.

3. **Short-clause lower certificate.**  For every typed unary, binary, or
   ternary atom, the verifier checks a dual inequality of the form

   ```text
   h(c) - rho * o(c) + dual_correction(c) >= 0.
   ```

   Summing these inequalities over all atoms proves the global lower bound.

See [docs/lp_certificate.md](docs/lp_certificate.md) for the mathematical
description of the LP certificate.

See
[docs/relationship_to_oblivious_csps.md](docs/relationship_to_oblivious_csps.md)
for how this artifact relates to Singer's `oblivious-csps` codebase.

## Citation

If you use this artifact, cite the accompanying paper and mention that the
certificate was checked exactly over \(\mathbb Q\).

## License

No license has been selected yet.  Add a license before making the repository
public if you want others to reuse the code.
