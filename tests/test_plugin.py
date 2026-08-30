import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]


def load_plugin():
    spec = importlib.util.spec_from_file_location("obsidian_curator", ROOT / "__init__.py")
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


def install_cron_mock(monkeypatch, result=(True, "doc", "Obsidian review complete.", None)):
    calls = []

    def run_job(job):
        calls.append(job)
        return result

    monkeypatch.setitem(sys.modules, "cron.scheduler", SimpleNamespace(run_job=run_job, tick=lambda *args, **kwargs: None))
    return calls


def wait(plugin):
    for _ in range(20):
        thread = plugin._ACTIVE_THREAD
        if thread:
            thread.join(timeout=0.2)
        if plugin._ACTIVE_THREAD is None:
            return


def test_setup_uses_native_cron_runner_and_forwards_config(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context()
    plugin.register(ctx)
    result = json.loads(ctx.tools["obsidian_curator"]({
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
    }))
    wait(plugin)

    assert result["ok"] is True
    assert len(calls) == 1
    job = calls[0]
    assert job["id"].startswith("obsidian_curator_")
    assert job["enabled_toolsets"] == ["file", "skills"]
    assert job["skills"] == ["notes"]
    assert job["model"] == "model-x"
    assert job["provider"] == "provider-x"
    assert job["base_url"] == "https://example.invalid"
    assert job["reasoning_effort"] == "high"
    assert job["workdir"] == str(tmp_path)
    assert job["deliver"] == "local"
    assert "Map the entire vault recursively" in job["prompt"]


def test_setup_rejects_unsafe_toolsets(tmp_path):
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)
    res = json.loads(ctx.tools["obsidian_curator"]({
        "operation": "setup",
        "vault_path": str(tmp_path),
        "review_interval": 3,
        "curator_prompt": "Audit.",
        "enabled_toolsets": ["file", "terminal"],
    }))
    assert "error" in res
    assert "enabled_toolsets only supports" in res["error"]


def test_setup_passes_parent_context_as_untrusted_evidence(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context()
    plugin.register(ctx)
    parent = SimpleNamespace(session_id="parent-123", messages=[{"role": "user", "content": "Durable candidate fact."}])
    ctx.tools["obsidian_curator"]({
        "operation": "setup",
        "vault_path": str(tmp_path),
        "review_interval": 3,
        "curator_prompt": "Audit vault.",
    }, parent_agent=parent)
    wait(plugin)

    assert "Durable candidate fact." in calls[0]["prompt"]
    assert "NON-AUTHORITATIVE CANDIDATE EVIDENCE" in calls[0]["prompt"]


def test_interval_trigger_uses_cron_runner(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 2, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="s1", assistant_response="One", platform="telegram")
    assert not calls
    ctx.hooks["post_llm_call"](session_id="s1", assistant_response="Two", platform="telegram")
    wait(plugin)

    assert len(calls) == 1
    assert "This is the initial setup run" not in calls[0]["prompt"]
    assert ctx.state.get("session_activity_counts", {}) == {}


def test_cron_activity_is_ignored(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)
    ctx.hooks["post_llm_call"](session_id="cron_obsidian_curator_x_20260830", platform="cron")
    ctx.hooks["post_tool_call"](session_id="cron_obsidian_curator_x_20260830", platform="cron")
    assert ctx.state.get("session_activity_counts", {}) == {}
    assert not calls


def test_sessions_count_and_review_independently(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 2, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="telegram-a", assistant_response="Telegram one", platform="telegram")
    ctx.hooks["post_llm_call"](session_id="whatsapp-b", assistant_response="WhatsApp one", platform="whatsapp")
    assert ctx.state.get("session_activity_counts") == {"telegram-a": 1, "whatsapp-b": 1}
    assert not calls

    ctx.hooks["post_llm_call"](session_id="telegram-a", assistant_response="Telegram two", platform="telegram")
    wait(plugin)
    assert len(calls) == 1
    assert "Telegram one" in calls[0]["prompt"]
    assert "WhatsApp one" not in calls[0]["prompt"]
    assert ctx.state.get("session_activity_counts") == {"whatsapp-b": 1}


def test_switch_without_activity_does_not_flush_other_session(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 20, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="session-b", assistant_response="B activity", platform="telegram")
    ctx.hooks["pre_llm_call"](session_id="session-a", conversation_history=[], platform="telegram")
    ctx.hooks["on_session_finalize"](old_session_id="session-a", platform="telegram")

    assert not calls
    assert ctx.state.get("session_activity_counts") == {"session-b": 1}


def test_due_sessions_are_queued_and_run_sequentially(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    monkeypatch.setattr(plugin, "_deliver_notification", lambda *_: True)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    plugin._record_activity({"session_id": "telegram-a", "platform": "telegram"}, "turn")
    plugin._record_activity({"session_id": "whatsapp-b", "platform": "whatsapp"}, "turn")
    assert plugin._launch("telegram-a", initial_setup=False, origin_target="telegram:1")
    assert plugin._launch("whatsapp-b", initial_setup=False, origin_target="whatsapp:2")
    wait(plugin)

    assert len(calls) == 2
    assert ctx.state.get("session_activity_counts") == {}


def test_turn_added_during_run_survives_review(tmp_path, monkeypatch):
    plugin = load_plugin()
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def run_job(job):
        started.set()
        release.wait(timeout=2)
        return True, "doc", "done", None

    monkeypatch.setitem(sys.modules, "cron.scheduler", SimpleNamespace(run_job=run_job, tick=lambda *args, **kwargs: None))
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    assert plugin._launch("s1", initial_setup=False, origin_target="telegram:1")
    assert started.wait(timeout=1)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    release.set()
    wait(plugin)

    assert ctx.state.get("session_activity_counts") == {"s1": 1}


def test_failed_review_is_persisted_for_retry(tmp_path, monkeypatch):
    plugin = load_plugin()
    install_cron_mock(monkeypatch, result=(False, "doc", "", "Rate limited"))
    monkeypatch.setattr(plugin, "_deliver_notification", lambda *_: True)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    assert plugin._launch("s1", initial_setup=False, origin_target="telegram:1")
    wait(plugin)

    queue = ctx.state.get("pending_reviews")
    assert len(queue) == 1
    assert queue[0]["session_id"] == "s1"
    assert queue[0]["attempts"] == 2
    assert queue[0]["next_retry_at"] > 0
    assert ctx.state.get("session_activity_counts") == {"s1": 1}


def test_pending_reviews_are_restored_on_register(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    monkeypatch.setattr(plugin, "_deliver_notification", lambda *_: True)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    ctx.state.set("pending_reviews", [{
        "id": "rev_saved",
        "session_id": "s1",
        "reviewed_count": 1,
        "origin_target": "telegram:1",
        "job": {"id": "cron_job_1", "prompt": "test", "deliver": "local", "no_agent": False},
        "attempts": 1,
        "next_retry_at": 0,
    }])
    ctx.state.set("session_activity_counts", {"s1": 1})

    plugin.register(ctx)
    wait(plugin)

    assert len(calls) == 1
    assert ctx.state.get("session_activity_counts") == {}
    assert ctx.state.get("pending_reviews") == []


def test_setup_validation(tmp_path):
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)
    base = {"operation": "setup", "vault_path": str(tmp_path), "review_interval": 3}
    assert json.loads(ctx.tools["obsidian_curator"]({**base, "curator_prompt": " "})) == {"error": "curator_prompt must be a non-empty string."}
    assert json.loads(ctx.tools["obsidian_curator"]({**base, "curator_prompt": "A" * 12001})) == {"error": "curator_prompt must be at most 12000 characters."}
    assert "error" in json.loads(ctx.tools["obsidian_curator"]({**base, "curator_prompt": "ok", "skills": "bad"}))


def test_pre_tool_call_sandboxes_native_cron_session(tmp_path):
    plugin = load_plugin()
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 3, "curator_prompt": "Audit.", "blocked_tools": ["custom_tool"]})
    plugin.register(ctx)
    session_id = "cron_obsidian_curator_abc_20260830_120000"

    assert ctx.hooks["pre_tool_call"](session_id=session_id, tool_name="custom_tool", args={})["action"] == "block"
    assert ctx.hooks["pre_tool_call"](session_id=session_id, tool_name="terminal", args={})["action"] == "block"
    assert ctx.hooks["pre_tool_call"](session_id=session_id, tool_name="read_file", args={"path": "/etc/passwd"})["action"] == "block"
    note = tmp_path / "note.md"
    note.write_text("ok")
    assert ctx.hooks["pre_tool_call"](session_id=session_id, tool_name="read_file", args={"path": str(note)}) is None
    assert ctx.hooks["pre_tool_call"](session_id="parent", tool_name="read_file", args={"path": "/etc/passwd"}) is None


def test_prompt_keeps_governance_boundary(tmp_path):
    plugin = load_plugin()
    prompt = plugin._prompt(tmp_path, "s1", "Read HERMES.md as authoritative governance rules.", initial_setup=False)
    assert "unless explicitly designated as authoritative governance rules" in prompt
