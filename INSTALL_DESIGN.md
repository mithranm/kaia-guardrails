# kaia-guardrails Installation Design

**Purpose**: Install kaia-guardrails hooks into any project to guide Claude Code behavior

## Installation Command

```bash
# In target project directory
kaia-guardrails install

# Or from anywhere
kaia-guardrails install /path/to/project
```

## What Gets Installed

### 1. Hooks → `.claude/hooks/`

Copy relevant hook implementations:

```
.claude/hooks/
├── post_edit_vibelint_check.py         # Validates code after edits
├── agents_compliance_judge.py          # Checks AGENTS.md compliance
├── file_insertion_validator.py         # Prevents duplicate code
├── git_operations_guard.py             # Safe git operations
└── pre_edit_validation.py              # Pre-edit checks
```

### 2. Settings → `.claude/settings.local.json`

Create/update with hook configuration:

```json
{
  "hooks": {
    "enabled": true,
    "implementations": {
      "post_edit_vibelint_check": {
        "enabled": true,
        "priority": 50,
        "config": {
          "block_on_critical": true,
          "auto_fix": false
        }
      },
      "agents_compliance_judge": {
        "enabled": true,
        "priority": 40,
        "config": {
          "llm_endpoint": "${KAIA_JUDGE_LLM_URL}",
          "llm_model": "${KAIA_JUDGE_LLM_MODEL}"
        }
      },
      "file_insertion_validator": {
        "enabled": true,
        "priority": 60
      },
      "git_operations_guard": {
        "enabled": true,
        "priority": 30,
        "config": {
          "block_force_push": true,
          "require_approval_for": ["push", "force-push", "rebase"]
        }
      },
      "pre_edit_validation": {
        "enabled": true,
        "priority": 10
      }
    }
  },
  "environment": {
    "KAIA_JUDGE_LLM_URL": "http://localhost:8000",
    "KAIA_JUDGE_LLM_MODEL": "Qwen/Qwen2.5-7B-Instruct"
  }
}
```

### 3. Python Project Detection

If project has `pyproject.toml`:

**Check for vibelint:**
```bash
pip list | grep vibelint
```

If missing:
```
⚠️  vibelint not found. Install it?
   pip install vibelint

   Then configure in pyproject.toml:

   [tool.vibelint]
   include_globs = ["**/*.py"]
   exclude_globs = ["**/__pycache__/**", "**/.*"]

   [tool.vibelint.rules]
   # Add project-specific rules here
```

If present:
```
✅ vibelint found (v0.3.0)
```

**Check pyproject.toml for vibelint config:**
```bash
grep -q "\[tool.vibelint\]" pyproject.toml
```

If missing:
```
⚠️  No [tool.vibelint] section in pyproject.toml

   Add this minimal configuration:

   [tool.vibelint]
   include_globs = ["**/*.py"]
   exclude_globs = ["**/__pycache__/**", "**/.*"]
```

If present:
```
✅ vibelint configured in pyproject.toml
```

## CLI Implementation

```python
# cli.py additions

def install_command(args):
    """Install kaia-guardrails into a project."""
    project_root = Path(args.project_root or Path.cwd())

    print(f"📦 Installing kaia-guardrails to {project_root}")

    # 1. Create .claude directory
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    print(f"✅ Created {claude_dir}")

    # 2. Copy hooks
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    source_hooks = Path(__file__).parent / "hooks" / "implementation"
    essential_hooks = [
        "post_edit_vibelint_check.py",
        "agents_compliance_judge.py",
        "file_insertion_validator.py",
        "git_operations_guard.py",
        "pre_edit_validation.py",
    ]

    for hook_name in essential_hooks:
        src = source_hooks / hook_name
        dst = hooks_dir / hook_name
        if src.exists():
            shutil.copy(src, dst)
            print(f"  ✅ Installed {hook_name}")
        else:
            print(f"  ⚠️  Skipped {hook_name} (not found)")

    # 3. Create/update settings.local.json
    settings_file = claude_dir / "settings.local.json"
    if settings_file.exists():
        print(f"⚠️  {settings_file} exists, merging configuration...")
        with open(settings_file) as f:
            settings = json.load(f)
    else:
        settings = {}

    # Merge default hook config
    default_config = get_default_hook_config()
    settings["hooks"] = {**default_config, **settings.get("hooks", {})}

    # Prompt for LLM endpoint configuration
    if not settings.get("environment", {}).get("KAIA_JUDGE_LLM_URL"):
        print("\n🤖 LLM Configuration (for agents_compliance_judge)")
        llm_url = input("  LLM API URL [http://localhost:8000]: ") or "http://localhost:8000"
        llm_model = input("  LLM Model [Qwen/Qwen2.5-7B-Instruct]: ") or "Qwen/Qwen2.5-7B-Instruct"

        settings["environment"] = settings.get("environment", {})
        settings["environment"]["KAIA_JUDGE_LLM_URL"] = llm_url
        settings["environment"]["KAIA_JUDGE_LLM_MODEL"] = llm_model

    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"✅ Updated {settings_file}")

    # 4. Python project checks
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        print("\n🐍 Python project detected")

        # Check vibelint installation
        try:
            import vibelint
            print(f"  ✅ vibelint found (v{vibelint.__version__})")
        except ImportError:
            print("  ⚠️  vibelint not installed")
            print("     Install: pip install vibelint")

        # Check vibelint config
        with open(pyproject) as f:
            content = f.read()
            if "[tool.vibelint]" not in content:
                print("  ⚠️  No [tool.vibelint] section in pyproject.toml")
                print("     Add minimal config:")
                print("     [tool.vibelint]")
                print('     include_globs = ["**/*.py"]')
                print('     exclude_globs = ["**/__pycache__/**", "**/.*"]')
            else:
                print("  ✅ vibelint configured in pyproject.toml")

    print("\n✅ Installation complete!")
    print("\n📋 Next steps:")
    print("  1. Review .claude/settings.local.json")
    print("  2. For Python projects: ensure vibelint is installed and configured")
    print("  3. Restart Claude Code to load hooks")


def get_default_hook_config():
    """Get default hook configuration."""
    return {
        "enabled": True,
        "implementations": {
            "post_edit_vibelint_check": {
                "enabled": True,
                "priority": 50,
                "config": {
                    "block_on_critical": True,
                    "auto_fix": False,
                },
            },
            "agents_compliance_judge": {
                "enabled": True,
                "priority": 40,
                "config": {
                    "llm_endpoint": "${KAIA_JUDGE_LLM_URL}",
                    "llm_model": "${KAIA_JUDGE_LLM_MODEL}",
                },
            },
            "file_insertion_validator": {
                "enabled": True,
                "priority": 60,
            },
            "git_operations_guard": {
                "enabled": True,
                "priority": 30,
                "config": {
                    "block_force_push": True,
                    "require_approval_for": ["push", "force-push", "rebase"],
                },
            },
            "pre_edit_validation": {
                "enabled": True,
                "priority": 10,
            },
        },
    }
```

## Usage Examples

### Example 1: Fresh Python Project

```bash
$ cd my-new-project
$ kaia-guardrails install

📦 Installing kaia-guardrails to /Users/me/my-new-project
✅ Created /Users/me/my-new-project/.claude
  ✅ Installed post_edit_vibelint_check.py
  ✅ Installed agents_compliance_judge.py
  ✅ Installed file_insertion_validator.py
  ✅ Installed git_operations_guard.py
  ✅ Installed pre_edit_validation.py

🤖 LLM Configuration (for agents_compliance_judge)
  LLM API URL [http://localhost:8000]:
  LLM Model [Qwen/Qwen2.5-7B-Instruct]:
✅ Updated .claude/settings.local.json

🐍 Python project detected
  ⚠️  vibelint not installed
     Install: pip install vibelint
  ⚠️  No [tool.vibelint] section in pyproject.toml
     Add minimal config:
     [tool.vibelint]
     include_globs = ["**/*.py"]
     exclude_globs = ["**/__pycache__/**", "**/.*"]

✅ Installation complete!

📋 Next steps:
  1. Review .claude/settings.local.json
  2. For Python projects: ensure vibelint is installed and configured
  3. Restart Claude Code to load hooks
```

### Example 2: Existing Project with vibelint

```bash
$ cd killeraiagent
$ kaia-guardrails install

📦 Installing kaia-guardrails to /Users/me/killeraiagent
✅ Created /Users/me/killeraiagent/.claude
  ✅ Installed post_edit_vibelint_check.py
  ✅ Installed agents_compliance_judge.py
  ✅ Installed file_insertion_validator.py
  ✅ Installed git_operations_guard.py
  ✅ Installed pre_edit_validation.py

⚠️  .claude/settings.local.json exists, merging configuration...
✅ Updated .claude/settings.local.json

🐍 Python project detected
  ✅ vibelint found (v0.3.0)
  ✅ vibelint configured in pyproject.toml

✅ Installation complete!

📋 Next steps:
  1. Review .claude/settings.local.json
  2. For Python projects: ensure vibelint is installed and configured
  3. Restart Claude Code to load hooks
```

### Example 3: Non-Python Project

```bash
$ cd my-js-project
$ kaia-guardrails install

📦 Installing kaia-guardrails to /Users/me/my-js-project
✅ Created /Users/me/my-js-project/.claude
  ✅ Installed agents_compliance_judge.py
  ✅ Installed file_insertion_validator.py
  ✅ Installed git_operations_guard.py
  ✅ Installed pre_edit_validation.py
  ⚠️  Skipped post_edit_vibelint_check.py (Python-only)

🤖 LLM Configuration (for agents_compliance_judge)
  LLM API URL [http://localhost:8000]:
  LLM Model [Qwen/Qwen2.5-7B-Instruct]:
✅ Updated .claude/settings.local.json

✅ Installation complete!

📋 Next steps:
  1. Review .claude/settings.local.json
  2. Restart Claude Code to load hooks
```

## Hook Behavior After Installation

Once installed, Claude Code automatically loads hooks from `.claude/hooks/`:

### post_edit_vibelint_check.py
- **Trigger**: After Edit/Write tool usage
- **Action**: Runs vibelint on edited files
- **Block**: If critical security/architecture issues found

### agents_compliance_judge.py
- **Trigger**: Before any Claude Code operation
- **Action**: Checks compliance with AGENTS.md
- **Block**: If critical violations (wrong env, outside project, etc.)

### file_insertion_validator.py
- **Trigger**: Before Write/Edit operations
- **Action**: Detects duplicate code insertion
- **Block**: If inserting code that already exists

### git_operations_guard.py
- **Trigger**: Before git commands
- **Action**: Validates git operations (no force-push to main, etc.)
- **Block**: If unsafe operation detected

### pre_edit_validation.py
- **Trigger**: Before Edit operations
- **Action**: Validates file exists, backup if needed
- **Block**: Never (just warns)

## Uninstall Command

```bash
kaia-guardrails uninstall [project_root]
```

Removes:
- `.claude/hooks/*.py` (kaia-guardrails hooks only)
- `.claude/settings.local.json` hooks section
- Leaves `.claude/` directory if other files exist

## Configuration Updates

After installation, users can customize `.claude/settings.local.json`:

```json
{
  "hooks": {
    "implementations": {
      "post_edit_vibelint_check": {
        "enabled": false  // Disable this hook
      },
      "agents_compliance_judge": {
        "config": {
          "llm_endpoint": "http://my-llm-server:8080"  // Custom endpoint
        }
      }
    }
  }
}
```

## Future Enhancements

1. **Template configs**: `--template=python-strict`, `--template=javascript`
2. **Interactive setup**: Wizard-style configuration
3. **Hook marketplace**: Install community hooks
4. **Auto-update**: `kaia-guardrails update` to fetch latest hooks
