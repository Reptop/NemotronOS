from __future__ import annotations


def extract_wake_command(transcript: str, wake_words: tuple[str, ...]) -> str | None:
    normalized_transcript = transcript.strip()
    span = find_wake_word_span(normalized_transcript, wake_words)
    if span is None:
        return None

    _, end = span
    command = normalized_transcript[end:].lstrip(" \t\n\r,.:;-")
    if command:
        return command

    return None


def has_wake_word(transcript: str, wake_words: tuple[str, ...]) -> bool:
    return find_wake_word_span(transcript, wake_words) is not None


def find_wake_word_span(
    transcript: str,
    wake_words: tuple[str, ...],
) -> tuple[int, int] | None:
    normalized_transcript = transcript.strip()
    lowered_transcript = normalized_transcript.lower()

    for wake_word in wake_words:
        start = 0
        while True:
            index = lowered_transcript.find(wake_word, start)
            if index < 0:
                break

            before = lowered_transcript[index - 1] if index > 0 else " "
            after_index = index + len(wake_word)
            after = lowered_transcript[after_index] if after_index < len(lowered_transcript) else " "
            if not before.isalnum() and not after.isalnum():
                return index, after_index

            start = after_index

    return None
