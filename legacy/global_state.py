raise ImportError(
    "Archived module: use canine_core.core.state.StateStore via BehaviorContext."
)
"""
PiDog Global State Management
==================================
This module defines and stores all of PiDog’s global state variables. These variables 
allow PiDog to maintain consistency across multiple modules, dynamically adjust its 
behavior, and react intelligently to its environment.

Key Features:
✅ Centralized state variables for PiDog.
✅ Supports adaptive behavior and memory-based learning.
✅ Implements **safe state modification and validation**.
✅ Introduces **persistent learning** for past obstacles and interactions.
✅ Expands error tracking into an **error log with timestamps**.

Usage:
- Import this module in other scripts to access PiDog's global state.
- Call functions to modify state safely and retrieve past experiences.

7-lynx
"""

import json  # noqa: E402
import time  # noqa: E402

# ✅ Global Variables for PiDog
position = (
    "standing"  # Tracks PiDog's posture (standing, sitting, lying down, crouching)
)
emotion = "neutral"  # Stores PiDog's current emotional state
speed = 80  # Default movement speed
idle_behavior = True  # Determines whether PiDog performs idle animations
obstacle_memory = []  # Stores locations of past obstacles
sound_direction = None  # Most recently detected sound source direction
touch_count = 0  # Tracks how many times PiDog has been touched
interaction_history = []  # Logs past user interactions
battery_level = 100  # Simulated battery level (0-100%)
active_mode = "idle"  # Default operational mode
environment_status = "clear"  # Tracks PiDog’s environmental awareness
error_log = []  # Expanded error tracking with timestamps

# ✅ Allowed Mode Transitions
VALID_MODE_TRANSITIONS = {
    "idle": ["patrol", "reacting", "sleeping"],
    "patrol": ["idle", "reacting"],
    "reacting": ["idle", "patrol"],
    "sleeping": ["idle"],
}


# ✅ Safe State Modification Function
def set_state(variable, value):
    """
    Safely modifies a global state variable with validation.

    Parameters:
    - variable (str): The name of the global variable to modify.
    - value (any): The new value to assign.

    Returns:
    - (bool) True if successful, False if invalid.
    """
    if variable not in globals():
        print(f"❌ ERROR: `{variable}` is not a valid global state variable!")
        return False

    if variable == "active_mode" and value not in VALID_MODE_TRANSITIONS.get(
        active_mode, []
    ):
        print(
            f"🚫 INVALID MODE TRANSITION: Cannot switch from {active_mode} to {value}!"
        )
        return False

    globals()[variable] = value
    print(f"✅ State Updated: {variable} → {value}")
    return True


# ✅ Persistent Learning System
def save_state():
    """Stores global state variables in a JSON file."""
    persistent_data = {
        "obstacle_memory": obstacle_memory,
        "interaction_history": interaction_history,
        "error_log": error_log,
    }
    with open("pidog_state.json", "w") as file:
        json.dump(persistent_data, file)
    print("📁 PiDog state saved successfully.")


def load_state():
    """Loads global state variables from a JSON file."""
    try:
        with open("pidog_state.json", "r") as file:
            persistent_data = json.load(file)
            global obstacle_memory, interaction_history, error_log
            obstacle_memory = persistent_data.get("obstacle_memory", [])
            interaction_history = persistent_data.get("interaction_history", [])
            error_log = persistent_data.get("error_log", [])
        print("📁 PiDog state loaded successfully.")
    except FileNotFoundError:
        print("⚠️ No previous state found. Starting fresh.")


# ✅ Error Logging System
def log_error(error_message):
    """
    Logs an error with a timestamp.

    Parameters:
    - error_message (str): The error description.
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    error_entry = {"timestamp": timestamp, "error": error_message}
    error_log.append(error_entry)
    print(f"⚠️ ERROR LOGGED: {error_message} @ {timestamp}")


# ✅ Debugging Functions
def print_global_state():
    """Prints all global state variables in a readable format."""
    state_snapshot = {
        var: globals()[var]
        for var in globals()
        if not var.startswith("__") and var not in ["print_global_state", "set_state"]
    }
    print("\n📊 PiDog Global State Overview:")
    for key, value in state_snapshot.items():
        print(f"🔹 {key}: {value}")


def reset_global_state():
    """Resets PiDog’s global state to default values."""
    global position, emotion, speed, idle_behavior, obstacle_memory, sound_direction, touch_count
    global interaction_history, battery_level, active_mode, environment_status, error_log

    position = "standing"
    emotion = "neutral"
    speed = 80
    idle_behavior = True
    obstacle_memory.clear()
    sound_direction = None
    touch_count = 0
    interaction_history.clear()
    battery_level = 100
    active_mode = "idle"
    environment_status = "clear"
    error_log.clear()

    print("🔄 PiDog global state has been reset to default values.")


# ✅ Example Usage (for debugging)
if __name__ == "__main__":
    load_state()  # ✅ Load previous state at startup
    print_global_state()  # ✅ Prints all current state variables
    reset_global_state()  # ✅ Resets PiDog’s state
    save_state()  # ✅ Saves the reset state
