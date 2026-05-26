import subprocess
import sys
import unittest
from pathlib import Path


class CertificateVerifierTest(unittest.TestCase):
    def test_exact_certificate_verifier_runs(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "verify_certificate.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn("ratio rho: 28691/40000 = 0.717275000", result.stdout)
        self.assertIn("upper constraints verified: 4096", result.stdout)
        self.assertIn("atom inequalities verified: 33824", result.stdout)
        self.assertIn("minimum certificate slack: 3/10000000", result.stdout)


if __name__ == "__main__":
    unittest.main()
