"""Platform capture: mic, screen frames, cursor/click/app events, hotkey.

Heavy platform imports (sounddevice, mss, pynput, AppKit) happen lazily inside
start()/run() so the compiler stays importable on headless machines.
"""
