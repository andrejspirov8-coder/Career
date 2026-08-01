# tests/test_contract_pipeline_e2e.py
import json
import subprocess


def test_contract_pipeline_e2e():
    """Verify: Python schema -> TS generation -> TypeScript compiles -> runtime works"""
    
    # 1. All helpers export schema
    for helper in ["career_job_search.automation.control", "career_job_search.opportunities.dashboard_adapter", "career_job_search.recruiters.dashboard_adapter", "career_job_search.cvs.catalogue_cli", "career_job_search.cvs.studio", "career_job_search.cvs.drafting", "career_job_search.notifications.center", "career_job_search.opportunities.preferences", "career_job_search.workspace.control", "career_job_search.automation.analytics"]:
        result = subprocess.run(["uv", "run", "python", "-m", helper, "--schema"], capture_output=True, text=True)
        assert result.returncode == 0
        schema = json.loads(result.stdout)
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    
    # 2. TypeScript generation succeeds
    result = subprocess.run(["uv", "run", "python", "scripts/generate-contracts.py"], capture_output=True, text=True)
    assert result.returncode == 0
    
    # 3. Dashboard typecheck passes
    result = subprocess.run(["npm", "run", "typecheck"], capture_output=True, text=True, cwd="dashboard")
    assert result.returncode == 0, f"TypeScript failed: {result.stderr}"
    
    # 4. Dashboard unit tests pass
    result = subprocess.run(["npm", "test"], capture_output=True, text=True, cwd="dashboard")
    assert result.returncode == 0, f"Dashboard tests failed: {result.stderr}"