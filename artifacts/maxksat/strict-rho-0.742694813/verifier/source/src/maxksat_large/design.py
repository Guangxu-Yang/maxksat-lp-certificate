"""Exact lattice outer design without the legacy small-LP dimension limit.

Every positive bucket owns a separate rounding coordinate.  Certificate
grouping, if used by a solver, never changes or identifies those coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
import json
from numbers import Integral
from typing import Any, Mapping


MAX_POSITIVE_BUCKETS = 4096
FORMULATION_VERSION = "scaled-k-pair-h5-v1"


def _integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an exact integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class LargeDesign:
    formulation_version: str = FORMULATION_VERSION
    tick_denominator: int = 1_000_000
    positive_bucket_boundary_ticks: tuple[int, ...] = (250_000, 500_000, 750_000)
    profile_rounding_ticks: tuple[tuple[int, ...], ...] = ((570_000, 650_000, 700_000, 740_000),)
    bias_weight_ticks: tuple[int, ...] = (73, 20, 10, 6, 1)
    eta_min_ticks: int = 10_000
    monotone_rounding: bool = True
    boundary_convention: str = "left-closed-right-open-last-closed"

    def __post_init__(self):
        d = _integer(self.tick_denominator, "tick_denominator")
        if not 2 <= d <= 10**12:
            raise ValueError("tick_denominator must be in [2, 10**12]")
        bounds = tuple(_integer(x, "boundary") for x in self.positive_bucket_boundary_ticks)
        p = len(bounds) + 1
        if not 1 <= p <= MAX_POSITIVE_BUCKETS:
            raise ValueError("unsupported positive bucket count")
        if any(not 0 < x < d for x in bounds) or any(a >= b for a, b in zip(bounds, bounds[1:])):
            raise ValueError("positive boundaries must strictly increase inside (0,D)")
        profiles = tuple(tuple(_integer(x, "rounding") for x in row) for row in self.profile_rounding_ticks)
        if len(profiles) != 1 or len(profiles[0]) != p:
            raise ValueError("large-bucket backend requires J=1 and one q per positive bucket")
        if not isinstance(self.monotone_rounding, bool):
            raise ValueError("monotone_rounding must be bool")
        if any(2*x < d or x > d for x in profiles[0]):
            raise ValueError("positive-half q must lie in [1/2,1]")
        if self.monotone_rounding and any(a > b for a,b in zip(profiles[0],profiles[0][1:])):
            raise ValueError("rounding must be nondecreasing")
        weights = tuple(_integer(x, "weight") for x in self.bias_weight_ticks)
        if len(weights) != 5 or any(x < 0 for x in weights) or sum(weights) != 110:
            raise ValueError("five nonnegative weight ticks must sum to 110")
        if any(a < b for a,b in zip(weights,weights[1:])):
            raise ValueError("weights must be nonincreasing")
        eta = _integer(self.eta_min_ticks, "eta_min_ticks")
        if not 0 < eta <= d:
            raise ValueError("eta_min must lie in (0,1]")
        if self.formulation_version != FORMULATION_VERSION:
            raise ValueError("unknown surrogate formulation")
        if self.boundary_convention != "left-closed-right-open-last-closed":
            raise ValueError("unsupported bucket boundary convention")
        for name, value in (("tick_denominator",d),("positive_bucket_boundary_ticks",bounds),
                            ("profile_rounding_ticks",profiles),("bias_weight_ticks",weights),
                            ("eta_min_ticks",eta)):
            object.__setattr__(self, name, value)

    @property
    def num_positive_buckets(self): return len(self.positive_bucket_boundary_ticks) + 1

    @property
    def positive_bucket_count(self): return self.num_positive_buckets

    @property
    def num_buckets(self): return 2*self.num_positive_buckets

    @property
    def num_profiles(self): return 1

    @property
    def weights(self): return self.bias_weight_ticks

    @property
    def eta_min(self): return Fraction(self.eta_min_ticks, self.tick_denominator)

    @property
    def positive_bucket_boundaries(self):
        return tuple(Fraction(x,self.tick_denominator) for x in self.positive_bucket_boundary_ticks)

    @property
    def bucket_edges(self):
        pos = self.positive_bucket_boundaries
        return (Fraction(-1), *(-x for x in reversed(pos)), Fraction(0), *pos, Fraction(1))

    @property
    def bucket_intervals(self):
        edges = self.bucket_edges
        return tuple(zip(edges,edges[1:]))

    def full_rounding_profile(self, profile_index=0):
        if profile_index != 0: raise ValueError("J=1")
        pos = tuple(Fraction(x,self.tick_denominator) for x in self.profile_rounding_ticks[0])
        return tuple(1-x for x in reversed(pos)) + pos

    @property
    def full_rounding_profiles(self): return (self.full_rounding_profile(0),)

    @property
    def distinct_positive_rounding_count(self): return len(set(self.profile_rounding_ticks[0]))

    def with_rounding(self, ticks):
        return replace(self, profile_rounding_ticks=(tuple(ticks),))

    def to_dict(self) -> dict[str,Any]:
        return {"formulation_version":self.formulation_version,
                "tick_denominator":self.tick_denominator,
                "positive_bucket_boundary_ticks":list(self.positive_bucket_boundary_ticks),
                "profile_rounding_ticks":[list(self.profile_rounding_ticks[0])],
                "bias_weight_ticks":list(self.bias_weight_ticks),
                "eta_min_ticks":self.eta_min_ticks,
                "monotone_rounding":self.monotone_rounding,
                "boundary_convention":self.boundary_convention}

    def to_json(self, *, indent=None):
        return json.dumps(self.to_dict(),sort_keys=True,ensure_ascii=False,
                          separators=(",",":") if indent is None else None,indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str,Any]):
        if not isinstance(data, Mapping): raise ValueError("design must be a mapping")
        unknown = set(data)-set(cls.__dataclass_fields__)
        if unknown: raise ValueError(f"unknown design fields: {sorted(unknown)}")
        return cls(**dict(data))

    @classmethod
    def from_json(cls, data: str): return cls.from_dict(json.loads(data))

    @property
    def canonical_hash(self): return sha256(self.to_json().encode("utf-8")).hexdigest()
