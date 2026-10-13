import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import tofu_outputs  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "tofu_outputs.py")


def full() -> dict:
    return {
        name: {"value": f"v-{name}", "sensitive": False} for name in tofu_outputs.OUTPUTS.values()
    }


class TofuOutputsTest(unittest.TestCase):
    def test_every_output_becomes_a_quoted_assignment(self) -> None:
        outputs = full()
        outputs["s3_secret_key"]["value"] = "a b'c"
        lines = tofu_outputs.assignments(outputs)
        self.assertEqual(len(lines), len(tofu_outputs.OUTPUTS))
        self.assertIn("VKE_ID=v-vke_id", lines)
        self.assertIn("S3_SECRET_KEY='a b'\"'\"'c'", lines)

    def test_missing_or_empty_output_fails_naming_it_only(self) -> None:
        outputs = full()
        del outputs["vke_id"]
        outputs["s3_bucket"]["value"] = ""
        with self.assertRaises(ValueError) as caught:
            tofu_outputs.assignments(outputs)
        self.assertIn("vke_id", str(caught.exception))
        self.assertIn("s3_bucket", str(caught.exception))
        self.assertNotIn("v-s3_secret_key", str(caught.exception))

    def test_no_state_exits_nonzero_and_prints_nothing(self) -> None:
        # What `tofu output -json` prints without a state: an empty object.
        run = subprocess.run(
            [sys.executable, SCRIPT], input="{}", capture_output=True, text=True, check=False
        )
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")


if __name__ == "__main__":
    unittest.main()
