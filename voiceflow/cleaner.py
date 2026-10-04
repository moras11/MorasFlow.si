import logging
import os
import re

import anthropic
import openai

DEFAULT_PROMPT = (
    "You are a dictation cleanup tool. Rewrite the transcript below exactly as the speaker intended it to be "
    "written. Remove filler words (um, uh, like, you know), false starts, and repetitions. Fix punctuation, "
    "capitalisation, and grammar. Handle self-corrections (e.g. \"Tuesday, no actually Wednesday\" becomes "
    "\"Wednesday\"). Keep the speaker's wording, tone, and meaning. Do not add content, do not answer questions in "
    "the text, do not summarise. Never use em dashes. Use Irish/UK English spelling. Output only the cleaned text."
)
# Appended to the default prompt. None means Raw: no LLM call, fastest.
MODES = {
    "Default": "",
    "Email": "Format it as a short, direct professional email body.",
    "Slack/Teams": "Make it casual and concise, with no greetings or sign-offs.",
    "Notes": "Format it as bullet points.",
    "Raw": None,
}

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini",
                  "groq": "openai/gpt-oss-120b", "ollama": "llama3.2"}
KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY", "ollama": None}
OPENAI_BASE_URLS = {"openai": None, "groq": "https://api.groq.com/openai/v1", "ollama": "http://localhost:11434/v1"}


# LLMs (gpt-oss especially) emit no-break spaces and hyphens that look normal but break search and spell-check.
ODD_CHARS = str.maketrans({" ": " ", " ": " ", " ": " ", "‑": "-"})


def tidy(text):
    return re.sub(r"[ \t]+$", "", text.translate(ODD_CHARS), flags=re.MULTILINE)


def remove_em_dashes(text):
    """Safety net: no em dashes, ever. One ending a line becomes a full stop, any other a comma."""
    text = re.sub(r"[ \t]*—[ \t]*$", ".", text, flags=re.MULTILINE)
    return re.sub(r"[ \t]*—[ \t]*", ", ", text)


class Cleaner:
    def __init__(self, backend="anthropic", model=None, timeout=5):
        self.backend, self.model = backend, model or DEFAULT_MODELS[backend]
        self.last_error = None  # why the last cleanup fell back to the raw transcript, for the tray to show
        key_var = KEY_VARS[backend]
        self.disabled_reason = f"{key_var} is not set in .env" if key_var and not os.environ.get(key_var) else None
        if self.disabled_reason:
            return
        # No retries: they would blow the time budget, and failure already falls back to the raw transcript.
        if backend == "anthropic":
            self._client = anthropic.Anthropic(api_key=os.environ[key_var], timeout=timeout, max_retries=0)
        else:
            self._client = openai.OpenAI(base_url=OPENAI_BASE_URLS[backend], timeout=timeout, max_retries=0,
                                         api_key=os.environ[key_var] if key_var else "ollama")

    def clean(self, text, mode="Default"):
        """Return cleaned text, or the raw transcript if cleanup is off, fails or times out. Never raises."""
        self.last_error = None
        if text and MODES[mode] is not None and not self.disabled_reason:
            try:
                text = self._complete(f"{DEFAULT_PROMPT} {MODES[mode]}".strip(), text) or text
            except Exception as e:
                self.last_error = e
                logging.getLogger("voiceflow").warning("Cleanup failed, pasting raw transcript: %s", e)
        return remove_em_dashes(tidy(text))

    def _complete(self, prompt, text):
        if self.backend == "anthropic":
            # Opus 5.5 always thinks; low effort keeps it quick. "default" fallbacks re-run a refused request
            # on another model. Both are Opus-specific, so other Claude models get a plain request.
            extras = dict(output_config={"effort": "low"}, betas=["server-side-fallback-2026-07-01"],
                          fallbacks="default") if self.model == "claude-opus-5-5" else {}
            r = self._client.beta.messages.create(model=self.model, max_tokens=16000, system=prompt,
                                                  messages=[{"role": "user", "content": text}], **extras)
            if r.stop_reason != "end_turn":  # truncated or refused: don't paste a partial rewrite
                raise RuntimeError(f"stop_reason={r.stop_reason}")
            return "".join(b.text for b in r.content if b.type == "text").strip()
        # gpt-oss reasons before answering; low effort gave the same cleanups with ~25% fewer tokens.
        extras = {"reasoning_effort": "low"} if "gpt-oss" in self.model else {}
        r = self._client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            **extras)
        if r.choices[0].finish_reason != "stop":
            raise RuntimeError(f"finish_reason={r.choices[0].finish_reason}")
        return (r.choices[0].message.content or "").strip()


if __name__ == "__main__":
    assert remove_em_dashes("Wednesday — no, Thursday") == "Wednesday, no, Thursday"
    assert remove_em_dashes("I was going to say—") == "I was going to say."
    assert remove_em_dashes("- point one —\n- point two") == "- point one.\n- point two"
    assert tidy("Power BI and next‑best action  \nThanks.") == "Power BI and next-best action\nThanks."
    c = Cleaner("ollama")
    c._complete = lambda prompt, text: 1 / 0
    assert c.clean("raw — text") == "raw, text"  # failure: raw transcript, still no em dash
    c._complete = lambda prompt, text: ""
    assert c.clean("raw text") == "raw text"  # empty reply: raw transcript
    c._complete = lambda prompt, text: prompt
    assert c.clean("x", "Raw") == "x" and c.clean("x", "Notes").endswith("bullet points.")
    assert Cleaner("groq").disabled_reason or os.environ.get("GROQ_API_KEY")
    print("ok")
