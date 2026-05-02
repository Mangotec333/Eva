from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Sequence


class MacOSSaySpeakerError(RuntimeError):
    """Raised when the macOS `say` speaker cannot be used or invoked."""


class MacOSSaySpeaker:
    """Speak through the macOS built-in `say` command.

    The speaker is intentionally strict: it raises `MacOSSaySpeakerError` if
    the host is not macOS or if the `say` executable cannot be found, unless
    `fallback_to_print` is set. The console fallback is opt-in so silent
    drops never happen by accident.
    """

    name = "macos-say"

    def __init__(
        self,
        voice: str | None = None,
        rate: int | None = None,
        *,
        say_path: str | None = None,
        fallback_to_print: bool = False,
        platform: str | None = None,
        runner: callable | None = None,
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.fallback_to_print = fallback_to_print
        self._platform = platform if platform is not None else sys.platform
        self._runner = runner or subprocess.run
        self._say_path = self._resolve_say_path(say_path)

    def _resolve_say_path(self, say_path: str | None) -> str | None:
        if say_path:
            return say_path
        if self._platform != "darwin":
            return None
        return shutil.which("say") or "/usr/bin/say"

    def _ensure_available(self) -> str:
        if self._platform != "darwin":
            raise MacOSSaySpeakerError(
                f"macOS `say` is only available on darwin (current platform: {self._platform})."
            )
        if not self._say_path:
            raise MacOSSaySpeakerError(
                "Could not locate the `say` executable on this system."
            )
        return self._say_path

    def build_command(self, text: str) -> list[str]:
        say_path = self._say_path or "say"
        cmd: list[str] = [say_path]
        if self.voice:
            cmd += ["-v", self.voice]
        if self.rate is not None:
            cmd += ["-r", str(self.rate)]
        cmd += ["--", text]
        return cmd

    def speak(self, text: str) -> None:
        try:
            self._ensure_available()
        except MacOSSaySpeakerError:
            if self.fallback_to_print:
                print(f"EVA: {text}")
                return
            raise

        cmd: Sequence[str] = self.build_command(text)
        try:
            self._runner(list(cmd), check=True)
        except FileNotFoundError as exc:
            if self.fallback_to_print:
                print(f"EVA: {text}")
                return
            raise MacOSSaySpeakerError(
                f"`say` executable not found at {self._say_path}: {exc}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise MacOSSaySpeakerError(
                f"`say` exited with status {exc.returncode}"
            ) from exc
