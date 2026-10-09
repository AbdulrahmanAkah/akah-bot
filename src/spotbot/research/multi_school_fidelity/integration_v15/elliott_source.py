"""Declared consecutive-pivot finite grammar, not a silent combinatorial cap.

Native V8 geometry/subdivision validation is unchanged. Every supported
interpretation of adjacent source tuples is retained, including opposing ones.
The original unrestricted V13 research search remains available and unmodified.
"""
from ..integration_v13.elliott_source import CompleteProofSearch, ElliottSource as Previous, GeometricResume
from ..elliott_contract_v8 import CHILD_DEGREE, CORRECTIVE
from ..school_contract_common_v8 import validate_points
from ..structural_lifecycle_v6 import ContractError

class ConsecutiveProofSearch(CompleteProofSearch):
    def _sequences(self, degree, length, start=None, end=None):
        self.sequence_queries += 1
        points = self.points[degree]
        for i in range(max(0, len(points)-length+1)):
            seq = points[i:i+length]
            if start is not None and self._endpoint(seq[0]) != self._endpoint(start):
                continue
            if end is not None and self._endpoint(seq[-1]) != self._endpoint(end):
                continue
            try:
                validate_points(seq, self.now)
            except ContractError:
                continue
            yield seq

    def resumptions(self, parent_degrees=("4H", "1D"), legs=("W2", "W4", "ABC"), ends=None):
        result = {}
        for degree in parent_degrees:
            points = self.points[degree]
            selected = {p.event_id for p in points if ends is None or p in ends}
            for start, end in zip(points[:-1], points[1:]):
                if end.event_id not in selected:
                    continue
                corrections = tuple(w for kind in sorted(CORRECTIVE)
                    for w in self.waves(CHILD_DEGREE[degree], kind, start, end))
                for leg in legs:
                    for parent in self.parent_prefixes(degree, leg, start):
                        for correction in corrections:
                            geom = GeometricResume(parent, leg, end, correction)
                            try:
                                self._validate_geometry(geom)
                            except ContractError as exc:
                                self.diagnostics[str(exc)] += 1
                                continue
                            result[geom.structure_id] = geom
        return tuple(result.values())

class ElliottSource(Previous):
    def search(self, now, **kwargs):
        if self._search is None:
            self._search = ConsecutiveProofSearch(self.prefix, now)
        return super().search(now, **kwargs)
