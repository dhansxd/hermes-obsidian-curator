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
    class CronTracker(list):
        def __init__(self):
            super().__init__()
            self.runs = []
            self.deliveries = []

    calls = CronTracker()

    def run_job(job):
        calls.append(job)
        calls.runs.append(job)
        return result

    def deliver_result(job, content, **kwargs):
        calls.deliveries.append({"job": job, "content": content})
        return None

    monkeypatch.setitem(
        sys.modules,
        "cron.scheduler",
        SimpleNamespace(run_job=run_job, _deliver_result=deliver_result, tick=lambda *args, **kwargs: None),
    )
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


def test_interval_twenty_triggers_exactly_on_twentieth_turn(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 20, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    for turn in range(19):
        ctx.hooks["post_llm_call"](session_id="s20", assistant_response=str(turn), platform="telegram")
    assert not calls
    assert ctx.state.get("session_activity_counts") == {"s20": 19}

    ctx.hooks["post_llm_call"](session_id="s20", assistant_response="twenty", platform="telegram")
    wait(plugin)

    assert len(calls) == 1
    assert ctx.state.get("session_activity_counts") == {}


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


def test_shutdown_or_exit_finalize_does_not_flush_session(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 20, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="session-a", assistant_response="A activity", platform="telegram")
    assert ctx.state.get("session_activity_counts") == {"session-a": 1}

    ctx.hooks["on_session_finalize"](session_id="session-a", reason="shutdown", platform="telegram")
    ctx.hooks["on_session_finalize"](session_id="session-a", reason="process_exit", platform="telegram")

    assert not calls
    assert ctx.state.get("session_activity_counts") == {"session-a": 1}


def test_finalize_uses_native_origin_saved_during_whatsapp_turn(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    env = {
        "HERMES_SESSION_PLATFORM": "whatsapp",
        "HERMES_SESSION_CHAT_ID": "2362534006947@lid",
        "HERMES_SESSION_THREAD_ID": "",
    }
    monkeypatch.setitem(
        sys.modules,
        "gateway.session_context",
        SimpleNamespace(get_session_env=lambda name, default="": env.get(name, default)),
    )
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 20, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="session-a", assistant_response="A activity", platform="whatsapp")
    assert ctx.state.get("session_origins")["session-a"]["chat_id"] == "2362534006947@lid"
    env.clear()
    ctx.hooks["on_session_finalize"](session_id="session-a", reason="new_session", platform="whatsapp")
    wait(plugin)

    job = calls[0]
    assert job["deliver"] == "origin"
    assert job["origin"]["platform"] == "whatsapp"
    assert calls.deliveries[0]["job"] is job


def test_finalize_migrates_legacy_platform_origin(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 20, "curator_prompt": "Audit vault."})
    ctx.state.set("platform_queues", {"telegram": {"origin_target": "telegram:8804634959"}})
    ctx.state.set("session_activity_counts", {"old-session": 1})
    plugin.register(ctx)

    ctx.hooks["on_session_finalize"](old_session_id="old-session", reason="new_session", platform="telegram")
    wait(plugin)

    assert calls[0]["origin"] == {"platform": "telegram", "chat_id": "8804634959", "thread_id": None}
    assert calls[0]["deliver"] == "origin"


def test_format_summary_extracts_final_marker_and_strips_preamble():
    plugin = load_plugin()
    raw = (
        "Now I have a solid picture. Let me analyze candidate evidence.\n"
        "📝 Obsidian Review: Updated Mac to Dyra2 wired guide.\n"
        "Extra noise."
    )
    assert plugin._format_summary(raw) == "📝 Obsidian Review: Updated Mac to Dyra2 wired guide. Extra noise."


def test_due_sessions_are_queued_and_run_sequentially(tmp_path, monkeypatch):
    plugin = load_plugin()
    calls = install_cron_mock(monkeypatch)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)

    plugin._record_activity({"session_id": "telegram-a", "platform": "telegram"}, "turn")
    plugin._record_activity({"session_id": "whatsapp-b", "platform": "whatsapp"}, "turn")
    assert plugin._launch("telegram-a", initial_setup=False, origin={"platform": "telegram", "chat_id": "1"})
    assert plugin._launch("whatsapp-b", initial_setup=False, origin={"platform": "whatsapp", "chat_id": "2"})
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

    monkeypatch.setitem(
        sys.modules,
        "cron.scheduler",
        SimpleNamespace(run_job=run_job, _deliver_result=lambda *args, **kwargs: None, tick=lambda *args, **kwargs: None),
    )
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    assert plugin._launch("s1", initial_setup=False, origin={"platform": "telegram", "chat_id": "1"})
    assert started.wait(timeout=1)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    release.set()
    wait(plugin)

    assert ctx.state.get("session_activity_counts") == {"s1": 1}


def test_failed_review_is_persisted_for_retry(tmp_path, monkeypatch):
    plugin = load_plugin()
    install_cron_mock(monkeypatch, result=(False, "doc", "", "Rate limited"))
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    plugin.register(ctx)
    plugin._record_activity({"session_id": "s1", "platform": "telegram"}, "turn")
    assert plugin._launch("s1", initial_setup=False, origin={"platform": "telegram", "chat_id": "1"})
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
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1, "curator_prompt": "Audit vault."})
    ctx.state.set("pending_reviews", [{
        "id": "rev_saved",
        "session_id": "s1",
        "reviewed_count": 1,
        "job": {
            "id": "cron_job_1",
            "name": "Obsidian curator",
            "prompt": "test",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "1"},
            "no_agent": False,
        },
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
