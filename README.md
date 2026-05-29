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
├── artifacts/
│   └── max2sat/
│       ├── nonuniform_L450_focus0_str36_sig012_plus009_s6_w335.json
│       ├── multirounding_L450_9_rounding_curves.json
│       └── multirounding_L450_focus36_sig012_plus009_s6_ultrafine_scales.json
├── scripts/
│   ├── verify_certificate.py
│   ├── search_lp_certificate.py
│   ├── max2sat_weighted_certificate_search.py
│   ├── max2sat_build_multirounding_curves.py
│   └── max2sat_multi_rounding_certificate_search.py
├── docs/
│   ├── lp_certificate.md
│   ├── relationship_to_oblivious_csps.md
│   └── max2sat_appendix_code.md
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

This search script is not part of the formal proof; it uses floating point
linear programming.  The proof-relevant step is `verify_certificate.py`.

## Companion Max-2SAT Appendix Code

This repository also contains the code path used by the companion Max-2SAT
appendix line with ratio `0.7425`. This is not yet an exact rational verifier.
It is the floating-point construction path for the appendix certificate.

The appendix-facing chain is:

```text
weighted -> nonuniform -> multirounding.
```

The relevant scripts are:

- `scripts/max2sat_weighted_certificate_search.py`
  - base weighted Max-2SAT snapshot LP and nonuniform single-rounding search;
- `scripts/max2sat_build_multirounding_curves.py`
  - expands a base curve plus a scale witness into the nine rounding curves
    used by the appendix certificate;
- `scripts/max2sat_multi_rounding_certificate_search.py`
  - certifies the max of those rounding rules.

The proof-relevant JSON artifacts carried by this appendix line are:

- `artifacts/max2sat/nonuniform_L450_focus0_str36_sig012_plus009_s6_w335.json`
  - base nonuniform single-rounding witness;
- `artifacts/max2sat/multirounding_L450_9_rounding_curves.json`
  - nine-curve bundle used by the multi-rounding step;
- `artifacts/max2sat/multirounding_L450_focus36_sig012_plus009_s6_ultrafine_scales.json`
  - final multi-rounding witness certifying the appendix ratio.

See [docs/max2sat_appendix_code.md](docs/max2sat_appendix_code.md) for the
role of these scripts and the artifact chain they implement.

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
