#!/usr/bin/env python3
"""Build the nine clipped scaled Max-2SAT rounding curves.

This helper fills the gap between the weighted single-rounding artifact and the
multi-rounding certificate LP used in the 0.7425 Max-2SAT appendix line.

Input 1 is a base single-rounding artifact such as

    nonuniform_L450_focus0_str36_sig012_plus009_s6_w335.json

containing a length-L probability vector ``p`` and the bucket partition.

Input 2 is a witness file such as

    multirounding_L450_focus36_sig012_plus009_s6_ultrafine_scales.json

containing the list of scales and the convex-combination weights ``alphas``.

For each scale ``s``, this script forms the clipped scaled curve

    p^(s) = clip(1/2 + s (p - 1/2), 0, 1).

The output matches the structure of

    multirounding_L450_9_rounding_curves.json

used by the formal Max-2SAT note.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def build_scaled_curve(base_p: list[float], scale: float) -> list[float]:
    return [clip01(0.5 + scale * (x - 0.5)) for x in base_p]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-json", required=True, help="base single-rounding artifact with keys p, L, unary_weight")
    parser.add_argument("--witness-json", required=True, help="multirounding witness with keys scales and alphas")
    parser.add_argument("--output-json", required=True, help="where to write the nine-curve bundle")
    parser.add_argument("--source-base-label", default=None, help="optional label to store as source_base_curve")
    parser.add_argument("--source-witness-label", default=None, help="optional label to store as source_multirounding")
    args = parser.parse_args()

    base = json.loads(Path(args.base_json).read_text())
    witness = json.loads(Path(args.witness_json).read_text())

    base_p = [float(x) for x in base["p"]]
    scales = [float(x) for x in witness["scales"]]
    alphas = [float(x) for x in witness["alphas"]]

    if len(scales) != len(alphas):
        raise ValueError("witness scales and alphas must have the same length")

    curves = []
    for scale, alpha in zip(scales, alphas):
        curves.append(
            {
                "scale": scale,
                "alpha": alpha,
                "p": build_scaled_curve(base_p, scale),
            }
        )

    out = {
        "description": "Nine clipped scaled rounding curves p^(t) derived from the L=450 base curve for the 0.7425 Max-2SAT multirounding certificate.",
        "source_multirounding": args.source_witness_label or args.witness_json,
        "source_base_curve": args.source_base_label or args.base_json,
        "rho": float(witness["rho"]),
        "L": int(base["L"]),
        "unary_weight": float(witness.get("unary_weight", base.get("unary_weight"))),
        "intervals": base["intervals"],
        "base_p": base_p,
        "curves": curves,
    }

    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))

    print(json.dumps({"curve_count": len(curves), "output_json": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
