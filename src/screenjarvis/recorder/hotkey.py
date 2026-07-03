"""Hold-to-record: a global key listener; recording lasts while the key is held."""

from __future__ import annotations


def parse_key(name: str):
    from pynput import keyboard

    name = name.strip()
    try:
        return keyboard.Key[name]
    except KeyError:
        if len(name) == 1:
            return keyboard.KeyCode.from_char(name)
        raise SystemExit(
            f"Unknown key name: {name!r}. Use e.g. alt_r, cmd_r, f8, or a single character."
        )


class HoldListener:
    def __init__(self, key_name: str, on_press, on_release):
        self._key_name = key_name
        self._on_press = on_press
        self._on_release = on_release
        self._held = False
        self._listener = None

    def start(self) -> None:
        from pynput import keyboard

        target = parse_key(self._key_name)
        target_char = getattr(target, "char", None)

        def matches(key) -> bool:
            if key == target:
                return True
            return target_char is not None and getattr(key, "char", None) == target_char

        def pressed(key):
            if matches(key) and not self._held:  # ignore key auto-repeat
                self._held = True
                self._on_press()

        def released(key):
            if matches(key) and self._held:
                self._held = False
                self._on_release()

        self._listener = keyboard.Listener(on_press=pressed, on_release=released)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
