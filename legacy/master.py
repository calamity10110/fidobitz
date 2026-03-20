raise ImportError(
    "Archived module: replaced by canine_core.core.orchestrator and control.py."
)
#!/usr/bin/env python3
"""
PiDog Master Control Script
==================================
This script serves as the central controller for PiDog’s behavior system, managing 
module execution, state-based transitions, and real-time decision-making.

Key Features:
✅ Dynamically loads and executes behavior modules.
✅ Allows manual module selection with user-configurable keyboard interruption.
✅ Implements a **shuffled queue** with memory to reduce back-to-back repetitions.
✅ Tracks active threads and prevents accumulation.
✅ Logs errors with detailed traceback for debugging.
✅ Uses `global_state.py` for **state-aware execution**, ensuring PiDog adapts dynamically.

7-lynx
"""

import time  # noqa: E402
import threading  # noqa: E402
import importlib  # noqa: E402
import keyboard  # noqa: E402
import traceback  # noqa: E402
import random  # noqa: E402
from . import global_state  # noqa: E402  # ✅ Integrated state tracking

# ✅ Define Available Modules (Updated for new structure)
module_names = {
    "smart_patrol": "src.behaviors.smart_patrol",
    "smarter_patrol": "src.behaviors.smarter_patrol",
    "voice_patrol": "src.behaviors.voice_patrol",
    "voice_control": "src.behaviors.whisper_voice_control",
    "idle_behavior": "src.behaviors.idle_behavior",
    "emotion": "src.core.emotions",
    "find_open_space": "src.ai.find_open_space",
    "turn_toward_noise": "src.utils.turn_toward_noise",
    "reactions": "src.behaviors.reactions",
    "actions": "src.behaviors.actions",
}

# ✅ Track Active Threads
active_threads = []
recently_used = []  # ✅ Prevents repeating recent modules


def load_module(module_name):
    """
    Dynamically load a module and handle errors.

    Parameters:
    - module_name (str): The name of the module to load.

    Returns:
    - (function) The module's `start_behavior` function, or None if loading fails.
    """
    try:
        module = importlib.import_module(module_name)
        if hasattr(module, "start_behavior"):  # ✅ Validate function exists
            return module.start_behavior
        else:
            print(
                f"⚠️ WARNING: '{module_name}' does not have 'start_behavior'. Check implementation."
            )
            return None
    except ModuleNotFoundError:
        print(f"❌ ERROR: Module '{module_name}' not found! Skipping.")
    except Exception as e:
        print(f"⚠️ Unexpected error while loading '{module_name}': {e}")
        traceback.print_exc()
    return None


def run_module_for_time(module_name, duration):
    """
    Run a module for a set duration in a separate thread.

    Parameters:
    - module_name (str): The module to execute.
    - duration (int): Time in seconds before switching modules.
    """
    behavior_function = load_module(module_name)
    if not behavior_function:
        return

    global_state.active_mode = module_name  # ✅ Track the active module globally
    print(f"🚀 Running {module_name} (Active Mode: {global_state.active_mode})")

    # ✅ Track and manage active threads
    thread = threading.Thread(target=behavior_function, daemon=True)
    active_threads.append(thread)
    thread.start()

    start_time = time.time()
    while time.time() - start_time < duration:
        if keyboard.is_pressed(
            global_state.interrupt_key
        ):  # ✅ Customizable interruption key
            print("\n🔴 INTERRUPTED! Select a new module.")
            thread.join()  # ✅ Graceful shutdown before switching
            active_threads.remove(thread)
            global_state.active_mode = "idle"  # ✅ Reset active state
            select_module_manually()
            return
        time.sleep(0.1)

    print(f"⏳ {module_name} completed.")
    active_threads.remove(thread)
    global_state.active_mode = "idle"  # ✅ Reset active mode after completion


def select_module_manually():
    """
    Displays a numbered list of available modules and allows user selection with timeout.

    If no selection is made within **30 seconds**, auto-selection resumes.
    """
    print("\n🚀 Available Modules:")
    module_list = list(module_names.keys())

    for i, module in enumerate(module_list, 1):
        print(f"{i}. {module}")

    print(f"{len(module_list) + 1}. Resume Random Module Selection")

    start_time = time.time()
    while time.time() - start_time < 30:  # ✅ Timeout after 30 seconds
        try:
            choice = input(
                "\n🔢 Enter module number to run (or wait to resume auto-selection): "
            )
            if not choice:
                continue  # ✅ Ignore empty input

            choice = int(choice)
            if 1 <= choice <= len(module_list):
                run_module_for_time(module_list[choice - 1], duration=10)
                return
            elif choice == len(module_list) + 1:
                print("\n🔄 Resuming automatic module selection...")
                return
            else:
                print("❌ Invalid selection. Try again.")
        except ValueError:
            print("⚠️ Please enter a valid number.")

    print("\n⏳ Timeout reached. Resuming automatic module selection...")


# ✅ Enhanced Random Module Selection
def shuffled_module_queue():
    """
    Generates a shuffled queue of modules, ensuring variety while avoiding repetition.

    Returns:
    - (list) A shuffled list of module names.
    """
    module_list = list(module_names.keys())
    random.shuffle(module_list)

    # ✅ Prevent back-to-back repetition by ensuring variety
    while module_list[0] in recently_used:
        random.shuffle(module_list)

    return module_list


def main():
    """Main function for the modular system master controller."""
    module_queue = shuffled_module_queue()  # ✅ Ensures non-repetitive selection

    while True:
        if not module_queue:  # ✅ Re-shuffle when queue is empty
            module_queue = shuffled_module_queue()

        selected_module = module_queue.pop(0)  # ✅ Select from queue

        recently_used.append(selected_module)
        if len(recently_used) > 3:  # ✅ Keep a short-term history of last 3 modules
            recently_used.pop(0)

        run_module_for_time(selected_module, duration=10)


if __name__ == "__main__":
    main()
