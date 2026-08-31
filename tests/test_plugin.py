import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "obsidian_curator", ROOT / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class State:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class Context:
    def __init__(self, config=None):
        self.config = config or {}
        self.state = State()
        self.hooks = {}
        self.tools = {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, name, handler, **kwargs):
        self.tools[name] = handler


def install_scheduler_mock(monkeypatch):
    calls = []

    def create_job_with_scheduler_registration(**kwargs):
        calls.append(kwargs)
        return {"id": "cron_test_123", **kwargs}

    monkeypatch.setitem(
        sys.modules,
        "cron.scheduler",
        SimpleNamespace(
            create_job_with_scheduler_registration=create_job_with_scheduler_registration
        ),
    )
    return calls


def test_setup_registers_native_oneshot_job(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    ctx = Context()
    plugin.register(ctx)

    result = json.loads(
        ctx.tools["obsidian_curator"](
            {
                "operation": "setup",
                "vault_path": str(tmp_path),
                "review_interval": 3,
                "curator_prompt": "Audit and curate vault.",
                "enabled_toolsets": ["file", "skills"],
                "skills": ["notes"],
                "model": "model-x",
                "provider": "provider-x",
                "base_url": "https://example.invalid",
                "reasoning_effort": "high",
                "workdir": str(tmp_path),
            }
        )
    )

    assert result == {
        "ok": True,
        "status": "active",
        "vault_path": str(tmp_path.resolve()),
    }
    assert len(calls) == 1
    job = calls[0]
    assert job["name"] == "Obsidian Curator Initial Setup"
    assert job["repeat"] == 1
    assert job["deliver"] == "local"
    assert job["enabled_toolsets"] == ["file", "skills"]
    assert job["skills"] == ["notes"]
    assert job["model"] == "model-x"
    assert job["provider"] == "provider-x"
    assert job["base_url"] == "https://example.invalid"
    assert job["reasoning_effort"] == "high"
    assert job["workdir"] == str(tmp_path)
    assert "Map the entire vault recursively" in job["prompt"]


def test_setup_rejects_unsafe_toolsets(tmp_path):
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)
    res = json.loads(
        ctx.tools["obsidian_curator"](
            {
                "operation": "setup",
                "vault_path": str(tmp_path),
                "review_interval": 3,
                "curator_prompt": "Audit.",
                "enabled_toolsets": ["file", "terminal"],
            }
        )
    )
    assert res == {"error": "enabled_toolsets may only contain: 'file', 'skills'"}


def test_turn_and_tool_triggers_schedule_due_job(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    ctx = Context(
        {
            "vault_path": str(tmp_path),
            "review_interval": 3,
            "curator_prompt": "Audit vault.",
        }
    )
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](
        session_id="session-a", assistant_response="Turn 1", platform="telegram"
    )
    ctx.hooks["post_tool_call"](
        session_id="session-a", status="ok", platform="telegram"
    )
    assert len(calls) == 0
    assert ctx.state.get("session_activity_counts") == {"session-a": 2}

    ctx.hooks["post_llm_call"](
        session_id="session-a", assistant_response="Turn 2", platform="telegram"
    )
    assert len(calls) == 1
    assert calls[0]["repeat"] == 1
    assert calls[0]["name"] == "Obsidian Curator (session-)"
    assert ctx.state.get("session_activity_counts") == {}


def test_interval_20_exact_trigger(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    ctx = Context(
        {
            "vault_path": str(tmp_path),
            "review_interval": 20,
            "curator_prompt": "Audit vault.",
        }
    )
    plugin.register(ctx)

    for i in range(1, 20):
        ctx.hooks["post_llm_call"](
            session_id="session-20", assistant_response=f"Turn {i}", platform="telegram"
        )
        assert len(calls) == 0
        assert ctx.state.get("session_activity_counts") == {"session-20": i}

    ctx.hooks["post_llm_call"](
        session_id="session-20", assistant_response="Turn 20", platform="telegram"
    )
    assert len(calls) == 1
    assert ctx.state.get("session_activity_counts") == {}


def test_finalize_schedules_remaining_activity_with_origin(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    env = {
        "HERMES_SESSION_PLATFORM": "discord",
        "HERMES_SESSION_CHAT_ID": "1539392114360844340",
        "HERMES_SESSION_THREAD_ID": "",
    }
    monkeypatch.setitem(
        sys.modules,
        "gateway.session_context",
        SimpleNamespace(
            get_session_env=lambda name, default="": env.get(name, default)
        ),
    )
    ctx = Context(
        {
            "vault_path": str(tmp_path),
            "review_interval": 20,
            "curator_prompt": "Audit vault.",
        }
    )
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](
        session_id="discord-session", assistant_response="Turn 1", platform="discord"
    )
    env.clear()
    ctx.hooks["on_session_finalize"](
        session_id="discord-session", reason="new_session", platform="discord"
    )

    assert len(calls) == 1
    job = calls[0]
    assert job["deliver"] == "origin"
    assert job["origin"]["platform"] == "discord"
    assert job["origin"]["chat_id"] == "1539392114360844340"
    assert ctx.state.get("session_activity_counts") == {}


def test_reset_does_not_duplicate_finalize_review(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    ctx = Context(
        {
            "vault_path": str(tmp_path),
            "review_interval": 20,
            "curator_prompt": "Audit vault.",
        }
    )
    ctx.state.set(
        "session_origins",
        {"old-session": {"platform": "telegram", "chat_id": "8804634959"}},
    )
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](
        session_id="old-session", assistant_response="Turn 1", platform="telegram"
    )
    ctx.hooks["on_session_finalize"](
        session_id="old-session", reason="new_session", platform="telegram"
    )
    ctx.hooks["on_session_reset"](
        session_id="new-session", reason="new_session", platform="telegram"
    )

    assert len(calls) == 1
    assert calls[0]["origin"]["platform"] == "telegram"


def test_shutdown_finalize_does_not_schedule_review(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_scheduler_mock(monkeypatch)
    ctx = Context(
        {
            "vault_path": str(tmp_path),
            "review_interval": 20,
            "curator_prompt": "Audit vault.",
        }
    )
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](
        session_id="old-session", assistant_response="Turn 1", platform="telegram"
    )
    ctx.hooks["on_session_finalize"](
        session_id="old-session", reason="shutdown", platform="telegram"
    )
    ctx.hooks["on_session_finalize"](
        session_id="old-session", reason="process_exit", platform="telegram"
    )

    assert len(calls) == 0
    assert ctx.state.get("session_activity_counts") == {"old-session": 1}


def test_pre_tool_call_sandboxes_cron_curator(tmp_path):
    plugin = load_plugin()
    ctx = Context({"vault_path": str(tmp_path), "curator_prompt": "Audit vault."})
    ctx.state.set("curator_job_ids", {"obsidian_curator_123": None})
    plugin.register(ctx)

    inside = tmp_path / "notes.md"
    outside = Path("/tmp/outside.md")

    blocked_tool = ctx.hooks["pre_tool_call"](
        session_id="cron_obsidian_curator_123", tool_name="terminal"
    )
    assert blocked_tool == {
        "action": "block",
        "message": "Tool 'terminal' is disabled for the Obsidian curator.",
    }

    no_path = ctx.hooks["pre_tool_call"](
        session_id="cron_obsidian_curator_123", tool_name="read_file", args={}
    )
    assert no_path == {
        "action": "block",
        "message": "Tool 'read_file' requires an absolute vault path.",
    }

    allowed_read = ctx.hooks["pre_tool_call"](
        session_id="cron_obsidian_curator_123",
        tool_name="read_file",
        args={"path": str(inside)},
    )
    assert allowed_read is None

    blocked_read = ctx.hooks["pre_tool_call"](
        session_id="cron_obsidian_curator_123",
        tool_name="read_file",
        args={"path": str(outside)},
    )
    assert blocked_read == {
        "action": "block",
        "message": f"Path '{outside}' is outside the designated Obsidian vault.",
    }


def test_setup_validation(tmp_path):
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)
    base = {"operation": "setup", "vault_path": str(tmp_path), "review_interval": 3}
    assert json.loads(
        ctx.tools["obsidian_curator"]({**base, "curator_prompt": " "})
    ) == {"error": "curator_prompt must be a non-empty string."}
    assert json.loads(
        ctx.tools["obsidian_curator"](
            {**base, "curator_prompt": "Audit.", "review_interval": 0}
        )
    ) == {"error": "review_interval must be a positive integer."}
