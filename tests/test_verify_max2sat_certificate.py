import importlib.util
import unittest
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "verify_max2sat_certificate.py"
    spec = importlib.util.spec_from_file_location("verify_max2sat_certificate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Max2SatCertificateVerifierTest(unittest.TestCase):
    def test_tiny_exact_instance(self):
        verifier = load_module()
        data = {
            "L": 1,
            "unary_weight": "67/20",
            "rho": "0",
            "intervals": [["-1", "1"]],
            "curves": [{"alpha": "1", "p": ["1/2"]}],
            "alphas": ["1"],
            "lambdas": ["0", "0", "0", "0"],
        }
        result = verifier.check_certificate(data, data, verifier.Q(0))
        self.assertEqual(result["checked_unary"], 4)
        self.assertEqual(result["checked_binary"], 16)
        self.assertEqual(result["min_slack"], verifier.Q(1, 2))

    def test_missing_lambdas_is_rejected(self):
        verifier = load_module()
        data = {
            "L": 1,
            "unary_weight": "67/20",
            "rho": "0",
            "intervals": [["-1", "1"]],
            "curves": [{"alpha": "1", "p": ["1/2"]}],
            "alphas": ["1"],
        }
        with self.assertRaisesRegex(ValueError, "dual multipliers"):
            verifier.check_certificate(data, data, verifier.Q(0))


if __name__ == "__main__":
    unittest.main()
