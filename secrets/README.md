# LLM API keys

`llmpipe` reads one raw API key from a plain-text file. You need only the file
for the provider you intend to use:

| Provider | Key file |
|---|---|
| Gemini (the default) | `gemini_secrets.txt` |
| OpenAI | `gpt_secrets.txt` |
| Anthropic | `claude_secrets.txt` |
| DeepSeek | `deepseek_secrets.txt` |

The file must contain the raw key only: no JSON, variable name, or quotation
marks. These filenames are ignored by Git.

Create and edit the file without placing the key directly in a shell command,
where it may remain in shell history. For example:

```bash
install -m 600 /dev/null secrets/gemini_secrets.txt
${EDITOR:-nano} secrets/gemini_secrets.txt
```

If the file already exists, restrict its permissions with:

```bash
chmod 600 secrets/gemini_secrets.txt
```

Name the same provider when running the solver:

```bash
cd llmpipe
python3 solver/solve.py -llm gemini \
  "Elephants are animals. John is an elephant. Is John an animal?"
```

`python3 smoketest.py`, run from the repository root, reports which provider
key files are non-empty. It does not send a model request.
