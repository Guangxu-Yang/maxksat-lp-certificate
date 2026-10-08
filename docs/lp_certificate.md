# Current Max-kSAT certificate: 0.742694813

The current artifact is [`artifacts/maxksat/strict-rho-0.742694813`](../artifacts/maxksat/strict-rho-0.742694813/).

## Mathematical scope

For a fixed rounding profile `Theta`, the certificate supports the weighted-snapshot score inequality

```text
rho * OPT(Phi) <= L^Theta(Phi) <= OPT(Phi),
rho = 742694813 / 1000000000.
```

The profile has cutoff `ell_0 = 5`, 1000 reflected bias buckets, and rounding probabilities in `[61/250, 189/250]`. For clauses of lengths three through five, the surrogate has fine-label unary terms and coarse-group-pair terms. Unary and binary clauses are handled by low-order constraints. Nonnegative bias multipliers provide the lower certificate relative to a reference assignment; upper constraints bound the surrogate by independent-rounding satisfaction probabilities.

Every clause of length at least six has satisfaction probability at least

```text
1 - (189/250)^6
  = 198560991889639 / 244140625000000
  = 0.813305822779961... > rho.
```

The paper then accounts for pseudo-snapshot and estimation errors to obtain `0.7426`. The finite certificate alone does not implement or verify the entire quantum streaming algorithm.

## Exact checking and compression

The verifier uses exact rational arithmetic and checks 14 constraint families. It checks 2,001,000 unordered low-order literal-label pairs. For higher orders it enumerates 52,899 group multisets and uses exact upper-envelope compression, totaling 21,946,945 transitions. This is complete constraint checking through the verifier's compressed representation, not sampled testing. The reported global minimum slack is `1/1000000000000`.

Terminology matters: the design has 500 positive-side bias buckets and 1000 after reflection; each literal label also includes the literal sign, giving 2000 `(sign, bucket)` labels. The supplied archive sometimes calls the 1000 reflected buckets “signed labels.”

## Evidence chain

- `original/certificate/exact_candidate.json`: rational witness.
- `original/certificate/numerical_payload.json`: numerical input bound by hash; this file alone is not a strict certificate.
- `original/certificate/exact_gate/identity_report.json`: identity and design binding.
- `original/certificate/exact_gate/verify_report.json`: archived exact constraint report.
- `BUNDLE_MANIFEST.json` and the nested SHA-256 lists: file-set and evidence consistency.
- `validation/full_exact_replay/FULL_EXACT_REPLAY.json`: supplied archived replay.
- `tools/replay_exact_certificate.py`: portable entry point for a fresh replay using the bundled verifier.

A quick manifest check authenticates internal consistency and archived result fields. Only a full replay recomputes the constraints. See [INSTALLING](../INSTALLING).

## Reproduction boundary

The bundle is self-contained for verifying the fixed certificate with Python's standard library. Archived numerical search files reference components of the original research environment that are not included. Do not use those runner files as a promised standalone search pipeline. The preserved historical Windows paths and missing historical experiment-policy bytes are explained in the bundle's [`README_CN.md`](../artifacts/maxksat/strict-rho-0.742694813/README_CN.md).
