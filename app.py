import streamlit as st
from bot import add_content_item  # process_all_pending_items not needed in this UI step

import datetime
import re
import requests
import textwrap
import streamlit.components.v1 as components

COMPANY_LOGO = "https://play-lh.googleusercontent.com/rt1NjtZV8hnqPL-7nI6685Etm1nS4EpQ96ibw_EYEPOyu4vH8Kgq3oBUplUYexx1mA"

# -------------------------
# Draft helper (for live preview)
# -------------------------
def current_draft():
    return st.session_state.draft or {
        "date": "",
        "time": "",
        "platforms": "",
        "idea": "",
        "groups": "",
        "caption": "",
        "hashtags": "",
        "image_url": "",
    }


# -------------------------
# Page config
# -------------------------
st.set_page_config(page_title="Biznex Bot 🤖 – Content Scheduler", page_icon="🤖")
st.title("Biznex Bot 🤖 – Content Scheduler")

PROMPT_TEMPLATE = """\
date: 2025-12-15 (optional)
time: 16:00 (optional, 24-hour HH:MM)
platforms: FB, IG, LinkedIn
idea: 20% off for new subscribers
groups: Group 1, Group 2 (optional)
caption: optional custom caption
hashtags: #globalbiznex #marketing (optional)
image_url: https://... (optional)
"""

st.write("Type your post details like this **(or just write a simple sentence)**:")
st.code(PROMPT_TEMPLATE, language="text")


st.divider()

# -------------------------
# Session state
# -------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Tell me how you want to schedule your post."}
    ]

if "draft" not in st.session_state:
    st.session_state.draft = None

# -------------------------
# Display chat history
# -------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -------------------------
# Parsers
# -------------------------
PLATFORM_ALIASES = {
    "fb": "FB",
    "facebook": "FB",
    "ig": "IG",
    "insta": "IG",
    "instagram": "IG",
    "linkedin": "LinkedIn",
    "li": "LinkedIn",
}


def parse_simple_statement(text: str):
    """
    Extract: date, time, platforms, idea, groups, hashtags, image_url from free text.
    Rule-based (no OpenAI).
    Example: "Post 20% off for new subscribers on FB and IG tomorrow 4pm #sale"
    """
    raw = text.strip()

    data = {
        "date": "",
        "time": "",
        "platforms": "",
        "idea": "",
        "groups": "",
        "caption": "",
        "hashtags": "",
        "image_url": "",
    }

    # 1) image_url
    url_match = re.search(r"(https?://\S+)", raw)
    if url_match:
        data["image_url"] = url_match.group(1).rstrip(".,)")
        raw = raw.replace(url_match.group(1), "").strip()

    # 2) hashtags
    tags = re.findall(r"#\w+", raw)
    if tags:
        data["hashtags"] = " ".join(tags)
        raw = re.sub(r"#\w+", "", raw).strip()

    # 3) platforms
    found_platforms = []
    for token in re.findall(r"[A-Za-z]+", raw.lower()):
        if token in PLATFORM_ALIASES:
            p = PLATFORM_ALIASES[token]
            if p not in found_platforms:
                found_platforms.append(p)
    if found_platforms:
        data["platforms"] = ", ".join(found_platforms)

    # 4) date (YYYY-MM-DD / today / tomorrow)
    today = datetime.date.today()
    if re.search(r"\btomorrow\b", raw.lower()):
        data["date"] = (today + datetime.timedelta(days=1)).isoformat()
    elif re.search(r"\btoday\b", raw.lower()):
        data["date"] = today.isoformat()
    else:
        d = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
        if d:
            data["date"] = d.group(1)

    # 5) time (16:00 or 4pm/4 pm)
    t = re.search(r"\b(\d{1,2}:\d{2})\b", raw)
    if t:
        data["time"] = t.group(1)
    else:
        ap = re.search(r"\b(\d{1,2})\s*(am|pm)\b", raw.lower())
        if ap:
            hour = int(ap.group(1))
            mer = ap.group(2)
            if mer == "pm" and hour != 12:
                hour += 12
            if mer == "am" and hour == 12:
                hour = 0
            data["time"] = f"{hour:02d}:00"

    # 6) groups (simple: text after "group" or "groups")
    after = re.split(r"\bgroups?\b", raw, flags=re.IGNORECASE, maxsplit=1)
    if len(after) == 2:
        group_text = after[1].strip(" :.-")
        group_text = re.split(
            r"\b(on|at|today|tomorrow)\b", group_text, flags=re.IGNORECASE
        )[0].strip()
        if group_text:
            data["groups"] = group_text

    # 7) idea: remove obvious keywords and keep remaining text
    cleaned = raw
    cleaned = re.sub(
        r"\b(post|schedule|publish|share)\b", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\b(on|at|today|tomorrow)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d{4}-\d{2}-\d{2})\b", "", cleaned)
    cleaned = re.sub(r"\b(\d{1,2}:\d{2})\b", "", cleaned)
    cleaned = re.sub(
        r"\b(\d{1,2}\s*(am|pm))\b", "", cleaned, flags=re.IGNORECASE
    )

    for k in PLATFORM_ALIASES.keys():
        cleaned = re.sub(rf"\b{k}\b", "", cleaned, flags=re.IGNORECASE)

    # remove "groups ..." part from idea if present
    cleaned = re.split(r"\bgroups?\b", cleaned, flags=re.IGNORECASE, maxsplit=1)[0].strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-")
    data["idea"] = cleaned

    # validate requirements
    if not data["idea"]:
        raise ValueError(
            "Couldn’t detect the idea. Example: 'Post 20% off on FB tomorrow 4pm'"
        )
    if not data["platforms"]:
        raise ValueError("Couldn’t detect platforms. Mention FB/IG/LinkedIn in the sentence.")

    # validate date/time formats if present
    if data["date"]:
        datetime.date.fromisoformat(data["date"])
    if data["time"]:
        datetime.datetime.strptime(data["time"], "%H:%M")

    return data


def parse_template_prompt(prompt: str):
    """
    Supports:
    - key: value lines (recommended)
    - OR old key=value; key=value format
    """
    data = {
        "date": "",
        "time": "",
        "platforms": "",
        "idea": "",
        "groups": "",
        "caption": "",
        "hashtags": "",
        "image_url": "",
    }

    text = prompt.strip()

    # 1) key: value (line-based or pipe-separated)
    candidates = []
    if "\n" in text:
        candidates = [line.strip() for line in text.splitlines() if line.strip()]
    elif "|" in text:
        candidates = [chunk.strip() for chunk in text.split("|") if chunk.strip()]

    for line in candidates:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip().replace("(optional)", "").strip()
            if key in data:
                data[key] = value

    # 2) fallback old key=value; ...
    if not data["platforms"] or not data["idea"]:
        parts = [p.strip() for p in text.split(";") if p.strip()]
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                if key in data:
                    data[key] = value

    # validation
    if not data["idea"]:
        raise ValueError("Missing 'idea'. Example: idea: 20% off for new subscribers")
    if not data["platforms"]:
        raise ValueError("Missing 'platforms'. Example: platforms: FB, LinkedIn")

    if data["date"]:
        datetime.date.fromisoformat(data["date"])
    if data["time"]:
        datetime.datetime.strptime(data["time"], "%H:%M")

    return data


# -------------------------
# Draft + preview + form (always above chat input)
# -------------------------
st.divider()
st.subheader("📝 Draft Post (edit + confirm)")
draft = st.session_state.draft

if not draft:
    st.info("No draft yet. Type a prompt at the bottom to create one.")
else:
    # ---------- Platform previews helpers ----------
    def escape_html(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def render_caption_html(text: str) -> str:
        safe = escape_html(text)
        safe = re.sub(r"(#\w+)", r"<span style='color:#1d9bf0; font-weight:600;'>\1</span>", safe)
        safe = safe.replace("\n", "<br>")
        return safe

    def render_li_preview(img_url: str, caption_text: str):
        max_width = 700
        border = "rgba(0,0,0,0.12)"
        subtle = "rgba(0,0,0,0.6)"
        text_main = "#111827"
        panel = "#ffffff"
        bg = "#f3f4f6"

        company = "Global Biznex"
        tagline = "Company • 1w • 🌎"
        headline = ""

        raw = (caption_text or "").strip()
        plain = raw.replace("\r\n", "\n")

        if not plain:
            body_html = f"<div style='color:{subtle}; font-size:14px;'>No caption</div>"
        else:
            max_chars = 180
            is_long = len(plain) > max_chars
            short = plain[:max_chars].rstrip()
            more_html = " <span style='color:#0a66c2; font-weight:700;'>…more</span>" if is_long else ""
            body_html = f"""
            <div style="font-size:16px; color:{text_main}; line-height:1.35; white-space:normal;">
                {render_caption_html(short)}{more_html}
            </div>
            """

        if img_url:
            media_html = f"""
            <div style="
                width:100%;
                aspect-ratio:16/9;
                background:#e5e7eb;
                overflow:hidden;
                border-top:1px solid {border};
                border-bottom:1px solid {border};
            ">
                <img src="{escape_html(img_url)}" style="width:100%;height:100%;object-fit:cover;display:block;" />
            </div>
            """
        else:
            media_html = f"""
            <div style="
                width:100%;
                aspect-ratio:16/9;
                background:#e5e7eb;
                display:flex;align-items:center;justify-content:center;
                color:{subtle};
                border-top:1px solid {border};
                border-bottom:1px solid {border};
                font-weight:700;
            ">No image</div>
            """

        html = textwrap.dedent(f"""
        <div style="background:{bg}; padding:10px;">
        <div style="
            max-width:{max_width}px;
            margin:0 auto;
            border:1px solid {border};
            border-radius:14px;
            overflow:hidden;
            background:{panel};
            box-shadow:0 6px 18px rgba(0,0,0,0.08);
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
        ">

            <div style="display:flex; gap:10px; padding:14px 14px 10px 14px; align-items:flex-start;">
            <div style="
                width:44px;
                height:44px;
                border-radius:50%;
                overflow:hidden;
                border:1px solid rgba(0,0,0,0.1);
                background:#ffffff;
                flex:0 0 auto;
            ">
                <img src="{escape_html(COMPANY_LOGO)}"
                    style="width:100%;height:100%;object-fit:cover;display:block;" />
            </div>

            <div style="line-height:1.15;">
                <div style="display:flex; align-items:center; gap:6px;">
                <div style="font-weight:900; color:{text_main}; font-size:16px;">{escape_html(company)}</div>
                <div style="width:18px;height:18px;border-radius:50%; background:#0a66c2; color:#fff;
                            display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;">✓</div>
                <div style="color:{subtle}; font-weight:600;">• 1st</div>
                </div>
                <div style="font-size:12.5px; color:{subtle}; margin-top:2px;">
                {escape_html(tagline)}
                </div>
                {f"<div style='font-size:12.5px;color:{subtle};'>{escape_html(headline)}</div>" if headline else ""}
            </div>

            <div style="margin-left:auto; color:{subtle}; font-size:18px; font-weight:900;">⋯</div>
            </div>

            <div style="padding:0 14px 12px 14px;">
            {body_html}
            </div>

            {media_html}

            <div style="display:flex; align-items:center; justify-content:space-between;
                        padding:10px 14px; color:{subtle}; font-size:13px;">
            <div>👍 ❤️ 🎉 <span style="margin-left:6px;">xyz and 88 others</span></div>
            <div>9 comments • 1 repost</div>
            </div>

            <div style="display:flex; gap:0; border-top:1px solid {border};">
            <div style="flex:1; padding:12px; text-align:center; font-weight:800; color:{subtle};">👍Like</div>
            <div style="flex:1; padding:12px; text-align:center; font-weight:800; color:{subtle};">💬Comment</div>
            <div style="flex:1; padding:12px; text-align:center; font-weight:800; color:{subtle};">🔁Repost</div>
            <div style="flex:1; padding:12px; text-align:center; font-weight:800; color:{subtle};">📧Send</div>
            </div>

        </div>
        </div>
        """).strip()

        components.html(html, height=760, scrolling=False)

    def render_fb_preview(img_url: str, caption_text: str):
        page_name = "Global Biznex"
        subtitle = "15h · 🌐"
        reactions = "260K"
        comments = "42K comments"
        shares = "25K shares"

        caption_html = render_caption_html(caption_text)

        if img_url:
            media_html = f"""
            <div style="background:#ffffff;">
            <div style="
                width:100%;
                aspect-ratio:4/3;
                background:#eee;
                overflow:hidden;
            ">
                <img src="{escape_html(img_url)}"
                    style="width:100%;height:100%;object-fit:cover;display:block;" />
            </div>
            </div>
            """
        else:
            media_html = """
            <div style="
                width:100%;
                aspect-ratio:4/3;
                background:#f3f4f6;
                display:flex;align-items:center;justify-content:center;
                color:#6b7280;font-weight:800;
            ">No image</div>
            """

        html = textwrap.dedent(f"""
        <div style="
            max-width:560px;
            border:1px solid #d9dde3;
            background:#ffffff;
            border-radius:12px;
            overflow:hidden;
            box-shadow:0 3px 12px rgba(0,0,0,0.10);
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
        ">

        <div style="padding:12px 12px 6px 12px; display:flex; gap:10px; align-items:flex-start;">
            <div style="
                width:42px;
                height:42px;
                border-radius:50%;
                overflow:hidden;
                border:1px solid rgba(0,0,0,0.15);
                background:#ffffff;
            ">
                <img src="{escape_html(COMPANY_LOGO)}"
                    style="width:100%;height:100%;object-fit:cover;display:block;" />
            </div>

            <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="font-weight:900; color:#111827; font-size:15px;">
                {escape_html(page_name)}
                </div>
                <div style="color:#1877f2; font-weight:800; font-size:14px;">· Follow</div>
            </div>
            <div style="font-size:12px; color:#6b7280; margin-top:2px;">
                {escape_html(subtitle)}
            </div>
            </div>

            <div style="display:flex; gap:10px; color:#6b7280; font-weight:900;">
            <div style="font-size:18px;">⋯</div>
            <div style="font-size:18px;">✕</div>
            </div>
        </div>

        <div style="padding:0 12px 10px 12px; color:#111827; font-size:14px; line-height:1.35;">
            {caption_html}
        </div>

        {media_html}

        <div style="padding:10px 12px; display:flex; align-items:center; justify-content:space-between; color:#6b7280; font-size:13px;">
            <div style="display:flex; align-items:center; gap:6px;">
            <span style="
                width:18px;height:18px;border-radius:50%;
                background:#1877f2;color:#fff;
                display:inline-flex;align-items:center;justify-content:center;
                font-size:12px;font-weight:900;
            ">👍</span>
            <span style="
                width:18px;height:18px;border-radius:50%;
                background:#f59e0b;color:#fff;
                display:inline-flex;align-items:center;justify-content:center;
                font-size:12px;font-weight:900;
            ">😮</span>
            <span style="font-weight:800;">{escape_html(reactions)}</span>
            </div>
            <div style="display:flex; gap:12px; font-weight:700;">
            <div>{escape_html(comments)}</div>
            <div>{escape_html(shares)}</div>
            </div>
        </div>

        <div style="height:1px;background:#e5e7eb;"></div>

        <div style="display:flex; justify-content:space-around; padding:10px 0; color:#6b7280; font-weight:900; font-size:14px;">
            <div style="display:flex; align-items:center; gap:8px;">👍 <span>Like</span></div>
            <div style="display:flex; align-items:center; gap:8px;">💬 <span>Comment</span></div>
            <div style="display:flex; align-items:center; gap:8px;">↗ <span>Share</span></div>
        </div>

        </div>
        """).strip()

        components.html(html, height=720, scrolling=False)

    def render_post_preview(platform: str, img_url: str, caption_text: str):
        platform_key = platform.strip().lower()

        if platform_key in ["ig", "instagram"]:
            username = "globalbiznex"
            location = ""
            max_width = 420
            border = "rgba(255,255,255,0.10)"
            subtle = "rgba(255,255,255,0.65)"
            text_main = "#ffffff"
            panel = "#0f1720"
            caption_html = render_caption_html(caption_text)

            if img_url:
                media_html = f"""
                <div style="
                    width:100%;
                    aspect-ratio:1/1;
                    background:#111827;
                    overflow:hidden;
                ">
                <img src="{escape_html(img_url)}"
                    style="width:100%;height:100%;object-fit:cover;display:block;" />
                </div>
                """
            else:
                media_html = """
                <div style="
                    width:100%;
                    aspect-ratio:1/1;
                    background:#111827;
                    display:flex;align-items:center;justify-content:center;
                    color:rgba(255,255,255,0.6);
                    font-weight:700;
                ">No image</div>
                """

            html = textwrap.dedent(f"""
                <div style="
                    max-width:{max_width}px;
                    margin-top:10px;
                    border:1px solid {border};
                    border-radius:14px;
                    overflow:hidden;
                    background:{panel};
                    box-shadow:0 6px 18px rgba(0,0,0,0.35);
                    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
                ">
                    <div style="display:flex;align-items:center;gap:10px;padding:12px;background:{panel};">
                        <div style="
                            width:36px;
                            height:36px;
                            border-radius:50%;
                            padding:2px;
                            background: radial-gradient(circle at 30% 30%, #f9ce34, #ee2a7b, #6228d7);
                        ">
                        <div style="
                            width:100%;
                            height:100%;
                            border-radius:50%;
                            overflow:hidden;
                            background:#fff;
                        ">
                            <img src="{escape_html(COMPANY_LOGO)}"
                                style="width:100%;height:100%;object-fit:cover;display:block;" />
                        </div>
                        </div>

                        <div style="line-height:1.1;">
                            <div style="font-weight:800;color:{text_main};font-size:14px;">{escape_html(username)}</div>
                            <div style="font-size:12px;color:{subtle};">{escape_html(location)}</div>
                        </div>
                        <div style="margin-left:auto;color:{subtle};font-size:18px;font-weight:900;">⋯</div>
                    </div>

                    {media_html}

                    <div style="display:flex;align-items:center;gap:14px;padding:10px 12px 6px;color:{text_main};font-size:18px;">
                        <div>♡</div><div>💬</div><div>✈️</div><div style="margin-left:auto">🔖</div>
                    </div>

                    <div style="padding:0 12px 8px;color:{text_main};font-size:13px;">
                        <span style="font-weight:800;">1,234</span> likes
                    </div>

                    <div style="padding:0 12px 10px;color:{text_main};font-size:13px;line-height:1.35;">
                        <span style="font-weight:800;">{escape_html(username)}</span>
                        <span style="font-weight:500;"> {caption_html}</span>
                    </div>

                    <div style="padding:0 12px 12px;color:{subtle};font-size:11px;">25 minutes ago</div>
                </div>
                """).strip()

            components.html(html, height=720, scrolling=False)
            return

        if platform_key in ["li", "linkedin"]:
            render_li_preview(img_url=img_url, caption_text=caption_text)
            return

        render_fb_preview(img_url=img_url, caption_text=caption_text)
        return

    # -------------------------
    # SIDE-BY-SIDE LAYOUT
    # -------------------------
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("📝 Draft")
        d = current_draft()

        st.session_state.setdefault("date_val", d.get("date", ""))
        st.session_state.setdefault("time_val", d.get("time", ""))
        st.session_state.setdefault("platforms_val", d.get("platforms", ""))
        st.session_state.setdefault("idea_val", d.get("idea", ""))
        st.session_state.setdefault("groups_val", d.get("groups", ""))
        st.session_state.setdefault("caption_val", d.get("caption", ""))
        st.session_state.setdefault("hashtags_val", d.get("hashtags", ""))
        st.session_state.setdefault("image_url_val", d.get("image_url", ""))

        date_val = st.text_input("Date (YYYY-MM-DD, optional)", key="date_val")
        time_val = st.text_input("Time (HH:MM, optional)", key="time_val")
        platforms_val = st.text_input("Platforms (comma-separated)", key="platforms_val")
        idea_val = st.text_area("Idea (required)", key="idea_val")
        groups_val = st.text_input("Groups (optional)", key="groups_val")
        caption_val = st.text_area("Caption (optional)", key="caption_val")
        hashtags_val = st.text_input("Hashtags (optional)", key="hashtags_val")
        image_url_val = st.text_input("Image URL (optional)", key="image_url_val")

        st.session_state.draft = {
            "date": date_val.strip(),
            "time": time_val.strip(),
            "platforms": platforms_val.strip(),
            "idea": idea_val.strip(),
            "groups": groups_val.strip(),
            "caption": caption_val.strip(),
            "hashtags": hashtags_val.strip(),
            "image_url": image_url_val.strip(),
        }

        col_a, col_b = st.columns(2)
        with col_a:
            save_clicked = st.button("✅ Confirm & Save to Google Sheet")
        with col_b:
            clear_clicked = st.button("🧹 Clear Draft")

    with right:
        st.subheader("👀 Preview")

        draft = st.session_state.draft

        st.caption(
            f"Date: {draft.get('date') or 'Any day'} | "
            f"Time: {draft.get('time') or 'Any time'} | "
            f"Platforms: {draft.get('platforms') or '-'}"
        )

        img = (draft.get("image_url") or "").strip()
        caption = (draft.get("caption") or "").strip()
        hashtags = (draft.get("hashtags") or "").strip()

        caption_preview = caption + ("\n\n" + hashtags if (caption and hashtags) else "")

        st.markdown("### Platform Preview")
        platforms_raw = draft.get("platforms") or ""
        platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()]
        if not platforms:
            platforms = ["FB", "IG", "LinkedIn"]

        tabs = st.tabs(platforms)
        for i, p in enumerate(platforms):
            with tabs[i]:
                render_post_preview(platform=p, img_url=img, caption_text=caption_preview)

    # -------------------------
    # Buttons actions (must be OUTSIDE columns)
    # -------------------------
    if clear_clicked:
        st.session_state.draft = None
        for k in ["date_val","time_val","platforms_val","idea_val","groups_val","caption_val","hashtags_val","image_url_val"]:
            st.session_state.pop(k, None)
        st.rerun()

    if save_clicked:
        if not idea_val.strip():
            st.error("Idea is required.")
        elif not platforms_val.strip():
            st.error("Platforms is required.")
        else:
            try:
                if date_val.strip():
                    datetime.date.fromisoformat(date_val.strip())
                if time_val.strip():
                    datetime.datetime.strptime(time_val.strip(), "%H:%M")
            except Exception:
                st.error("Invalid date/time. Date must be YYYY-MM-DD, time must be HH:MM (24-hour).")
            else:
                new_id = add_content_item(
                    date=date_val.strip(),
                    time=time_val.strip(),
                    platforms=platforms_val.strip(),
                    idea=idea_val.strip(),
                    caption=caption_val.strip(),
                    image_url=image_url_val.strip(),
                    hashtags=hashtags_val.strip(),
                    groups=groups_val.strip(),
                )
                st.success(f"Saved ✅ (ID {new_id}) — status is pending.")
                st.session_state.draft = None
                for k in ["date_val","time_val","platforms_val","idea_val","groups_val","caption_val","hashtags_val","image_url_val"]:
                    st.session_state.pop(k, None)
                st.rerun()


# -------------------------
# Chat input (keep LAST)
# -------------------------
user_prompt = st.chat_input("Type your scheduling request...")

if user_prompt:
    st.session_state.messages.append({"role": "user", "content": user_prompt})

    try:
        try:
            parsed = parse_simple_statement(user_prompt)
        except Exception:
            parsed = parse_template_prompt(user_prompt)

        st.session_state.draft = parsed

        assistant_reply = f"""
✅ **I understood your request**

Here’s what I extracted:

- **Date:** `{parsed['date'] or 'Any day'}`
- **Time:** `{parsed['time'] or 'Any time'}`
- **Platforms:** `{parsed['platforms']}`
- **Idea:** `{parsed['idea']}`
- **Groups:** `{parsed['groups'] or 'None'}`
- **Hashtags:** `{parsed['hashtags'] or 'Auto'}`
- **Image URL:** `{parsed['image_url'] or 'None'}`

👇 You can edit everything in the draft form above, then click **Confirm & Save**.
"""
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
        st.rerun()

    except Exception as e:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"⚠️ I couldn’t understand that.\n\n**Error:** {e}"}
        )
        st.rerun()
