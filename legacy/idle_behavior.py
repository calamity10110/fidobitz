#!/usr/bin/env python3
import time
import threading
import random

try:
    # Prefer real actions if available
    from action import (
        wag_tail,
        stop_and_stand,
        bark,
        wave_paw,
        turn_left_medium,
        turn_right_medium,
    )  # type: ignore
except Exception:
    # Fallback stubs so this archived script doesn't error if action.py is missing
    def wag_tail():
        pass

    def stop_and_stand():
        pass

    def bark():
        pass

    def wave_paw():
        pass

    def turn_left_medium():
        pass

    def turn_right_medium():
        pass


from pidog import Pidog
from pidog.b9_rgb import RGB
from pidog.sound_sensor import SoundSensor

# ✅ Initialize PiDog and sound sensor
dog = Pidog()
rgb = RGB(dog)
sound_sensor = SoundSensor(dog)

exit_flag = False  # ✅ Allows controlled exit when needed

# ✅ Idle behaviors pulled from `action.py`
idle_actions = [wag_tail, stop_and_stand, bark, wave_paw]


def listen_for_sound():
    """Continuously listen for incoming sounds and react based on direction."""
    while not exit_flag:
        if sound_sensor.isdetected():
            direction = sound_sensor.read()
            print(f"🔊 Sound detected! Adjusting direction {direction}°")
            react_to_sound(direction)
        time.sleep(0.5)  # ✅ Prevent unnecessary CPU usage


def react_to_sound(direction):
    """PiDog reacts by barking and turning toward sound."""
    rgb.set_color((255, 0, 0))  # ✅ Red flash effect for alertness
    rgb.flash(2)

    dog.head_move([[direction, 0, 0]], speed=80)
    dog.wait_head_done()

    # ✅ Bark if the sound is loud
    if abs(direction) > 30:
        print("🔊 Loud sound detected—PiDog is barking!")
        bark()
        time.sleep(0.5)

    # ✅ Turn toward sound direction using `action.py`
    turn_direction = "right" if direction > 0 else "left"
    globals().get(
        f"turn_{turn_direction}_medium", lambda: None
    )()  # ✅ Dynamic function call (safe)
    rgb.set_color((255, 255, 255))  # ✅ Reset LED after reaction


def start_behavior():
    """PiDog cycles through idle behaviors dynamically."""
    print("🐶 PiDog is entering idle mode...")
    threading.Thread(
        target=listen_for_sound, daemon=True
    ).start()  # ✅ Start sound listener

    while not exit_flag:
        action = random.choice(idle_actions)
        action()  # ✅ Execute behavior dynamically
        time.sleep(random.randint(3, 6))

    print("🔴 Exiting Idle Mode...")
    rgb.set_color((255, 255, 255))
    dog.close()


# ✅ Allow execution via `master.py`
if __name__ == "__main__":
    start_behavior()
