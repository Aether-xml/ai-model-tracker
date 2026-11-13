#!/usr/bin/env python3
"""
AI Model & Leak Tracker v3.0
OpenRouter (all modalities) + Vercel AI Gateway + Models.dev + LiteLLM +
NVIDIA Catalog + HuggingFace + GitHub Commit/PR Diff + Path-Targeted Cloud SDKs +
GitHub Org New Repos + Vertex/OpenAI/DeepMind/Anthropic News + NPM CLIs
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

STATE_FILE = os.environ.get("STATE_FILE", "state.json")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

HEADERS_BASE = {"User-Agent": "AI-Model-Leak-Tracker/3.0"}

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

# Dev monorepolarda sadece AI/SDK yollarini izleyen keskin nisanci listesi: (repo, path)
GITHUB_PATH_TARGETS = [
    ("Azure/azure-rest-api-specs", "specification/ai"),
    ("Azure/azure-sdk-for-python", "sdk/ai"),
    ("openai/openai-openapi", "openapi.yaml"),
    ("openai/tiktoken", ""),
    ("boto/botocore", "botocore/data/bedrock-runtime"),
    ("aws/aws-sdk-js-v3", "clients/client-bedrock-runtime"),
    ("pydantic/genai-prices", "prices/providers"),
    ("pydantic/pydantic-ai", "pydantic_ai_slim/pydantic_ai/models"),
    ("GoogleCloudPlatform/generative-ai", ""),
    ("earendil-works/pi", "packages/ai/src/models.generated.ts"),
    ("asgeirtj/system_prompts_leaks", "README.md"),
]

NPM_PACKAGES = [
    "@anthropic-ai/claude-code",
    "@openai/codex",
    "@google/gemini-cli",
    "@earendil-works/pi-ai",
]

XML_FEEDS = [
    ("Vertex AI", "https://cloud.google.com/feeds/vertex-ai-release-notes.xml"),
    ("Vertex GenAI", "https://cloud.google.com/feeds/generative-ai-on-vertex-ai-release-notes.xml"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
]

MODEL_REGEX = re.compile(
    r"""(?i)\b(
        gpt-(?:[5-9]|image|oss|audio|realtime)[a-z0-9._-]* |
        o[3-9](?:-[a-z0-9._-]+)? |
        claude-(?:opus|sonnet|haiku|mythos|fable|[456])[a-z0-9._-]* |
        gemini-[3-9][a-z0-9._-]* |
        deepseek-(?:v[4-9]|r[2-9])[a-z0-9._-]* |
        qwen-?(?:3\.[5-9]|3[5-9]|[4-9]|4exp|image|omni)[a-z0-9._-]* |
        llama-?[4-9][a-z0-9._-]* |
        glm-?[5-9][a-z0-9._-]* |
        grok-?[3-9][a-z0-9._-]* |
        kimi-k[3-9][a-z0-9._-]* |
        minimax-m[3-9][a-z0-9._-]* |
        (?:mistral|devstral|magistral|voxtral)-[a-z0-9._-]*[2-9][a-z0-9._-]*
    )\b""",
    re.VERBOSE,
)

NOISE_WORDS = ("test", "mock", "fake", "dummy", "example", "sample", "invalid", "deprecated")
EXT_STRIP_RE = re.compile(r"\.(toml|ya?ml|json|py|ts|js|md)$", re.IGNORECASE)


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
    state["seen_commits"] = state["seen_commits"][-1200:]
    state["seen_prs"] = state["seen_prs"][-800:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(text):
    print(f"[ALERT]\n{text}\n{'-' * 40}")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text[:4000],
                "disable_web_page_preview": True,
            }).encode("utf-8")
            req = urllib.request.Request(
                tg_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:
            print(f"[ERR] Telegram: {e}")


def send_grouped(header, items, footer=""):
    if not items:
        return
    if len(items) == 1:
        msg = f"{header}\n{items[0]}" + (f"\n{footer}" if footer else "")
        send_telegram(msg)
        return

    chunk = [f"{header} ({len(items)} yeni)"]
    cur_len = len(chunk[0])
    for item in items:
        if cur_len + len(item) + len(footer) + 10 > 3600:
            if footer:
                chunk.append(footer)
            send_telegram("\n\n".join(chunk))
            time.sleep(0.35)
            chunk = [f"{header} (devam)"]
            cur_len = len(chunk[0])
        chunk.append(item)
        cur_len += len(item) + 2

    if footer:
        chunk.append(footer)
    send_telegram("\n\n".join(chunk))


def clean_model_token(token):
    tok = EXT_STRIP_RE.sub("", token.strip()).strip("._-").lower()
    if len(tok) < 4 or any(w in tok for w in NOISE_WORDS):
        return None
    if tok in ("claude-4", "gemini-3", "gpt-5", "llama-4"):
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
                    found.setdefault(tok, (fname, line[1:].strip()[:110]))
    return found


def check_openrouter(state, known_set, groups):
    try:
        data = http_get_json("https://openrouter.ai/api/v1/models?output_modalities=all")
        models = data.get("data", [])
        seen = set(state.get("openrouter", []))
        current = []
        hits = []
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
                badge = "🚨 STEALTH/UCRETSIZ" if is_stealth else "🆕"
                hits.append(f"{badge} {mid}\nModalite: {mods} | Ctx: {ctx}\nhttps://openrouter.ai/{mid}")
        state["openrouter"] = sorted(set(current))
        if hits:
            groups.append(("🌐 OpenRouter Yeni Modeller", hits, ""))
    except Exception as e:
        print(f"[WARN] OpenRouter: {e}")


def check_vercel_gateway(state, known_set, groups):
    is_baseline = "vercel_gateway" not in state
    try:
        data = http_get_json("https://ai-gateway.vercel.sh/v1/models")
        models = data.get("data", [])
        seen = set(state.get("vercel_gateway", []))
        current = []
        hits = []
        for m in models:
            mid = m.get("id", "")
            if not mid:
                continue
            current.append(mid)
            known_set.add(mid.lower())
            known_set.add(mid.split("/")[-1].lower())
            if mid not in seen and state["initialized"] and not is_baseline:
                mtype = m.get("type", "language")
                name = m.get("name", mid)
                hits.append(f"• {mid} ({name} | {mtype})")
        state["vercel_gateway"] = sorted(set(current))
        if hits:
            groups.append(("▲ Vercel AI Gateway Yeni Modeller", hits, "https://vercel.com/ai-gateway/models"))
        return is_baseline
    except Exception as e:
        print(f"[WARN] Vercel Gateway: {e}")
        return False


def check_nvidia_catalog(state, known_set, groups):
    is_baseline = "nvidia_catalog" not in state
    try:
        data = http_get_json("https://assets.ngc.nvidia.com/products/api-catalog/featured-models.json")
        if isinstance(data, dict):
            raw_items = data.get("models") or data.get("data") or list(data.values())
        elif isinstance(data, list):
            raw_items = data
        else:
            raw_items = []
        seen = set(state.get("nvidia_catalog", []))
        current = []
        hits = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            mid = item.get("id") or item.get("model") or item.get("name") or ""
            if not mid:
                continue
            current.append(mid)
            known_set.add(mid.lower())
            known_set.add(mid.split("/")[-1].lower())
            if mid not in seen and state["initialized"] and not is_baseline:
                dname = item.get("name", mid)
                hits.append(f"• {mid} ({dname})")
        state["nvidia_catalog"] = sorted(set(current))
        if hits:
            groups.append(("🟢 NVIDIA API Katalog", hits, "https://build.nvidia.com"))
        return is_baseline
    except Exception as e:
        print(f"[WARN] NVIDIA Catalog: {e}")
        return False


def check_models_dev(state, known_set, groups):
    try:
        data = http_get_json("https://models.dev/api.json")
        seen = set(state.get("models_dev", []))
        current = []
        hits = []
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
                    hits.append(f"• {full_id} (Ctx: {ctx})")
        state["models_dev"] = sorted(set(current))
        if hits:
            groups.append(("🆕 Models.dev Katalog", hits, "https://models.dev"))
    except Exception as e:
        print(f"[WARN] Models.dev: {e}")


def check_litellm_json(state, known_set, groups):
    try:
        url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
        data = http_get_json(url)
        seen = set(state.get("litellm", []))
        current = []
        hits = []
        for k, info in data.items():
            if k == "sample_spec":
                continue
            current.append(k)
            known_set.add(k.lower())
            known_set.add(k.split("/")[-1].lower())
            if k not in seen and state["initialized"]:
                prov = info.get("litellm_provider", "?") if isinstance(info, dict) else "?"
                max_tok = (info.get("max_input_tokens") or info.get("max_tokens", "?")) if isinstance(info, dict) else "?"
                hits.append(f"• {k} ({prov} | max: {max_tok})")
        state["litellm"] = sorted(set(current))
        if hits:
            groups.append((
                "💎 LiteLLM Maliyet Tablosu",
                hits,
                "https://github.com/BerriAI/litellm/commits/main/model_prices_and_context_window.json",
            ))
    except Exception as e:
        print(f"[WARN] LiteLLM: {e}")


def check_huggingface(state, groups):
    seen = set(state.get("hf_models", []))
    current = set(seen)
    hits = []
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
                    hits.append(f"• {mid} ({task})\nhttps://huggingface.co/{mid}")
            time.sleep(0.12)
        except Exception as e:
            print(f"[WARN] HF {org}: {e}")
    state["hf_models"] = sorted(current)
    if hits:
        groups.append(("🤗 Hugging Face Yeni Modeller", hits, ""))


def check_npm_packages(state, groups):
    is_baseline = "npm_versions" not in state
    seen = dict(state.get("npm_versions", {}))
    hits = []
    for pkg in NPM_PACKAGES:
        try:
            encoded = urllib.parse.quote(pkg, safe="@")
            data = http_get_json(f"https://registry.npmjs.org/{encoded}/latest")
            ver = data.get("version", "")
            if not ver:
                continue
            prev = seen.get(pkg)
            seen[pkg] = ver
            if prev and ver != prev and state["initialized"] and not is_baseline:
                hits.append(f"• {pkg}: {prev} → {ver}\nhttps://www.npmjs.com/package/{pkg}")
        except Exception as e:
            print(f"[WARN] NPM {pkg}: {e}")
    state["npm_versions"] = seen
    if hits:
        groups.append(("📦 Yeni CLI / NPM Surumu", hits, ""))
    return is_baseline


def check_official_news(state, groups):
    is_baseline = "official_news" not in state
    seen = set(state.get("official_news", []))
    current = set(seen)
    hits = []

    for label, feed_url in XML_FEEDS:
        try:
            xml_str = http_get(feed_url)
            root = ET.fromstring(xml_str)
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//item")
            for entry in entries[:6]:
                title = (
                    entry.findtext("{http://www.w3.org/2005/Atom}title")
                    or entry.findtext("title")
                    or ""
                ).strip()
                link = entry.findtext("link") or ""
                if not link:
                    link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                    if link_el is not None:
                        link = link_el.attrib.get("href", "")
                key = link or f"{label}:{title}"
                if not key:
                    continue
                current.add(key)
                if key not in seen and state["initialized"] and not is_baseline:
                    hits.append(f"• [{label}] {title or 'Yeni guncelleme'}\n{link}")
        except Exception as e:
            print(f"[WARN] Feed {label}: {e}")

    try:
        sm_xml = http_get("https://www.anthropic.com/sitemap.xml")
        root = ET.fromstring(sm_xml)
        for loc_el in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            loc = (loc_el.text or "").strip()
            if any(seg in loc for seg in ("/news/", "/research/", "/engineering/")):
                current.add(loc)
                if loc not in seen and state["initialized"] and not is_baseline:
                    slug = loc.rstrip("/").split("/")[-1].replace("-", " ").title()
                    hits.append(f"• [Anthropic] {slug}\n{loc}")
    except Exception as e:
        print(f"[WARN] Anthropic Sitemap: {e}")

    state["official_news"] = sorted(current)[-1500:]
    if hits:
        groups.append(("📰 Resmi Lab Duyurulari & Vertex AI", hits, ""))
    return is_baseline


def check_github(state, known_set, groups):
    if not GITHUB_TOKEN:
        return False, False
    gh_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
    }
    seen_commits = set(state.get("seen_commits", []))
    seen_prs = set(state.get("seen_prs", []))

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
                    groups.append((
                        f"🕵️ GitHub Gizli Satir: {repo}",
                        [f"Commit: {msg}\n{lines_txt}"],
                        html_url,
                    ))
            time.sleep(0.08)
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
                    details = [f"Baslik: {title}"]
                    if text_hits:
                        details.append("Metin: " + ", ".join(dict.fromkeys(text_hits))[:120])
                    for tok, (fn, ln) in list(file_found.items())[:4]:
                        details.append(f"• {tok} ({fn}): {ln}")
                    if len(details) == 1 and has_kw:
                        details.append("Anahtar kelime eslesmesi")
                    groups.append((
                        f"👀 Acik PR Sinyali: {pr_id}",
                        ["\n".join(details)],
                        pr.get("html_url", ""),
                    ))
            time.sleep(0.08)
        except Exception as e:
            print(f"[WARN] GH PRs {repo}: {e}")

    is_path_baseline = "seen_path_commits" not in state
    seen_path_commits = set(state.get("seen_path_commits", []))
    path_hits = []

    for repo, subpath in GITHUB_PATH_TARGETS:
        try:
            q = f"?per_page=5" + (f"&path={urllib.parse.quote(subpath)}" if subpath else "")
            commits = http_get_json(f"https://api.github.com/repos/{repo}/commits{q}", gh_headers)
            for c in commits:
                sha = c.get("sha", "")
                if not sha or sha in seen_path_commits:
                    continue
                state.setdefault("seen_path_commits", []).append(sha)
                seen_path_commits.add(sha)
                if not state["initialized"] or is_path_baseline:
                    continue

                detail = http_get_json(f"https://api.github.com/repos/{repo}/commits/{sha}", gh_headers)
                msg = detail.get("commit", {}).get("message", "").splitlines()[0]
                html_url = detail.get("html_url", "")

                msg_hits = []
                for raw_tok in MODEL_REGEX.findall(msg):
                    tok = clean_model_token(raw_tok)
                    if tok and tok not in known_set:
                        msg_hits.append(tok)
                file_found = extract_new_models_from_files(detail.get("files", []), known_set)

                for tok in msg_hits:
                    known_set.add(tok)
                for tok in file_found:
                    known_set.add(tok)

                is_prompt_leak_repo = "system_prompts_leaks" in repo
                if msg_hits or file_found or is_prompt_leak_repo:
                    tag = f"{repo}" + (f" ({subpath})" if subpath else "")
                    lines = [f"• {tag}: {msg}"]
                    if msg_hits:
                        lines.append("  Modeller: " + ", ".join(dict.fromkeys(msg_hits))[:100])
                    for tok, (fn, ln) in list(file_found.items())[:3]:
                        lines.append(f"  + {tok} ({fn}): {ln}")
                    lines.append(html_url)
                    path_hits.append("\n".join(lines))
            time.sleep(0.08)
        except Exception as e:
            print(f"[WARN] Path {repo}: {e}")

    state["seen_path_commits"] = state.get("seen_path_commits", [])[-800:]
    if path_hits:
        groups.append(("🎯 Bulut SDK & Prompt Sizinti Radari", path_hits, ""))

    is_org_baseline = "seen_org_repos" not in state
    seen_org_repos = set(state.get("seen_org_repos", []))
    current_org_repos = set(seen_org_repos)
    org_hits = []

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
                    desc = (r.get("description") or "Aciklama yok")[:160]
                    url = r.get("html_url", f"https://github.com/{full_name}")
                    org_hits.append(f"• {full_name}\n{desc}\n{url}")
            time.sleep(0.08)
        except Exception as e:
            print(f"[WARN] GH org {org}: {e}")

    state["seen_org_repos"] = sorted(current_org_repos)
    if org_hits:
        groups.append(("🏛️ Yeni Lab GitHub Reposu", org_hits, ""))

    return is_path_baseline, is_org_baseline


def main():
    state = load_state()
    known_set = set(state.get("known_model_strings", []))
    groups = []

    check_openrouter(state, known_set, groups)
    b_vercel = check_vercel_gateway(state, known_set, groups)
    b_nvidia = check_nvidia_catalog(state, known_set, groups)
    check_models_dev(state, known_set, groups)
    check_litellm_json(state, known_set, groups)
    check_huggingface(state, groups)
    b_npm = check_npm_packages(state, groups)
    b_news = check_official_news(state, groups)
    b_path, b_org = check_github(state, known_set, groups)

    state["known_model_strings"] = sorted(known_set)

    if not state["initialized"]:
        state["initialized"] = True
        save_state(state)
        send_telegram(
            f"✅ AI Model Tracker v3.0 Aktif ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})\n"
            f"• Kayitli model izi: {len(known_set)}\n"
            f"• Izlenen kaynak: OpenRouter, Vercel Gateway, NVIDIA, Models.dev, LiteLLM, "
            f"{len(HF_ORGS)} HF lab, {len(GITHUB_REPOS)} repo, {len(GITHUB_PATH_TARGETS)} SDK yolu, "
            f"{len(GITHUB_ORGS)} org, NPM & Resmi Bloglar"
        )
        return

    save_state(state)

    if any([b_vercel, b_nvidia, b_npm, b_news, b_path, b_org]):
        send_telegram(
            "🚀 Tracker v3.0 Yukseltildi!\n"
            "Yeni eklenen baz hatlar sessizce kaydedildi:\n"
            "• Vercel AI Gateway & NVIDIA API Katalog\n"
            "• Azure AI / AWS Bedrock / OpenAI OpenAPI / Tiktoken / GenAI-Prices / Pi / System Prompts Leaks\n"
            "• Vertex AI, OpenAI, DeepMind, Anthropic Sitemap & NPM CLI surum radari\n"
            "• Gruplu bildirim & eski-nesil test gurultusu filtresi aktif!"
        )

    for header, items, footer in groups:
        send_grouped(header, items, footer)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
