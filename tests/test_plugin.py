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


class Lifecycle:
    def __init__(self):
        self.requests = []
        self.error = None

    def launch(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(subagent_id=f"child-{len(self.requests)}")


class Context:
    def __init__(self, config=None, parent_agent=None):
        self.config = config or {}
        self.state = State()
        self.subagent_lifecycle = Lifecycle()
        self._parent_agent = parent_agent
        self.hooks = {}
        self.tools = {}

    def _parent_agent_resolver(self):
        return self._parent_agent

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, name, handler, **kwargs):
        self.tools[name] = handler


def test_setup_launches_native_agent_with_recursive_mapping_prompt(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    ctx = Context()
    plugin.register(ctx)

    result = json.loads(
        ctx.tools["obsidian_curator"](
            {"operation": "setup", "vault_path": str(tmp_path), "review_interval": 3}
        )
    )

    assert result == {"ok": True, "status": "active", "vault_path": str(tmp_path.resolve())}
    assert ctx.config["vault_path"] == str(tmp_path.resolve())
    assert ctx.config["review_interval"] == 3
    assert len(ctx.subagent_lifecycle.requests) == 1
    req = ctx.subagent_lifecycle.requests[0]
    assert req.role == "orchestrator"
    assert "map the entire vault recursively" in req.goal
    assert "search_files with pagination" in req.goal
    assert "Read every readable vault file completely with read_file" in req.goal
    assert "Do not write or patch anything until this full-vault mapping is complete." in req.goal


def test_setup_passes_parent_context_when_available(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    parent = SimpleNamespace(
        session_id="parent-123",
        messages=[
            {"role": "user", "content": "Fact: mangrove fringe reduces erosion by 66 percent."},
            {"role": "assistant", "content": "Recorded."},
        ],
    )
    ctx = Context(parent_agent=parent)
    plugin.register(ctx)

    ctx.tools["obsidian_curator"](
        {"operation": "setup", "vault_path": str(tmp_path), "review_interval": 3},
        parent_agent=parent,
    )

    req = ctx.subagent_lifecycle.requests[0]
    assert req.parent_session_id == "parent-123"
    assert "mangrove fringe reduces erosion by 66 percent" in req.context
    assert "NON-AUTHORITATIVE CANDIDATE EVIDENCE" in req.context


def test_subsequent_activity_triggers_review_without_initial_setup_prompt(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 2})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="s1", platform="telegram", conversation_history=[])
    assert not ctx.subagent_lifecycle.requests
    assert ctx.state.get("activity_count") == 1

    ctx.hooks["post_llm_call"](session_id="s2", platform="telegram", conversation_history=[])
    assert len(ctx.subagent_lifecycle.requests) == 1
    req = ctx.subagent_lifecycle.requests[0]
    assert "This is the initial setup run" not in req.goal


def test_activity_counter_resets_on_first_turn_of_active_child(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 2})
    plugin.register(ctx)

    ctx.hooks["post_llm_call"](session_id="s1", platform="telegram", conversation_history=[])
    ctx.hooks["post_llm_call"](session_id="s2", platform="telegram", conversation_history=[])
    assert ctx.state.get("activity_count") == 2
    req = ctx.subagent_lifecycle.requests[0]

    ctx.hooks["subagent_start"](child_session_id="curator-child-1", child_goal=req.goal)
    assert getattr(plugin, "_ACTIVE_CHILD") == "curator-child-1"

    # Pre LLM call first turn resets
    ctx.hooks["pre_llm_call"](session_id="curator-child-1", platform="subagent", is_first_turn=True)
    assert ctx.state.get("activity_count") == 0


def test_curator_child_activity_is_ignored_for_anti_loop(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 1})
    plugin.register(ctx)
    setattr(plugin, "_ACTIVE_CHILD", "curator-child-1")

    ctx.hooks["post_llm_call"](session_id="curator-child-1", platform="subagent", conversation_history=[])
    assert not ctx.subagent_lifecycle.requests
    assert ctx.state.get("activity_count", 0) == 0


def test_unrelated_subagent_still_increments_counter(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    ctx = Context({"vault_path": str(tmp_path), "review_interval": 2})
    plugin.register(ctx)
    setattr(plugin, "_ACTIVE_CHILD", "curator-child-1")

    ctx.hooks["post_llm_call"](session_id="other-subagent", platform="subagent", conversation_history=[])
    assert ctx.state.get("activity_count") == 1


def test_subagent_stop_resets_active_child_and_notifies(monkeypatch):
    plugin = load_plugin()
    ctx = Context()
    notices = []
    monkeypatch.setattr(plugin, "_parent_review_callback", notices.append)
    plugin.register(ctx)
    setattr(plugin, "_ACTIVE_CHILD", "curator-child-1")

    ctx.hooks["subagent_stop"](
        child_session_id="curator-child-1",
        child_summary="Obsidian: updated coastal restoration note.",
        child_status="completed",
    )

    assert getattr(plugin, "_ACTIVE_CHILD") is None
    assert notices == ["Obsidian: updated coastal restoration note."]


def test_setup_quotes_arbitrary_vault_path_in_prompt(tmp_path, monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "SubagentLaunchRequest", SimpleNamespace)
    vault = tmp_path / "vault\nwith newline"
    vault.mkdir()
    ctx = Context()
    plugin.register(ctx)

    ctx.tools["obsidian_curator"](
        {"operation": "setup", "vault_path": str(vault), "review_interval": 3}
    )

    goal = ctx.subagent_lifecycle.requests[0].goal
    assert json.dumps(str(vault.resolve())) in goal
    assert f"at:\n{vault.resolve()}" not in goal


def test_context_stays_under_native_lifecycle_limit_and_keeps_latest_turn():
    plugin = load_plugin()
    history = [
        {"role": "user", "content": "old" * 12000},
        {"role": "assistant", "content": "latest durable fact"},
    ]

    context = plugin._format_context(history)

    assert context is not None
    assert len(context) <= 32000
    assert "latest durable fact" in context
    assert "prior history truncated" in context


def test_setup_rejects_non_directory():
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)

    result = json.loads(
        ctx.tools["obsidian_curator"](
            {"operation": "setup", "vault_path": "/path/does/not/exist/ever", "review_interval": 3}
        )
    )

    assert result == {"error": "vault_path must be an existing directory."}
    assert "vault_path" not in ctx.config


def test_setup_rejects_invalid_interval(tmp_path):
    plugin = load_plugin()
    ctx = Context()
    plugin.register(ctx)

    result = json.loads(
        ctx.tools["obsidian_curator"](
            {"operation": "setup", "vault_path": str(tmp_path), "review_interval": 0}
        )
    )

    assert result == {"error": "review_interval must be a positive integer."}
    assert "vault_path" not in ctx.config


def test_manifest_is_valid():
    manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "name: obsidian-curator" in manifest
    assert "provides_tools:\n  - obsidian_curator" in manifest
    assert "provides_hooks:" in manifest
    assert "- pre_llm_call" in manifest
    assert "- post_llm_call" in manifest
    assert "- subagent_start" in manifest
    assert "- subagent_stop" in manifest
    assert "vault_path:" in manifest
    assert "review_interval:" in manifest
