# Max-2SAT Appendix Code

This note records the Max-2SAT code path used by the companion appendix line
with target ratio `0.7425`.

Unlike the main Max-kSAT part of this repository, this is not yet an exact
rational verifier. It is the floating-point construction path for the appendix
certificate.

## Main chain

The intended pipeline is:

```text
weighted -> nonuniform -> multirounding.
```

Concretely:

1. `scripts/max2sat_weighted_certificate_search.py`
   builds the base weighted Max-2SAT LP and produces a strong nonuniform
   single-rounding artifact such as
   `nonuniform_L450_focus0_str36_sig012_plus009_s6_w335.json`.

2. `scripts/max2sat_build_multirounding_curves.py`
   takes a base curve plus a scale witness and expands them into the nine
   clipped scaled curves used in the appendix multi-rounding argument.

3. `scripts/max2sat_multi_rounding_certificate_search.py`
   runs the LP for the maximum of several rounding rules and produces the
   multi-rounding witness.

## Why this subset

The Max-2SAT source tree contains many exploratory branches. This repository
keeps only the scripts used directly by the appendix proof line. In particular,
the stronger residual-pressure numerical branch is not included here because it
is not part of the appendix's proof narrative.

## Artifact roles

- `max2sat_weighted_certificate_search.py`
  is the base engine.
- `max2sat_build_multirounding_curves.py`
  is the bridge from the base curve to the nine-rule bundle.
- `max2sat_multi_rounding_certificate_search.py`
  is the LP combiner that certifies the multi-rounding witness.

## Status

This subset is useful for reconstruction and experimentation, but it does not
yet provide a proof-relevant exact verifier analogous to
`scripts/verify_certificate.py` for Max-kSAT.
