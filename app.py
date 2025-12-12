import streamlit as st
from bot import add_content_item, process_all_pending_items

import datetime

st.set_page_config(page_title="Biznex Bot 🤖 – Content Scheduler", page_icon="🤖")

st.title("Biznex Bot 🤖 – Content Scheduler")

st.write(
    """
Type a **prompt** to schedule a post.  
The bot will parse it, save it to the Google Sheet, and (optionally) run the posting bot.

Use this format (simple, consistent):

`date=YYYY-MM-DD; platforms=FB, IG, LinkedIn; idea=Your idea here; groups=Group 1, Group 2; caption=Optional caption; hashtags=#tag1 #tag2`

- **date** → when it should be posted (YYYY-MM-DD). Leave blank to post any day the bot runs.
- **platforms** → e.g. `FB`, `FB, LinkedIn`, `IG`
- **idea** → main content idea
- **groups** → optional, FB groups list
- **caption** → optional, if you want to write it yourself
- **hashtags** → optional
"""
)

st.divider()

# Keep chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Tell me how you want to schedule your post."}
    ]

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Checkbox: run the posting bot immediately after scheduling
run_immediately = st.checkbox("Run posting bot immediately after scheduling", value=False)

def parse_prompt(prompt: str):
    """
    Very simple parser for prompts like:
    date=2025-12-15; platforms=FB, IG; idea=Something; groups=G1, G2; caption=...; hashtags=...
    Returns a dict with keys: date, platforms, idea, groups, caption, hashtags, image_url
    """
    data = {
        "date": "",
        "platforms": "",
        "idea": "",
        "groups": "",
        "caption": "",
        "hashtags": "",
        "image_url": "",
    }

    parts = [p.strip() for p in prompt.split(";") if p.strip()]
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in data:
                data[key] = value

    # Basic validation
    if not data["idea"]:
        raise ValueError("Missing 'idea'. Please include: idea=Your main idea")
    if not data["platforms"]:
        raise ValueError("Missing 'platforms'. Please include: platforms=FB, IG, LinkedIn")

    # Optional: check date format if provided
    if data["date"]:
        try:
            datetime.date.fromisoformat(data["date"])
        except ValueError:
            raise ValueError("Date must be in format YYYY-MM-DD, e.g. 2025-12-15")

    return data

# Chat input at the bottom
user_prompt = st.chat_input("Type your scheduling prompt here...")

if user_prompt:
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_prompt})

    try:
        parsed = parse_prompt(user_prompt)

        with st.chat_message("assistant"):
            st.markdown("Got it! Let me schedule that for you...")

        new_id = add_content_item(
            date=parsed["date"],
            platforms=parsed["platforms"],
            idea=parsed["idea"],
            caption=parsed["caption"],
            image_url=parsed["image_url"],
            hashtags=parsed["hashtags"],
            groups=parsed["groups"],
        )

        reply = (
            f"✅ Scheduled post **ID {new_id}**\n\n"
            f"- **Date**: `{parsed['date'] or 'any day the bot runs'}`\n"
            f"- **Platforms**: `{parsed['platforms']}`\n"
            f"- **Idea**: `{parsed['idea']}`\n"
            f"- **Groups**: `{parsed['groups'] or 'none'}`\n"
            f"- **Caption**: `{parsed['caption'] or 'auto-generated from idea'}`\n"
            f"- **Hashtags**: `{parsed['hashtags'] or 'auto-generated / default'}`\n"
            f"- **Status**: `pending` (will be posted when the bot runs)"
        )

        # Optionally run the posting bot immediately
        if run_immediately:
            with st.chat_message("assistant"):
                st.markdown(reply)
                st.markdown("🚀 Running the posting bot now...")
            try:
                process_all_pending_items()
                reply += "\n\n🚀 Bot has just run. Check your sheet/logs for updates."
            except Exception as e:
                reply += f"\n\n⚠️ Tried to run bot, but got an error: `{e}`"

        # Add assistant reply to chat
        st.session_state.messages.append({"role": "assistant", "content": reply})

    except Exception as e:
        error_msg = f"⚠️ I couldn't understand that. Error: {e}"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
