import hashlib
import hmac
import json
from pathlib import Path

SECRET_KEY = b"change-this-to-a-long-random-secret-key"

WORDS = [
    "amber", "breeze", "cedar", "daisy", "ember", "forest", "golden", "harbor",
    "ivory", "juniper", "kiwi", "lavender", "meadow", "nectar", "ocean", "pepper",
    "quiet", "river", "silver", "thunder", "umber", "violet", "willow", "xenon",
    "yellow", "zephyr", "autumn", "brisk", "crystal", "drift", "echo", "flame",
    "garden", "hazel", "island", "jade", "kernel", "lunar", "maple", "nova",
    "opal", "prairie", "quartz", "raven", "summit", "timber", "urban", "velvet",
    "winter", "yonder"
]

LOOKUP_FILE = Path("obfuscation_lookup.json")


def load_lookup() -> dict:
    if LOOKUP_FILE.exists():
        return json.loads(LOOKUP_FILE.read_text())
    return {}


def save_lookup(lookup: dict) -> None:
    LOOKUP_FILE.write_text(json.dumps(lookup, indent=2))


def _three_words(value: str) -> str:
    digest = hmac.new(
        SECRET_KEY,
        value.encode("utf-8"),
        hashlib.sha256
    ).digest()

    number = int.from_bytes(digest, "big")

    w1 = WORDS[number % len(WORDS)]
    w2 = WORDS[(number // len(WORDS)) % len(WORDS)]
    w3 = WORDS[(number // (len(WORDS) ** 2)) % len(WORDS)]

    return f"{w1}-{w2}-{w3}"


def obfuscate(value: str, prefix: str | None = None) -> str:
    lookup = load_lookup()

    three_word_value = _three_words(value)

    if prefix:
        obfuscated = f"{prefix}-{three_word_value}"
    else:
        obfuscated = three_word_value

    lookup[obfuscated] = value
    save_lookup(lookup)

    return obfuscated


def deobfuscate(value: str) -> str:
    lookup = load_lookup()
    return lookup[value]