# LP Certificate Verification

This document explains the finite certificate checked by
`scripts/verify_certificate.py`.

## 1. Rounding Data

The verifier fixes

```text
rho = 28691 / 40000.
```

The bias interval partition is

```text
[-1,-3/4), [-3/4,-1/2), [-1/2,-1/4), [-1/4,0),
[0,1/4), [1/4,1/2), [1/2,3/4), [3/4,1].
```

The rounding vector is

```text
r = (
  27083/100000, 27083/100000, 27083/100000, 4069/10000,
  5931/10000, 72917/100000, 72917/100000, 72917/100000
).
```

For a literal sign `s` and bucket `i`, define

```text
q_+(i) = r_i,
q_-(i) = 1 - r_i.
```

An endpoint label is a pair

```text
alpha = (literal sign, bias bucket).
```

There are `16` possible endpoint labels.

## 2. Weighted Short Snapshot

Only clauses of length one, two, and three define the short snapshot.  The
variable bias uses endpoint weights

```text
w_1 = 4,   w_2 = 2,   w_3 = 1.
```

Unary and binary clauses are scored by their exact independent-rounding
satisfaction probabilities.

Ternary clauses are scored by a pairwise-decomposable surrogate

```text
H(alpha_1, alpha_2, alpha_3)
  = c_0
    + sum_j u_j(alpha_j)
    + sum_{j<t} p_{jt}(alpha_j, alpha_t).
```

The rational coefficients `c_0`, `u_j`, and `p_jt` are stored in the
`component_nums` array in the verifier.

## 3. Ternary Upper Constraints

For each endpoint-label triple, the verifier checks

```text
H(alpha_1, alpha_2, alpha_3)
  <= 1 - prod_j (1 - q_{alpha_j}).
```

There are

```text
16^3 = 4096
```

such inequalities.

This ensures the snapshot score is never larger than the expected value of a
valid independent randomized assignment, giving the upper bound

```text
L_{\le 3}(Snap_{\le 3}(\Psi)) <= OPT(\Psi).
```

## 4. Typed Atom Lower Constraints

For the lower bound, fix a reference assignment.  A typed atom records:

```text
clause length,
literal signs,
bias buckets,
reference-assignment bits.
```

For each typed atom `c`, let:

```text
h(c) = contribution of c to the snapshot score,
o(c) = whether the reference assignment satisfies c.
```

The verifier uses nonnegative dual multipliers for the bucket constraints.
For each endpoint, the dual correction uses the appropriate endpoint weight
`w_length`.

For every typed atom, the verifier checks

```text
h(c) - rho * o(c) + dual_correction(c) >= 0.
```

The number of checked atom inequalities is

```text
32 + 1024 + 32768 = 33824.
```

Summing the atom inequalities over an instance and using feasibility of the
bucket constraints gives

```text
L_{\le 3}(Snap_{\le 3}(\Psi)) >= rho * OPT(\Psi).
```

## 5. Long Clauses

The minimum literal satisfaction probability is

```text
27083 / 100000.
```

Thus every literal fails with probability at most

```text
72917 / 100000.
```

For every clause of length at least four,

```text
Pr[clause is satisfied]
  >= 1 - (72917/100000)^4
  = 0.717306925420...
  > 28691/40000.
```

Therefore long clauses contribute the deterministic lower score

```text
rho * m_{\ge 4}.
```

## 6. Exactness

All arithmetic in the verifier is exact rational arithmetic.  The script uses
only Python's standard library:

```python
from fractions import Fraction
```

Floating point numbers are printed only for readability.

## 7. Search vs. Verification

The repository separates two tasks:

```text
scripts/search_lp_certificate.py
```

reconstructs a floating-point LP used to search for a
pairwise-decomposable certificate.  It is useful for experimentation, but it is
not a formal proof.

```text
scripts/verify_certificate.py
```

checks the final rationalized certificate exactly over \(\mathbb Q\).  This is
the proof-relevant artifact.
