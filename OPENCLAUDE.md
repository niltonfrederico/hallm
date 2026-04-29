# Using the LiteLLM Proxy with Claude Code

This project ships a LiteLLM proxy service (see [README.md](README.md) and [litellm/config.yaml](litellm/config.yaml)) that proxies requests to Gemini, Anthropic, and GitHub Copilot models. You can point Claude Code at it so all your AI calls go through the proxy.

## Steps

### 1. Start the LiteLLM proxy

```bash
docker compose up litellm -d
```

The proxy will be available at `http://localhost:4000`.

### 2. Set your API keys in `.env`

Make sure your `.env` has the keys for the models you want to use:

```env
ANTHROPIC_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
LITELLM_MASTER_KEY=sk-hallm          # used as the proxy auth key
```

### 3. Configure Claude Code to use the proxy

Add the following to your project's `.claude/settings.json` (or your global `~/.claude/settings.json` if you want it everywhere):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_API_KEY": "sk-hallm"
  }
}
```

`ANTHROPIC_API_KEY` here is the proxy's `LITELLM_MASTER_KEY`, not your real Anthropic key — the proxy holds the real key and forwards it upstream.

### 4. Verify

```bash
curl http://localhost:4000/health
```

Or send a test message via Claude Code — you should see requests logged in the proxy container:

```bash
docker compose logs -f litellm
```

## Model aliases

The proxy config maps Claude Code's full model IDs to the named entries in [litellm/config.yaml](litellm/config.yaml):

| Claude Code model ID | Proxy model name | Upstream |
| --- | --- | --- |
| `claude-sonnet-4-6` | `claude-sonnet` | `anthropic/claude-sonnet-4-6` |
| `claude-opus-4-7` | `claude-opus` | `anthropic/claude-opus-4-7` |
| `claude-haiku-4-5-20251001` | `claude-haiku` | `anthropic/claude-haiku-4-5-20251001` |
| *(any)* | `gemini-flash` | `gemini/gemini-2.5-flash` (default) |

To add more models or aliases, edit [litellm/config.yaml](litellm/config.yaml) and restart the service.
