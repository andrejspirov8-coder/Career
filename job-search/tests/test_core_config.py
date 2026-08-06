from career_job_search.core.config import Settings

def test_default_settings_instantiation():
    settings = Settings()
    assert settings.app_name == "career-job-search"
    assert settings.network_timeout_seconds >= 1
