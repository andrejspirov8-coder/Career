import subprocess


def test_all_dashboard_helper_types_compile():
    result = subprocess.run(
        ["npm", "run", "typecheck"], capture_output=True, text=True, cwd="dashboard"
    )
    assert (
        result.returncode == 0
    ), f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"
