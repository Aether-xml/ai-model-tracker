#!/usr/bin/env python3
"""
AI Model & Leak Tracker v2.1
OpenRouter (all modalities) + Models.dev + LiteLLM + HuggingFace +
GitHub Commit/PR Diff Patch + GitHub Org New Repo Radar
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

STATE_FILE = os.environ.get("STATE_FILE", "state.json")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

HEADERS_BASE = {"User-Agent": "AI-Model-Leak-Tracker/2.1"}

HF_ORGS = [
    "deepseek-ai",
    "Qwen",
    "zai-org",
    "moonshotai",
    "MiniMaxAI",
    "meta-llama",
    "mistralai",
    "google",
    "openai",
    "nvidia",
    "ByteDance-Seed",
    "stepfun-ai",
]

GITHUB_ORGS = [
    "deepseek-ai",
    "QwenLM",
    "zai-org",
    "MoonshotAI",
    "MiniMax-AI",
    "xai-org",
    "mistralai",
    "openai",
    "anthropics",
    "google-gemini",
    "meta-llama",
]

GITHUB_REPOS = [
    "BerriAI/litellm",
    "Kilo-Org/kilocode",
    "cline/cline",
    "RooCodeInc/Roo-Code",
    "anomalyco/opencode",
    "anomalyco/models.dev",
    "vercel/ai",
    "anthropics/claude-code",
    "anthropics/anthropic-sdk-python",
    "openai/codex",
    "openai/openai-python",
    "google-gemini/gemini-cli",
    "googleapis/python-genai",
    "ggml-org/llama.cpp",
    "vllm-project/vllm",
    "ollama/ollama",
]

MODEL_REGEX = re.compile(
    r"""(?i)\b(
        gpt-(?:[4-9]|image|oss|audio|realtime)[a-z0-9._-]* |
        o[3-9](?:-[a-z0-9._-]+)? |
        claude-(?:opus|sonnet|haiku|[3456])[a-z0-9._-]* |
        gemini-[2-9][a-z0-9._-]* |
        deepseek-(?:v[3-9]|r[1-9])[a-z0-9._-]* |
        qwen-?(?:[3-9]|image|omni|vl|coder)[a-z0-9._-]* |
        llama-?[4-9][a-z0-9._-]* |
        glm-?[4-9][a-z0-9._-]* |
        grok-?[3-9][a-z0-9._-]* |
        kimi-k[2-9][a-z0-9._-]* |
        minimax-m[2-9][a-z0-9._-]* |
        (?:mistral|devstral|magistral|voxtral)-[a-z0-9._-]*[2-9][a-z0-9._-]*
    )\b""",
    re.VERBOSE,
)

NOISE_WORDS = ("test", "mock", "fake", "dummy", "example", "sample", "invalid", "deprecated")


def http_get(url, extra_headers=None, timeout=25):
    headers = dict(HEADERS_BASE)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def http_get_json(url, extra_headers=None):
    return json.loads(http_get(url, extra_headers=extra_headers))


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "initialized": False,
        "openrouter": [],
        "models_dev": [],
        "litellm": [],
        "hf_models": [],
        "seen_commits": [],
        "seen_prs": [],
        "known_model_strings": [],
    }


def save_state(state):
    state["seen_commits"] = state["seen_commits"][-700:]
    state["seen_prs"] = state["seen_prs"][-700:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def notify(title, message, url=""):
    full_text = f"{title}\n\n{message}" + (f"\n\n{url}" if url else "")
    print(f"[ALERT] {title} -> {message} {url}")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": full_text[:4000],
                "disable_web_page_preview": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                tg_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:
            print(f"[ERR] Telegram: {e}")


def clean_model_token(token):
    tok = token.strip().strip("._-").lower()
    if len(tok) < 4 or any(w in tok for w in NOISE_WORDS):
        return None
    return tok


def extract_new_models_from_files(files_list, known_set):
    found = {}
    for f in files_list:
        patch = f.get("patch", "")
        if not patch:
            continue
        fname = f.get("filename", "")
        for line in patch.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for raw_tok in MODEL_REGEX.findall(line):
                tok = clean_model_token(raw_tok)
                if tok and tok not in known_set:
                    found.setdefault(tok, (fname, line[1:].strip()[:120]))
    return found


def check_openrouter(state, known_set, alerts):
    try:
        data = http_get_json("https://openrouter.ai/api/v1/models?output_modalities=all")
        models = data.get("data", [])
        seen = set(state["openrouter"])
        current = []
        for m in models:
            mid = m.get("id", "")
            if not mid:
                continue
            current.append(mid)
            known_set.add(mid.lower())
            known_set.add(mid.split("/")[-1].lower())
            if mid not in seen and state["initialized"]:
                ctx = m.get("context_length", "?")
                mods = ", ".join(m.get("architecture", {}).get("output_modalities", []) or ["text"])
                pricing = m.get("pricing", {}) or {}
                is_stealth = (
                    "alpha" in mid.lower()
                    or "stealth" in mid.lower()
                    or ":free" in mid.lower()
                    or (str(pricing.get("prompt", "")) == "0" and str(pricing.get("completion", "")) == "0")
                )
                tag = "🚨 STEALTH / UCRETSIZ" if is_stealth else "🆕 OpenRouter"
                alerts.append((
                    f"{tag}: {mid}",
                    f"Modalite: {mods} | Context: {ctx}",
                    f"https://openrouter.ai/{mid}",
                ))
        state["openrouter"] = sorted(set(current))
    except Exception as e:
        print(f"[WARN] OpenRouter: {e}")


def check_models_dev(state, known_set, alerts):
    try:
        data = http_get_json("https://models.dev/api.json")
        seen = set(state["models_dev"])
        current = []
        for prov_id, prov_data in data.items():
            if not isinstance(prov_data, dict):
                continue
            models = prov_data.get("models", {})
            if not isinstance(models, dict):
                continue
            for mid, minfo in models.items():
                full_id = f"{prov_id}/{mid}"
                current.append(full_id)
                known_set.add(mid.lower())
                known_set.add(full_id.lower())
                if full_id not in seen and state["initialized"]:
                    ctx = minfo.get("limit", {}).get("context", "?") if isinstance(minfo, dict) else "?"
                    alerts.append((
                        f"🆕 Models.dev: {full_id}",
                        f"Kataloga yeni model eklendi.\nContext: {ctx}",
                        "https://models.dev",
                    ))
        state["models_dev"] = sorted(set(current))
    except Exception as e:
        print(f"[WARN] Models.dev: {e}")


def check_litellm_json(state, known_set, alerts):
    try:
        url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
        data = http_get_json(url)
        seen = set(state["litellm"])
        current = []
        for k, info in data.items():
            if k == "sample_spec":
                continue
            current.append(k)
            known_set.add(k.lower())
            known_set.add(k.split("/")[-1].lower())
            if k not in seen and state["initialized"]:
                prov = info.get("litellm_provider", "?") if isinstance(info, dict) else "?"
                max_tok = (info.get("max_input_tokens") or info.get("max_tokens", "?")) if isinstance(info, dict) else "?"
                alerts.append((
                    f"💎 LiteLLM Eklemesi: {k}",
                    f"Saglayici: {prov} | Max Token: {max_tok}",
                    "https://github.com/BerriAI/litellm/commits/main/model_prices_and_context_window.json",
                ))
        state["litellm"] = sorted(set(current))
    except Exception as e:
        print(f"[WARN] LiteLLM: {e}")


def check_huggingface(state, alerts):
    seen = set(state["hf_models"])
    current = set(seen)
    for org in HF_ORGS:
        try:
            url = f"https://huggingface.co/api/models?author={org}&sort=createdAt&direction=-1&limit=5"
            items = http_get_json(url)
            for item in items:
                mid = item.get("id", "")
                if not mid:
                    continue
                current.add(mid)
                if mid not in seen and state["initialized"]:
                    task = item.get("pipeline_tag") or "belirsiz"
                    alerts.append((
                        f"🤗 HuggingFace Yeni Model: {mid}",
                        f"Lab: {org} | Gorev: {task}",
                        f"https://huggingface.co/{mid}",
                    ))
            time.sleep(0.15)
        except Exception as e:
            print(f"[WARN] HF {org}: {e}")
    state["hf_models"] = sorted(current)


def check_github(state, known_set, alerts):
    if not GITHUB_TOKEN:
        return False
    gh_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
    }
    seen_commits = set(state["seen_commits"])
    seen_prs = set(state["seen_prs"])

    for repo in GITHUB_REPOS:
        try:
            commits = http_get_json(f"https://api.github.com/repos/{repo}/commits?per_page=5", gh_headers)
            for c in commits:
                sha = c.get("sha", "")
                if not sha or sha in seen_commits:
                    continue
                state["seen_commits"].append(sha)
                seen_commits.add(sha)
                if not state["initialized"]:
                    continue

                detail = http_get_json(f"https://api.github.com/repos/{repo}/commits/{sha}", gh_headers)
                msg = detail.get("commit", {}).get("message", "").splitlines()[0]
                html_url = detail.get("html_url", "")
                found = extract_new_models_from_files(detail.get("files", []), known_set)

                if found:
                    for tok in found:
                        known_set.add(tok)
                    lines_txt = "\n".join(
                        f"• {tok} ({fn}): {ln}" for tok, (fn, ln) in list(found.items())[:5]
                    )
                    alerts.append((
                        f"🕵️ GitHub Gizli Satir / Sizinti: {repo}",
                        f"Commit: {msg}\n{lines_txt}",
                        html_url,
                    ))
            time.sleep(0.1)
        except Exception as e:
            print(f"[WARN] GH commits {repo}: {e}")

        try:
            prs = http_get_json(
                f"https://api.github.com/repos/{repo}/pulls?state=open&sort=created&direction=desc&per_page=5",
                gh_headers,
            )
            for pr in prs:
                num = pr.get("number")
                pr_id = f"{repo}#{num}"
                if pr_id in seen_prs:
                    continue
                state["seen_prs"].append(pr_id)
                seen_prs.add(pr_id)
                if not state["initialized"]:
                    continue

                title = pr.get("title", "")
                text_blob = f"{title}\n{pr.get('body') or ''}"
                text_hits = []
                for raw_tok in MODEL_REGEX.findall(text_blob):
                    tok = clean_model_token(raw_tok)
                    if tok and tok not in known_set:
                        text_hits.append(tok)

                file_found = {}
                try:
                    pr_files = http_get_json(
                        f"https://api.github.com/repos/{repo}/pulls/{num}/files?per_page=15",
                        gh_headers,
                    )
                    file_found = extract_new_models_from_files(pr_files, known_set)
                except Exception as fe:
                    print(f"[WARN] GH PR files {pr_id}: {fe}")

                for tok in text_hits:
                    known_set.add(tok)
                for tok in file_found:
                    known_set.add(tok)

                has_kw = any(k in title.lower() for k in ("stealth", "unreleased", "alpha model"))
                if text_hits or file_found or has_kw:
                    details = []
                    if text_hits:
                        details.append("Metin: " + ", ".join(dict.fromkeys(text_hits))[:120])
                    for tok, (fn, ln) in list(file_found.items())[:4]:
                        details.append(f"• {tok} ({fn}): {ln}")
                    if not details and has_kw:
                        details.append("Anahtar kelime eslesmesi")
                    alerts.append((
                        f"👀 Acik PR Sinyali: {pr_id}",
                        f"Baslik: {title}\n" + "\n".join(details),
                        pr.get("html_url", ""),
                    ))
            time.sleep(0.1)
        except Exception as e:
            print(f"[WARN] GH PRs {repo}: {e}")

    is_org_baseline = "seen_org_repos" not in state
    seen_org_repos = set(state.get("seen_org_repos", []))
    current_org_repos = set(seen_org_repos)

    for org in GITHUB_ORGS:
        try:
            repos = http_get_json(
                f"https://api.github.com/orgs/{org}/repos?type=public&sort=created&direction=desc&per_page=5",
                gh_headers,
            )
            for r in repos:
                full_name = r.get("full_name", "")
                if not full_name:
                    continue
                current_org_repos.add(full_name)
                if full_name not in seen_org_repos and state["initialized"] and not is_org_baseline:
                    desc = (r.get("description") or "Aciklama yok")[:180]
                    alerts.append((
                        f"🏛️ Yeni Lab GitHub Reposu: {full_name}",
                        f"Org: {org}\n{desc}",
                        r.get("html_url", f"https://github.com/{full_name}"),
                    ))
            time.sleep(0.1)
        except Exception as e:
            print(f"[WARN] GH org {org}: {e}")

    state["seen_org_repos"] = sorted(current_org_repos)
    return is_org_baseline


def main():
    state = load_state()
    known_set = set(state.get("known_model_strings", []))
    alerts = []

    check_openrouter(state, known_set, alerts)
    check_models_dev(state, known_set, alerts)
    check_litellm_json(state, known_set, alerts)
    check_huggingface(state, alerts)
    is_org_baseline = check_github(state, known_set, alerts)

    state["known_model_strings"] = sorted(known_set)

    if not state["initialized"]:
        state["initialized"] = True
        save_state(state)
        summary = (
            f"Takip baslatildi ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}).\n"
            f"• Kayitli model izi: {len(known_set)}\n"
            f"• Izlenen HF lab: {len(HF_ORGS)}\n"
            f"• Izlenen GH org/repo: {len(GITHUB_ORGS)} org / {len(GITHUB_REPOS)} repo"
        )
        notify("✅ AI Model Tracker Aktif", summary)
        return

    save_state(state)
    if is_org_baseline:
        notify(
            "🚀 Tracker v2.1 Guncellendi",
            f"PR kod farki (/files) ve {len(GITHUB_ORGS)} lab GitHub yeni repo radari eklendi.\n"
            f"• Kayitli model izi: {len(known_set)}\n"
            f"• Kayitli org repo baz hatti: {len(state.get('seen_org_repos', []))}",
        )

    for title, msg, url in alerts:
        notify(title, msg, url)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
