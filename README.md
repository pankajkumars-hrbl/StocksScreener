# Deploying Equity Radar Pro to Streamlit Cloud

Steps to deploy:

1. Commit this repository to a GitHub repository.
2. On Streamlit Cloud (https://share.streamlit.io) sign in with GitHub and create a new app.
3. Select the repository and the branch that contains `stocksScreen.py` and set the main file path to `stocksScreen.py`.
4. Streamlit Cloud will install dependencies from `requirements.txt` and run the app.

Notes and caveats:
- `stocksScreen.py` optionally uses a local Ollama LLM via `langchain_community.llms.Ollama`. Streamlit Cloud cannot access a local Ollama daemon running on your machine. If you rely on the LLM features, either host Ollama on a reachable endpoint or disable the local LLM code paths before deploying.
- To run locally before pushing, create a virtual environment and install dependencies:

Hosted LLM (OpenAI) support:
- The app can use a hosted LLM (OpenAI) if you set the `OPENAI_API_KEY` secret in Streamlit Cloud. When present, the app prefers the hosted LLM over a local Ollama instance.
- To add the secret in Streamlit Cloud, go to your app → Settings → Secrets and set `OPENAI_API_KEY`.

To run locally before pushing, create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run stocksScreen.py
```

Environment variables / secrets:
- If you replace the local Ollama usage with a hosted LLM (OpenAI, Anthropic, etc.), configure the provider API key in Streamlit Cloud's Secrets or environment variables.

If you want, I can:
- Add a `Dockerfile` for container-based deploys (Render/VPS).
- Modify `stocksScreen.py` to disable Ollama by default and fall back to a hosted LLM.