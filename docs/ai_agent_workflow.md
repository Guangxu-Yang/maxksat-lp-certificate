# AI-agent-assisted certificate discovery

The accompanying manuscript describes an AI agent that repeatedly changes a rounding profile, solves the associated factor-revealing LP, and uses the resulting approximation ratio to guide the next adjustment. The profile consists of the short-clause cutoff, length weights, bias buckets, and rounding probabilities.

The search scales by adding violated constraints iteratively and grouping literal labels for pair coefficients while retaining fine-label unary coefficients. The final profile has cutoff 5 and 1000 reflected bias buckets. Once a candidate is chosen, rationalization, identity checking, and complete exact constraint replay establish the released certificate.

This narrative follows the supplied paper. It does not assert a particular agent model, vendor, prompt sequence, token budget, search runtime, or number of trials. The repository contains the fixed certificate and verification sources, with selected search provenance; it does not contain the full autonomous search system.

## Paper-to-code map

| Paper source | Topic | Artifact counterpart |
| --- | --- | --- |
| [`Intro.tex`](../paper/Intro.tex), technical overview | Agent-guided profile search and scalable LP refinement | `provenance/lineage/`, `verifier/source/` |
| [`k-SATtoSnap.tex`](../paper/k-SATtoSnap.tex) | Weighted snapshots and the score inequality | Fixed design and exact candidate |
| [`SnapshotScoreProofs.tex`](../paper/SnapshotScoreProofs.tex), Steps 1–4 | Upper constraints, lower certificate, finite LP, feasibility proof | `v016_fine_unary_exact.py`, exact gate reports |
| [`SnapshotScoreProofs.tex`](../paper/SnapshotScoreProofs.tex), Step 5 | Final profile, rationalization, `rho = 0.742694813` | `exact_candidate.json`, identity checker, full replay |
| [`Algorithm.tex`](../paper/Algorithm.tex) | Estimation error and final `0.7426` streaming guarantee | Mathematical analysis in the manuscript |
| [`AI_agent.tikz`](../paper/AI_agent.tikz) | Agent / LP solver / exact verifier diagram | Discovery and verification workflow |

Artifact paths in this table are relative to [`artifacts/maxksat/strict-rho-0.742694813/`](../artifacts/maxksat/strict-rho-0.742694813/).

The manuscript is included unchanged. Its main file is `paper/Main.tex`; building it requires a normal multi-file LaTeX environment with its bibliography and included TikZ files. No compiled PDF is supplied by this update.
