#!/usr/bin/env python3
"""
Simple test script to check if pynput can capture events.
Run this with your venv activated to diagnose issues.
"""

import sys

print("Testing pynput installation...")
print("=" * 50)

try:
    from pynput import mouse, keyboard
    print("[OK] pynput imported successfully")
except ImportError as e:
    print(f"[FAIL] Could not import pynput: {e}")
    print("\nMake sure you've activated your virtual environment:")
    print("  source venv/bin/activate")
    sys.exit(1)

print("\nStarting mouse and keyboard listeners...")
print("Move your mouse or press a key to test.")
print("Press Ctrl+C to stop.\n")

event_count = 0

def on_move(x, y):
    global event_count
    event_count += 1
    print(f"Mouse moved to ({x}, {y}) - Total events: {event_count}", end='\r')

def on_click(x, y, button, pressed):
    global event_count
    event_count += 1
    action = "pressed" if pressed else "released"
    print(f"\nMouse {button} {action} at ({x}, {y}) - Total events: {event_count}")

def on_scroll(x, y, dx, dy):
    global event_count
    event_count += 1
    print(f"\nScrolled at ({x}, {y}) delta: ({dx}, {dy}) - Total events: {event_count}")

def on_press(key):
    global event_count
    event_count += 1
    try:
        print(f"\nKey {key.char} pressed - Total events: {event_count}")
    except AttributeError:
        print(f"\nSpecial key {key} pressed - Total events: {event_count}")

def on_release(key):
    if key == keyboard.Key.esc:
        # Stop listener
        return False

# Start listeners
mouse_listener = mouse.Listener(
    on_move=on_move,
    on_click=on_click,
    on_scroll=on_scroll
)

keyboard_listener = keyboard.Listener(
    on_press=on_press,
    on_release=on_release
)

try:
    mouse_listener.start()
    keyboard_listener.start()

    print("Listeners started successfully!")
    print("If you don't see any events when you move/click/type,")
    print("there may be a permissions issue on your system.\n")

    # Wait for keyboard listener to stop (ESC key)
    keyboard_listener.join()

    print(f"\n\nTest complete! Total events captured: {event_count}")

    if event_count == 0:
        print("\n[WARNING] No events were captured!")
        print("\nPossible issues:")
        print("1. On Linux, you may need to run with sudo (not recommended)")
        print("2. Or add your user to the 'input' group:")
        print("   sudo usermod -a -G input $USER")
        print("   (then log out and back in)")
        print("3. On Wayland, pynput may have limited support")
        print("   Try switching to X11 or using X11 compatibility mode")
    else:
        print("[OK] pynput is working correctly!")

except KeyboardInterrupt:
    print(f"\n\nInterrupted! Total events captured: {event_count}")
    mouse_listener.stop()
    keyboard_listener.stop()
