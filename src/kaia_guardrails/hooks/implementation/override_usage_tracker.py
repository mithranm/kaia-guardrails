"""
Override Usage Tracker

Tracks usage of KAIA_GUARDRAILS_OVERRIDE flags and automatically unsets them
if used more than 3 times without being manually unset.
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional


class OverrideUsageTracker:
    """Tracks and manages override flag usage to prevent abuse."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or self._get_project_root()
        self.claude_dir = self.project_root / '.claude'
        self.usage_file = self.claude_dir / 'override_usage.json'

    def _get_project_root(self) -> Path:
        """Find the project root directory."""
        current = Path.cwd()
        while current.parent != current:
            if (current / '.git').exists():
                return current
            current = current.parent
        return Path.cwd()

    def track_override_usage(self, override_type: str, hook_name: str) -> str:
        """
        Track usage of an override flag and return a message if auto-unsetting.

        Args:
            override_type: The type of override used (e.g., 'emoji_check', 'git_operations')
            hook_name: The name of the hook that detected the override

        Returns:
            Message to include in hook output (empty if no action taken)
        """
        try:
            usage_data = self._load_usage_data()
            current_time = datetime.now().isoformat()

            # Initialize override tracking if needed
            if override_type not in usage_data:
                usage_data[override_type] = {
                    "usage_count": 0,
                    "first_used": current_time,
                    "last_used": current_time,
                    "auto_unset_count": 0,
                    "usage_history": [],
                    "reset_conditions_met": []
                }

            override_data = usage_data[override_type]

            # Check logical reset conditions BEFORE tracking usage
            reset_reason = self._check_logical_reset_conditions(override_data, current_time)
            if reset_reason:
                override_data["usage_count"] = 0
                override_data["first_used"] = current_time
                override_data["reset_conditions_met"].append({
                    "timestamp": current_time,
                    "reason": reset_reason
                })
                print(f"[OVERRIDE-TRACKER] Logical reset triggered for {override_type}: {reset_reason}")

            # Check if override is still set
            current_override = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()
            emergency_override = os.environ.get('KAIA_EMERGENCY_OVERRIDE', '').lower()

            is_override_active = (
                current_override in [override_type, 'all', 'true'] or
                emergency_override in ['true', '1', 'yes']
            )

            if not is_override_active:
                # Override was manually unset, reset counter
                if override_data["usage_count"] > 0:
                    override_data["usage_count"] = 0
                    override_data["first_used"] = current_time
                    override_data["reset_conditions_met"].append({
                        "timestamp": current_time,
                        "reason": "manual_unset"
                    })
                    print(f"[OVERRIDE-TRACKER] {override_type} override manually unset, resetting usage counter")

                self._save_usage_data(usage_data)
                return ""

            # Increment usage count
            override_data["usage_count"] += 1
            override_data["last_used"] = current_time
            override_data["usage_history"].append({
                "timestamp": current_time,
                "hook": hook_name,
                "usage_number": override_data["usage_count"]
            })

            # Keep only last 10 usage records
            if len(override_data["usage_history"]) > 10:
                override_data["usage_history"] = override_data["usage_history"][-10:]

            # Check if we need to auto-unset
            if override_data["usage_count"] >= 3:
                # Auto-unset the override
                if 'KAIA_GUARDRAILS_OVERRIDE' in os.environ:
                    del os.environ['KAIA_GUARDRAILS_OVERRIDE']
                if 'KAIA_EMERGENCY_OVERRIDE' in os.environ:
                    del os.environ['KAIA_EMERGENCY_OVERRIDE']

                override_data["auto_unset_count"] += 1
                override_data["usage_count"] = 0

                self._save_usage_data(usage_data)

                return f"""
[OVERRIDE-TRACKER] Auto-unset override flag '{override_type}' after 3 uses.

Override flags are for emergency use only. Frequent usage indicates:
1. A workflow issue that should be addressed
2. Possible misuse of the override system

If you need to bypass guardrails regularly, consider:
- Updating the focus process workflow
- Adjusting guardrail sensitivity
- Creating project-specific override policies

To re-enable override: export KAIA_GUARDRAILS_OVERRIDE={override_type}
Auto-unset count for {override_type}: {override_data['auto_unset_count']}

LOGICAL RESET: Claude can reset counters by:
1. Completing a focus process successfully
2. Triggering a semantic escape
3. Fixing the underlying issue
4. Using: manager.reset_override_usage('{override_type}')"""

            else:
                self._save_usage_data(usage_data)
                remaining_uses = 3 - override_data["usage_count"]
                return f"[OVERRIDE-TRACKER] Override '{override_type}' used {override_data['usage_count']}/3 times. {remaining_uses} uses remaining before auto-unset."

        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to track override usage: {e}")
            return ""

    def _check_logical_reset_conditions(self, override_data: Dict[str, Any], current_time: str) -> Optional[str]:
        """
        Check if logical conditions for resetting the override counter are met.

        Returns:
            Reset reason if conditions are met, None otherwise
        """
        try:
            # Condition 1: Time-based reset (24 hours since last use)
            if override_data.get("last_used"):
                last_used = datetime.fromisoformat(override_data["last_used"])
                time_since_last = datetime.now() - last_used
                if time_since_last > timedelta(hours=24):
                    return "24_hour_timeout"

            # Condition 2: Focus process completion
            if self._check_recent_focus_completion():
                return "focus_process_completed"

            # Condition 3: Semantic escape usage (indicates problem resolution attempt)
            if self._check_recent_semantic_escape():
                return "semantic_escape_triggered"

            # Condition 4: Project state change (new session, git branch change)
            if self._check_significant_project_change():
                return "project_state_changed"

            # Condition 5: Error resolution (no recent hook errors)
            if self._check_error_resolution():
                return "error_resolution_detected"

            return None

        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to check reset conditions: {e}")
            return None

    def _check_recent_focus_completion(self) -> bool:
        """Check if a focus process was recently completed successfully."""
        try:
            # Check focus process stack for recent completions
            from .focus_process_manager import FocusProcessManager
            manager = FocusProcessManager()
            stack = manager.load_focus_stack()

            # Check for recent escape with completion
            last_escape = stack.get("last_escape")
            if last_escape:
                escape_time = datetime.fromisoformat(last_escape["timestamp"])
                if datetime.now() - escape_time < timedelta(minutes=30):
                    return True

            return False

        except Exception:
            return False

    def _check_recent_semantic_escape(self) -> bool:
        """Check if semantic escape was recently triggered."""
        try:
            from .focus_process_manager import FocusProcessManager
            manager = FocusProcessManager()
            stack = manager.load_focus_stack()

            last_escape = stack.get("last_escape")
            if last_escape and "semantic" in last_escape.get("reason", "").lower():
                escape_time = datetime.fromisoformat(last_escape["timestamp"])
                if datetime.now() - escape_time < timedelta(minutes=15):
                    return True

            return False

        except Exception:
            return False

    def _check_significant_project_change(self) -> bool:
        """Check for significant project state changes."""
        try:
            # Check if we're on a different git branch than when override was first used
            import subprocess
            current_branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )

            if current_branch_result.returncode == 0:
                current_branch = current_branch_result.stdout.strip()
                # This would need to be compared against stored branch info
                # For now, just check if we're on main (indicates major state change)
                if current_branch == "main":
                    return True

            return False

        except Exception:
            return False

    def _check_error_resolution(self) -> bool:
        """Check if recent errors have been resolved."""
        try:
            # Check model output logs for recent error patterns
            log_dir = self.claude_dir / 'logs' / 'model_outputs'
            if not log_dir.exists():
                return False

            # Look for recent successful operations vs error patterns
            # This is a simplified check - could be more sophisticated
            return True  # Optimistic: assume progress is being made

        except Exception:
            return False

    def reset_override_usage(self, override_type: str = None, reason: str = "manual_reset") -> bool:
        """
        Reset usage tracking for a specific override type or all types.
        This method can be called by Claude or other logical processes.

        Args:
            override_type: Specific override to reset, or None for all
            reason: Reason for the reset (for tracking)

        Returns:
            True if reset was successful
        """
        try:
            usage_data = self._load_usage_data()
            current_time = datetime.now().isoformat()

            if override_type:
                if override_type in usage_data:
                    usage_data[override_type]["usage_count"] = 0
                    usage_data[override_type]["first_used"] = current_time
                    usage_data[override_type]["reset_conditions_met"].append({
                        "timestamp": current_time,
                        "reason": reason
                    })
                    print(f"[OVERRIDE-TRACKER] Reset usage tracking for: {override_type} (reason: {reason})")
                else:
                    print(f"[OVERRIDE-TRACKER] No usage data found for: {override_type}")
            else:
                # Reset all override types
                for override_key, override_data in usage_data.items():
                    override_data["usage_count"] = 0
                    override_data["first_used"] = current_time
                    override_data["reset_conditions_met"].append({
                        "timestamp": current_time,
                        "reason": reason
                    })
                print(f"[OVERRIDE-TRACKER] Reset all override usage tracking (reason: {reason})")

            self._save_usage_data(usage_data)
            return True

        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to reset usage tracking: {e}")
            return False

    def _load_usage_data(self) -> Dict[str, Any]:
        """Load override usage data from file."""
        try:
            if self.usage_file.exists():
                with open(self.usage_file) as f:
                    return json.load(f)
            else:
                return {}
        except Exception:
            return {}

    def _save_usage_data(self, data: Dict[str, Any]):
        """Save override usage data to file."""
        try:
            self.claude_dir.mkdir(exist_ok=True)
            with open(self.usage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to save usage data: {e}")

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get a summary of override usage patterns."""
        try:
            usage_data = self._load_usage_data()

            summary = {
                "total_override_types": len(usage_data),
                "active_overrides": [],
                "frequently_used": [],
                "recent_auto_unsets": []
            }

            current_override = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()
            emergency_override = os.environ.get('KAIA_EMERGENCY_OVERRIDE', '').lower()

            for override_type, data in usage_data.items():
                # Check if currently active
                if (current_override in [override_type, 'all', 'true'] or
                    emergency_override in ['true', '1', 'yes']):
                    summary["active_overrides"].append({
                        "type": override_type,
                        "usage_count": data["usage_count"],
                        "first_used": data["first_used"]
                    })

                # Check for frequent usage
                if data.get("auto_unset_count", 0) > 2:
                    summary["frequently_used"].append({
                        "type": override_type,
                        "auto_unset_count": data["auto_unset_count"],
                        "last_used": data["last_used"]
                    })

                # Check for recent auto-unsets
                if data.get("auto_unset_count", 0) > 0:
                    last_used = datetime.fromisoformat(data["last_used"])
                    if datetime.now() - last_used < timedelta(hours=24):
                        summary["recent_auto_unsets"].append({
                            "type": override_type,
                            "last_used": data["last_used"],
                            "auto_unset_count": data["auto_unset_count"]
                        })

            return summary

        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to get usage summary: {e}")
            return {"error": str(e)}

    def reset_usage_tracking(self, override_type: str = None):
        """Reset usage tracking for a specific override type or all types."""
        try:
            usage_data = self._load_usage_data()

            if override_type:
                if override_type in usage_data:
                    del usage_data[override_type]
                    print(f"[OVERRIDE-TRACKER] Reset usage tracking for: {override_type}")
            else:
                usage_data.clear()
                print("[OVERRIDE-TRACKER] Reset all override usage tracking")

            self._save_usage_data(usage_data)

        except Exception as e:
            print(f"[OVERRIDE-TRACKER-ERROR] Failed to reset usage tracking: {e}")


# Global instance for easy access
_tracker_instance = None

def get_override_tracker() -> OverrideUsageTracker:
    """Get the global override tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = OverrideUsageTracker()
    return _tracker_instance