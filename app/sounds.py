"""Little sound effects they can drop onto a video.

Synthesised, not sampled. That is a deliberate choice and not a shortcut: a
folder of WAV files would be a licensing question, a download, and 40MB in the
image, where twelve lines of numpy is none of those and sounds exactly the same
every time. They are cached after the first render, so the cost is paid once
per effect per container life.

Everything is stereo float32 at gallery.VOICE_RATE, which is the shape the
voice mixer already speaks, so adding a sound and adding their voice are the
same operation with a different source.
"""

import io
import logging
import math
import wave

log = logging.getLogger("makery.sounds")

RATE = 48000
# Every effect is levelled to this RMS - see the note at the end of _build.
TARGET_RMS = 0.15

# (id, what they see, emoji). Order is the order they appear on the sheet, so
# the ones a child reaches for first go first.
CATALOGUE = [
    ("boing", "Boing", "🤸"),
    ("pop", "Pop", "🫧"),
    ("ding", "Ding!", "🔔"),
    ("sparkle", "Sparkle", "✨"),
    ("whoosh", "Whoosh", "💨"),
    ("splash", "Splash", "💦"),
    ("drum", "Drum", "🥁"),
    ("zap", "Zap", "⚡"),
    ("honk", "Honk", "📯"),
    ("fanfare", "Ta-daa!", "🎺"),
    ("cheer", "Cheering", "🎉"),
    ("thud", "Thud", "📦"),
]

IDS = [e[0] for e in CATALOGUE]


def catalogue() -> list[dict]:
    # Labels translated on the way out, like every other list of choices - see
    # styles.options. The ids are what the synthesiser is keyed on, and they
    # never move.
    from . import i18n

    return [{"id": i, "label": i18n.label("sound", i, label), "emoji": emoji}
            for i, label, emoji in CATALOGUE]


# --- the little synthesiser -------------------------------------------------


def _np():
    import numpy as np

    return np


def _t(seconds: float):
    np = _np()
    return np.linspace(0, seconds, int(RATE * seconds), endpoint=False, dtype="float32")


def _lowpass(signal, cutoff_hz):
    """One-pole lowpass. `cutoff_hz` may be an array, for a sweeping filter.

    Written as a plain loop because there is no scipy here and the arrays are
    at most a couple of seconds long. It runs once per effect, ever.
    """
    np = _np()
    n = signal.shape[0]
    cutoff = np.broadcast_to(np.asarray(cutoff_hz, dtype="float32"), (n,))
    alpha = 1.0 - np.exp(-2.0 * math.pi * np.clip(cutoff, 20.0, RATE / 2.2) / RATE)
    out = np.empty(n, dtype="float32")
    last = 0.0
    for i in range(n):
        last += float(alpha[i]) * (float(signal[i]) - last)
        out[i] = last
    return out


def _noise(seconds: float, seed: int = 7):
    np = _np()
    return np.random.default_rng(seed).standard_normal(
        int(RATE * seconds)
    ).astype("float32")


def _sine(freq, seconds: float):
    """A sine whose frequency may be an array, integrated so the pitch glides
    rather than jumping - a phase-stepped sweep clicks."""
    np = _np()
    t = _t(seconds)
    freq = np.broadcast_to(np.asarray(freq, dtype="float32"), t.shape)
    phase = np.cumsum(2.0 * math.pi * freq / RATE)
    return np.sin(phase).astype("float32")


def _decay(seconds: float, rate: float):
    np = _np()
    return np.exp(-rate * _t(seconds)).astype("float32")


def _saw(freq, seconds: float, harmonics: int = 8):
    np = _np()
    out = np.zeros(int(RATE * seconds), dtype="float32")
    for h in range(1, harmonics + 1):
        out += _sine(np.asarray(freq, dtype="float32") * h, seconds) / h
    return out


def _at(target, piece, start_seconds: float):
    """Drop `piece` into `target` at a time, growing nothing and clipping the
    tail if it would run off the end."""
    start = int(start_seconds * RATE)
    room = target.shape[0] - start
    if room <= 0:
        return target
    take = min(room, piece.shape[0])
    target[start:start + take] += piece[:take]
    return target


def _build(effect_id: str):
    np = _np()

    if effect_id == "boing":
        # A falling pitch with a wobble on it, which is the whole character of
        # the sound - a plain glide down reads as "sad", not "boing".
        t = _t(0.7)
        freq = 60.0 + 300.0 * np.exp(-5.0 * t) * (1.0 + 0.35 * np.sin(2 * math.pi * 13 * t))
        mono = _sine(freq, 0.7) * _decay(0.7, 4.5) * 0.8

    elif effect_id == "pop":
        t = _t(0.18)
        freq = 200.0 + 900.0 * np.exp(-35.0 * t)
        mono = _sine(freq, 0.18) * _decay(0.18, 28.0)
        mono += _noise(0.18, 3) * _decay(0.18, 90.0) * 0.35

    elif effect_id == "ding":
        mono = (
            _sine(880.0, 1.4) * _decay(1.4, 3.2)
            + _sine(2376.0, 1.4) * _decay(1.4, 5.5) * 0.45
            + _sine(5280.0, 1.4) * _decay(1.4, 9.0) * 0.15
        ) * 0.6

    elif effect_id == "sparkle":
        mono = np.zeros(int(RATE * 1.1), dtype="float32")
        for i, note in enumerate([1318, 1568, 1975, 2637, 3136]):
            ping = _sine(float(note), 0.45) * _decay(0.45, 11.0) * 0.34
            mono = _at(mono, ping, 0.06 * i)

    elif effect_id == "whoosh":
        t = _t(0.8)
        # The filter opens and closes again, which is what makes it pass by
        # rather than simply arrive.
        cutoff = 400.0 + 4200.0 * np.sin(math.pi * (t / 0.8)) ** 2
        mono = _lowpass(_noise(0.8, 11), cutoff)
        mono *= (np.sin(math.pi * (t / 0.8)) ** 1.5).astype("float32") * 1.6

    elif effect_id == "splash":
        t = _t(0.9)
        cutoff = 6000.0 * np.exp(-4.0 * t) + 300.0
        mono = _lowpass(_noise(0.9, 5), cutoff) * _decay(0.9, 5.0) * 1.5
        mono += _sine(180.0 + 500.0 * np.exp(-18.0 * t), 0.9) * _decay(0.9, 16.0) * 0.25

    elif effect_id == "drum":
        t = _t(0.45)
        freq = 50.0 + 130.0 * np.exp(-22.0 * t)
        mono = _sine(freq, 0.45) * _decay(0.45, 9.0)
        mono += _noise(0.45, 13) * _decay(0.45, 120.0) * 0.25

    elif effect_id == "zap":
        t = _t(0.4)
        freq = 90.0 + 1500.0 * np.exp(-12.0 * t)
        mono = _saw(freq, 0.4, 6) * _decay(0.4, 8.0) * 0.5
        mono += _noise(0.4, 17) * _decay(0.4, 25.0) * 0.2

    elif effect_id == "honk":
        mono = np.zeros(int(RATE * 0.75), dtype="float32")
        for start, note in ((0.0, 392.0), (0.3, 311.0)):
            body = _saw(note, 0.32, 5) * 0.35
            # A flat note starts and stops with a click; ease both ends.
            edge = np.minimum(1.0, np.minimum(_t(0.32), 0.32 - _t(0.32)) * 60.0)
            mono = _at(mono, (body * edge).astype("float32"), start)

    elif effect_id == "fanfare":
        mono = np.zeros(int(RATE * 1.5), dtype="float32")
        for i, note in enumerate([523.25, 659.25, 783.99]):
            length = 0.5 if i < 2 else 0.9
            body = (
                _sine(note, length) + 0.45 * _sine(note * 2, length)
                + 0.22 * _sine(note * 3, length)
            ) * _decay(length, 3.0) * 0.32
            edge = np.minimum(1.0, _t(length) * 90.0).astype("float32")
            mono = _at(mono, (body * edge).astype("float32"), 0.22 * i)

    elif effect_id == "cheer":
        t = _t(1.8)
        # A crowd is broadband noise with a slow swell and a lot of small
        # random movement on top. It will not fool anyone up close, but at the
        # back of a video it reads as people.
        wobble = 1.0 + 0.3 * np.sin(2 * math.pi * 3.1 * t) + 0.2 * np.sin(2 * math.pi * 7.3 * t)
        swell = np.sin(math.pi * (t / 1.8)) ** 1.2
        mono = _lowpass(_noise(1.8, 23), 2600.0) * wobble * swell * 2.2

    elif effect_id == "thud":
        t = _t(0.5)
        freq = 40.0 + 90.0 * np.exp(-30.0 * t)
        mono = _sine(freq, 0.5) * _decay(0.5, 11.0)
        mono += _lowpass(_noise(0.5, 29), 900.0) * _decay(0.5, 40.0) * 0.5

    else:
        raise KeyError(effect_id)

    # Every effect leaves at roughly the same *loudness*, so they are not
    # choosing between one that is inaudible and one that blows the speakers.
    # Matched on RMS rather than peak: a sustained honk and a short drum hit
    # can share a peak and be nothing like as loud as each other.
    rms = float(np.sqrt((mono.astype("float64") ** 2).mean())) or 1.0
    peak = float(np.abs(mono).max()) or 1.0
    gain = min(TARGET_RMS / rms, 0.92 / peak)
    return np.stack([(mono * gain).astype("float32")] * 2)


_cache: dict = {}


def render(effect_id: str):
    """Stereo float32, shape (2, n), at RATE. Raises KeyError for an unknown id."""
    if effect_id not in _cache:
        if effect_id not in IDS:
            raise KeyError(effect_id)
        _cache[effect_id] = _build(effect_id)
    return _cache[effect_id]


def seconds(effect_id: str) -> float:
    return render(effect_id).shape[1] / RATE


def wav_bytes(effect_id: str) -> bytes:
    """A 16-bit WAV, for the preview button on the sheet."""
    import numpy as np

    pcm = render(effect_id)
    interleaved = np.clip(pcm.T.reshape(-1), -1.0, 1.0)
    raw = (interleaved * 32767.0).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(raw)
    return out.getvalue()
