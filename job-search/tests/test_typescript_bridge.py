import subprocess


def test_dashboard_typescript_compiles_with_generated_types():
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True, text=True, cwd="dashboard"
    )
    assert result.returncode == 0, f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"