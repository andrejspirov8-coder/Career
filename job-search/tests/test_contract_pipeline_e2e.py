# tests/test_contract_pipeline_e2e.py
import subprocess
import json

def test_contract_pipeline_e2e():
    """Verify: Python schema -> TS generation -> TypeScript compiles -> runtime works"""
    
    # 1. All helpers export schema
    for helper in ["automation_control", "opportunity_dashboard", "recruiter_dashboard", "cv_catalogue", "cv_studio", "local_dev_agents", "local_drafting", "notification_center", "search_preferences", "workspace_control", "career_analytics"]:
        result = subprocess.run(["uv", "run", "python", f"tools/{helper}.py", "--schema"], capture_output=True, text=True)
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