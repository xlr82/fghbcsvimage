#!/usr/bin/env python3
"""
app.py – Streamlit Cloud / Docker version
Single “Download Results” ZIP (CSV + images)
"""
import csv, os, time, random, streamlit as st, zipfile, io
from pathlib import Path
from ddgs import DDGS
from urllib.parse import urlparse
import requests
import re

# ---------- helpers -------------------------------------------------------
def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', '_', text).strip()[:150]

def download_image(desc: str, out_dir: str) -> str:
    try:
        ddgs = DDGS()
        results = ddgs.images(query=desc, max_results=1)
        if not results:
            return ''
        img_url = results[0]['image']
        ext = Path(urlparse(img_url).path).suffix or '.jpg'
        fname = f"{safe_filename(desc)}{ext}"
        full_path = os.path.join(out_dir, fname)

        r = requests.get(img_url, timeout=15)
        r.raise_for_status()
        with open(full_path, 'wb') as fh:
            fh.write(r.content)
        return fname
    except Exception as e:
        raise e

# ---------- page / state --------------------------------------------------
st.set_page_config(page_title="CSV Image Downloader", layout="centered")
st.title("📸 CSV Image Downloader")

for k in ("csv_uploaded", "rows", "fieldnames", "zip_ready"):
    st.session_state.setdefault(k, None if k != "rows" else [])

log_placeholder = st.empty()

def log(msg: str):
    st.session_state.setdefault("log_buffer", [])
    st.session_state.log_buffer.append(msg)
    log_placeholder.code("\n".join(st.session_state.log_buffer[-200:]), language="text")

def reset_app():
    for k in ("csv_uploaded", "rows", "fieldnames", "zip_ready", "log_buffer"):
        st.session_state.pop(k, None)
    st.rerun()

# ---------- file upload ---------------------------------------------------
if st.session_state.csv_uploaded is None:
    uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="csv_uploader")
    if uploaded:
        csv_bytes = uploaded.read()
        csv_text  = csv_bytes.decode("utf-8").splitlines()
        reader     = csv.DictReader(csv_text)
        rows       = list(reader)
        fieldnames = reader.fieldnames or []

        if "description" not in fieldnames:
            st.error("CSV must contain a 'description' column.")
        else:
            st.session_state.csv_uploaded = uploaded.name
            st.session_state.rows       = rows
            st.session_state.fieldnames = fieldnames
            st.rerun()
else:
    st.info(f"Loaded CSV: **{st.session_state.csv_uploaded}** — {len(st.session_state.rows)} rows")

# ---------- processing ----------------------------------------------------
if st.session_state.csv_uploaded and not st.session_state.zip_ready:
    out_dir = st.text_input("Output folder (inside container)", value="/tmp/images")
    os.makedirs(out_dir, exist_ok=True)

    if st.button("Start Processing", type="primary"):
        log("🚀 Starting download…")
        progress = st.progress(0)
        rows = st.session_state.rows
        for idx, row in enumerate(rows):
            desc = row.get("description", "").strip()
            if not desc:
                log(f"⚠️ Row {idx+1}: empty description – skipped")
                row["image"] = ""
                continue
            try:
                log(f"📥 Row {idx+1}: searching image for '{desc[:60]}…'")
                image_name = download_image(desc, out_dir)
                if image_name:
                    log(f"✅ Row {idx+1}: saved as {image_name}")
                    row["image"] = image_name
                else:
                    log(f"⚠️ Row {idx+1}: no image found")
                    row["image"] = ""
            except Exception as e:
                log(f"❌ Row {idx+1}: error – {e}")
                row["image"] = ""
            progress.progress((idx + 1) / len(rows))
            time.sleep(random.uniform(1, 3))

        # build single ZIP with CSV + images
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1) updated CSV
            csv_path = os.path.join(out_dir, "updated.csv")
            with open(csv_path, "w", newline='', encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=st.session_state.fieldnames).writeheader()
                csv.DictWriter(f, fieldnames=st.session_state.fieldnames).writerows(rows)
            zf.write(csv_path, arcname="updated.csv")
            # 2) all images
            for fn in os.listdir(out_dir):
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    zf.write(os.path.join(out_dir, fn), arcname=fn)
        buf.seek(0)
        st.session_state.zip_ready = buf.getvalue()
        st.rerun()

# ---------- single download + reset --------------------------------------
if st.session_state.zip_ready:
    st.success("Processing finished!")
    st.download_button("📁 Download Results (ZIP)", st.session_state.zip_ready,
                       file_name="results.zip", mime="application/zip")
    if st.button("Find New Images", type="secondary"):
        reset_app()