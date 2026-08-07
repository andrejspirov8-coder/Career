from __future__ import annotations

import subprocess
from pathlib import Path


def test_generate_typescript_types():
    result = subprocess.run(
        ["uv", "run", "python", "scripts/generate-contracts.py"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0, f"Generation failed: {result.stderr}"

    generated_dir = Path("dashboard/lib/generated")
    assert generated_dir.exists(), "Generated directory not created"

    # Verify envelope type generated
    envelope_file = generated_dir / "envelope.ts"
    assert envelope_file.exists(), "envelope.ts not generated"
    content = envelope_file.read_text()
    assert "PythonHelperEnvelopeV1" in content
    assert "career_python_helper_v1" in content

    # Verify at least one helper type generated
    automation_file = generated_dir / "automation-contracts.ts"
    assert automation_file.exists(), "automation-contracts.ts not generated"
    content = automation_file.read_text()
    assert "AutomationOverview" in content
