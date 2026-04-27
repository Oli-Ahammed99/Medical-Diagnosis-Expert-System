#!/usr/bin/env python
"""
Medical Expert System - Web Application
A local web-based interface for the medical diagnosis expert system.
Run this file and access the application at http://localhost:5000
"""

import os
import json
import html
import webbrowser
import tempfile
import subprocess
import re
import textwrap
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, abort, url_for, send_file
import threading
import time
import uuid
from io import BytesIO
from expert import DiagnosisFlow, diagnose_from_answers

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

# Store diagnosis sessions
sessions = {}


def get_markdown_path_for_disease(disease):
    if not disease:
        return None
    path = BASE_DIR / "Treatment" / "markdown" / f"{disease}.md"
    return path if path.exists() else None


def get_treatment_html_path(filename):
    treatment_dir = BASE_DIR / "Treatment" / "html"
    file_path = (treatment_dir / filename).resolve()
    try:
        file_path.relative_to(treatment_dir.resolve())
    except ValueError:
        return None
    if not file_path.exists() or not file_path.is_file():
        return None
    return file_path


def extract_treatment_body(html_content):
    match = re.search(r"<body[^>]*>(.*)</body>", html_content, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return html_content


def get_browser_pdf_executable():
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def markdown_to_html_content(raw_text):
    lines = raw_text.splitlines()
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            continue

        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            continue

        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            continue

        if stripped[:2].isdigit() and stripped[1] == ".":
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
            continue

        if stripped.startswith(("- ", "* ")):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
            continue

        if in_list:
            html_parts.append("</ul>")
            in_list = False

        cleaned = stripped.replace("**", "").replace("_", "")
        html_parts.append(f"<p>{html.escape(cleaned)}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "".join(html_parts)


def get_disease_content(disease):
    html_path = get_treatment_html_path(f"{disease}.html")
    if html_path:
        return extract_treatment_body(html_path.read_text(encoding="utf-8", errors="ignore"))

    md_path = get_markdown_path_for_disease(disease)
    if md_path:
        return markdown_to_html_content(md_path.read_text(encoding="utf-8", errors="ignore"))

    return None


def html_to_plain_text(html_content):
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", html_content, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|h[1-6]|li|div|tr)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _pdf_escape(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(title, html_content, summary_html=""):
    plain_text = html_to_plain_text(f"{summary_html}\n{html_content}")
    lines = [title, ""]
    for paragraph in plain_text.splitlines():
        lines.extend(textwrap.wrap(paragraph, width=88) or [""])
        lines.append("")

    y = 790
    page_lines = []
    pages = []
    for line in lines:
        if y < 56:
            pages.append(page_lines)
            page_lines = []
            y = 790
        page_lines.append((line, y))
        y -= 14
    if page_lines:
        pages.append(page_lines)

    objects = []
    page_refs = []
    catalog_id = 1
    pages_id = 2
    font_id = 3
    next_id = 4

    for page in pages:
        content_id = next_id
        page_id = next_id + 1
        next_id += 2
        commands = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        previous_y = 790
        for line, line_y in page:
            if line_y != previous_y:
                commands.append(f"0 -{previous_y - line_y} Td")
            commands.append(f"({_pdf_escape(line)}) Tj")
            previous_y = line_y
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        objects.append((content_id, b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"))
        objects.append((page_id, f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")))
        page_refs.append(f"{page_id} 0 R")

    objects.insert(0, (font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objects.insert(0, (pages_id, f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("ascii")))
    objects.insert(0, (catalog_id, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")))

    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, body in objects:
        offsets.append(output.tell())
        output.write(f"{obj_id} 0 obj\n".encode("ascii"))
        output.write(body)
        output.write(b"\nendobj\n")
    xref_start = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii"))
    output.seek(0)
    return output


def build_browser_pdf(title, html_content, summary_html=""):
    browser = get_browser_pdf_executable()
    if not browser:
        return build_simple_pdf(title, html_content, summary_html)

    rendered_html = render_template_string(
        PDF_PRINT_PAGE,
        title=title,
        summary_html=summary_html,
        content=html_content,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        html_path = Path(temp_dir) / "document.html"
        pdf_path = Path(temp_dir) / "document.pdf"
        html_path.write_text(rendered_html, encoding="utf-8")

        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            str(html_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode != 0 or not pdf_path.exists():
            fallback_command = [
                browser,
                "--headless",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"--print-to-pdf={pdf_path}",
                str(html_path),
            ]
            result = subprocess.run(fallback_command, capture_output=True, text=True, timeout=45)
            if result.returncode != 0 or not pdf_path.exists():
                return build_simple_pdf(title, html_content, summary_html)

        return BytesIO(pdf_path.read_bytes())

MAIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medical Expert System</title>
    <style>
        :root {
            --bg-1: #edf6ff;
            --bg-2: #f8fbff;
            --card: #ffffff;
            --ink: #0f172a;
            --muted: #516176;
            --line: #d9e5f2;
            --primary: #13578f;
            --primary-2: #2a79bf;
            --accent: #0f766e;
            --shadow-lg: 0 24px 56px rgba(19, 87, 143, 0.14);
            --shadow-md: 0 14px 34px rgba(19, 87, 143, 0.12);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 12% 2%, rgba(42,121,191,0.15), transparent 38%),
                radial-gradient(circle at 94% 96%, rgba(15,118,110,0.12), transparent 38%),
                linear-gradient(165deg, var(--bg-1) 0%, var(--bg-2) 100%);
            min-height: 100vh;
            padding: 24px;
            display: grid;
            place-items: center;
        }
        .container {
            width: 100%;
            max-width: 1020px;
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
        }
        .topbar {
            padding: 14px 24px;
            border-bottom: 1px solid #e8f0f8;
            background: #fcfeff;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            font-size: 0.9rem;
        }
        .brand {
            font-weight: 700;
            color: var(--primary);
            letter-spacing: 0.02em;
        }
        .status {
            color: var(--muted);
            font-weight: 600;
        }
        .hero {
            padding: 34px;
            display: grid;
            grid-template-columns: 1.3fr 1fr;
            gap: 20px;
            background: linear-gradient(140deg, #ffffff 0%, #f8fcff 100%);
        }
        .headline {
            background: linear-gradient(130deg, var(--primary) 0%, var(--primary-2) 62%, var(--accent) 100%);
            color: #fff;
            border-radius: 16px;
            padding: 28px;
        }
        .badge {
            display: inline-block;
            margin-bottom: 10px;
            padding: 5px 11px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            border: 1px solid rgba(255,255,255,0.35);
            background: rgba(255,255,255,0.16);
        }
        .headline h1 {
            font-size: clamp(1.7rem, 3vw, 2.35rem);
            line-height: 1.2;
            margin-bottom: 10px;
        }
        .headline p {
            line-height: 1.55;
            opacity: 0.96;
            max-width: 620px;
        }
        .meta {
            margin-top: 16px;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
        }
        .meta-item {
            background: #f8fcff;
            border: 1px solid #e1edf9;
            border-radius: 12px;
            padding: 12px;
        }
        .meta-item strong {
            display: block;
            color: var(--ink);
            margin-bottom: 4px;
            font-size: 0.9rem;
        }
        .meta-item span {
            color: var(--muted);
            font-size: 0.84rem;
            line-height: 1.4;
        }
        .side {
            border: 1px solid #e1edf8;
            border-radius: 16px;
            padding: 18px;
            background: #fbfdff;
        }
        .side h3 {
            font-size: 1rem;
            margin-bottom: 10px;
            color: var(--ink);
        }
        .steps {
            list-style: none;
            display: grid;
            gap: 10px;
            margin-bottom: 16px;
        }
        .steps li {
            padding: 10px;
            background: #f4f9ff;
            border: 1px solid #dbe9f8;
            border-radius: 10px;
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.4;
        }
        .start-btn {
            width: 100%;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-size: 1rem;
            font-weight: 700;
            color: white;
            background: linear-gradient(120deg, var(--primary) 0%, var(--primary-2) 100%);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s, filter 0.2s;
        }
        .start-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
            filter: brightness(1.03);
        }
        .disclaimer {
            margin: 0 34px 28px;
            border: 1px solid #ffdb99;
            background: #fff8e9;
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 0.86rem;
            color: #764400;
            line-height: 1.5;
        }
        @media (max-width: 900px) {
            .hero { grid-template-columns: 1fr; }
            .meta { grid-template-columns: 1fr; }
        }
        @media (max-width: 640px) {
            body { padding: 14px; }
            .topbar { padding: 12px 14px; }
            .hero { padding: 16px; }
            .headline { padding: 18px; }
            .disclaimer { margin: 0 16px 16px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar">
            <span class="brand">Medical Expert System</span>
            <span class="status">Educational Decision Support</span>
        </div>

        <div class="hero">
            <div>
                <div class="headline">
                    <span class="badge">Digital Triage Assistant</span>
                    <h1>Check Symptoms with a Clear Guided Flow</h1>
                    <p>This assistant asks structured questions about your condition and medical history, then provides a likely disease match from the current database.</p>
                </div>
                <div class="meta">
                    <div class="meta-item">
                        <strong>Condition Coverage</strong>
                        <span>22 common diseases available in the current model.</span>
                    </div>
                    <div class="meta-item">
                        <strong>History Aware</strong>
                        <span>Considers past conditions and related risk factors.</span>
                    </div>
                    <div class="meta-item">
                        <strong>Treatment Reference</strong>
                        <span>Links to practical cure and prevention details.</span>
                    </div>
                </div>
            </div>

            <aside class="side">
                <h3>How It Works</h3>
                <ul class="steps">
                    <li>1. Start diagnosis and answer each question honestly.</li>
                    <li>2. Select symptoms and medical background details.</li>
                    <li>3. Review the suggested result and treatment page.</li>
                </ul>
                <button class="start-btn" onclick="startDiagnosis()">Start Diagnosis</button>
            </aside>
        </div>

        <div class="disclaimer">
            <strong>Medical Disclaimer:</strong> This tool is for educational use only and does not replace professional medical advice.
        </div>
    </div>

    <script>
        function startDiagnosis() {
            window.location.href = '/diagnosis';
        }
    </script>
</body>
</html>
"""

DIAGNOSIS_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diagnosis - Medical Expert System</title>
    <style>
        :root {
            --bg-1: #eff7ff;
            --bg-2: #f9fcff;
            --card: #ffffff;
            --ink: #0f172a;
            --muted: #4e6277;
            --line: #d9e6f3;
            --primary: #13578f;
            --primary-2: #2a79bf;
            --accent: #0f766e;
            --danger: #be123c;
            --shadow-lg: 0 24px 52px rgba(19, 87, 143, 0.14);
            --shadow-sm: 0 10px 24px rgba(19, 87, 143, 0.12);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 8% 0%, rgba(42,121,191,0.14), transparent 40%),
                radial-gradient(circle at 95% 100%, rgba(15,118,110,0.12), transparent 38%),
                linear-gradient(165deg, var(--bg-1) 0%, var(--bg-2) 100%);
            min-height: 100vh;
            padding: 12px;
        }
        .shell {
            width: 100%;
            max-width: 860px;
            margin: 0 auto;
            display: block;
        }
        .side {
            background: #fbfdff;
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 16px;
            align-self: start;
            position: sticky;
            top: 16px;
            display: none;
        }
        .side h3 {
            font-size: 0.95rem;
            margin-bottom: 10px;
            color: var(--primary);
        }
        .side p {
            color: var(--muted);
            font-size: 0.86rem;
            line-height: 1.5;
            margin-bottom: 8px;
        }
        .container {
            width: 100%;
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 22px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
            min-height: 0;
        }
        .header {
            background: linear-gradient(130deg, var(--primary) 0%, var(--primary-2) 62%, var(--accent) 100%);
            color: white;
            padding: 16px 20px;
            display: grid;
            gap: 10px;
            position: sticky;
            top: 0;
            z-index: 5;
        }
        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .header h2 {
            font-size: 1.03rem;
            letter-spacing: 0.02em;
        }
        .progress-label {
            font-size: 0.82rem;
            padding: 6px 10px;
            border: 1px solid rgba(255,255,255,0.35);
            border-radius: 999px;
            background: rgba(255,255,255,0.18);
            white-space: nowrap;
        }
        .progress-track {
            width: 100%;
            height: 8px;
            border-radius: 999px;
            background: rgba(255,255,255,0.25);
            overflow: hidden;
        }
        .progress-fill {
            width: 6%;
            height: 100%;
            border-radius: 999px;
            background: #d9f3ff;
            transition: width 0.25s ease;
        }
        .content {
            padding: 22px 20px 24px;
            min-height: 0;
            overflow: visible;
        }
        .prediction-banner {
            display: none;
            margin-bottom: 16px;
            padding: 16px 18px;
            border: 1px solid #cde4d9;
            border-radius: 16px;
            background: linear-gradient(135deg, #f5fffb 0%, #ecfbff 100%);
            box-shadow: 0 10px 22px rgba(15, 118, 110, 0.08);
        }
        .prediction-banner.show {
            display: block;
        }
        .prediction-banner.final {
            border-color: #c9dcf0;
            background: linear-gradient(135deg, #f7fbff 0%, #eef8ff 100%);
            box-shadow: 0 10px 22px rgba(19, 87, 143, 0.08);
        }
        .prediction-banner h3 {
            font-size: 1rem;
            color: #0f5c55;
            margin-bottom: 8px;
        }
        .prediction-banner p {
            color: var(--muted);
            font-size: 0.94rem;
            line-height: 1.5;
        }
        .prediction-actions {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }
        .secondary-btn {
            padding: 12px 14px;
            border: 1px solid #cfe0ef;
            border-radius: 11px;
            font-size: 0.94rem;
            font-weight: 700;
            cursor: pointer;
            color: var(--ink);
            background: #fff;
            transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
        }
        .secondary-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-sm);
            border-color: #b6cee5;
        }
        .question-stream {
            display: grid;
            gap: 16px;
            position: relative;
            padding-left: 16px;
        }
        .question-stream::before {
            content: "";
            position: absolute;
            top: 6px;
            bottom: 6px;
            left: 6px;
            width: 2px;
            background: linear-gradient(180deg, rgba(42,121,191,0.28) 0%, rgba(15,118,110,0.2) 100%);
            border-radius: 999px;
        }
        .loading-note {
            color: var(--muted);
            font-size: 0.95rem;
            text-align: left;
            padding: 14px 10px;
        }
        #content > * {
            width: 100%;
            max-width: 100%;
        }
        .question-card {
            width: 100%;
            position: relative;
        }
        .question-card::before {
            content: "";
            position: absolute;
            left: -14px;
            top: 14px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary-2), var(--accent));
            box-shadow: 0 0 0 4px #eef6fd;
        }
        .question-meta {
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--primary);
            margin: 0 0 8px 6px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .question-section {
            background: #ffffff;
            border: 1px solid #e2edf8;
            border-radius: 18px;
            padding: 22px;
            transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
        }
        .question-section.active {
            border-color: #9ec6e9;
            box-shadow: 0 14px 32px rgba(19, 87, 143, 0.1);
        }
        .question-section.answered {
            background: linear-gradient(180deg, #fbfdff 0%, #f6fbff 100%);
            border-color: #d7e6f4;
        }
        .answer-preview {
            margin-top: 12px;
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.4;
            border-top: 1px solid #e1ebf5;
            padding-top: 12px;
        }
        .card-actions {
            display: flex;
            gap: 10px;
            margin-top: 14px;
            flex-wrap: wrap;
        }
        .edit-btn {
            padding: 10px 14px;
            border: 1px solid #c7dbec;
            border-radius: 999px;
            background: #fff;
            color: var(--primary);
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
        }
        .edit-btn:hover {
            border-color: #91bce3;
            background: #f7fbff;
        }
        .question-section.editing {
            border-color: #86bbdf;
            box-shadow: 0 14px 32px rgba(19, 87, 143, 0.08);
        }
        .selected-answer {
            background: #eff7ff;
            border-color: #9ac4e8;
        }
        .question {
            font-size: 1.14rem;
            color: var(--ink);
            margin-bottom: 16px;
            line-height: 1.5;
            font-weight: 600;
        }
        .yes-no-buttons {
            display: flex;
            gap: 10px;
        }
        .yes-btn, .no-btn {
            flex: 1;
            padding: 13px 18px;
            border: none;
            border-radius: 11px;
            font-size: 0.98rem;
            font-weight: 700;
            cursor: pointer;
            color: white;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .yes-btn { background: linear-gradient(130deg, #0f766e, #0d9488); }
        .no-btn { background: linear-gradient(130deg, #be123c, #e11d48); }
        .yes-btn:hover, .no-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-sm);
        }
        .option-btn {
            width: 100%;
            padding: 13px 14px;
            margin-bottom: 9px;
            border-radius: 11px;
            border: 1px solid #d9e6f3;
            background: #fafdff;
            color: var(--ink);
            text-align: left;
            font-size: 0.96rem;
            cursor: pointer;
            transition: background 0.2s, border-color 0.2s, transform 0.2s;
        }
        .option-btn:hover {
            background: #eff7ff;
            border-color: #b8d2eb;
            transform: translateX(2px);
        }
        .text-input {
            width: 100%;
            padding: 13px;
            border: 1px solid #cfe0ef;
            border-radius: 11px;
            font-size: 0.98rem;
            margin-bottom: 11px;
            font-family: inherit;
        }
        .text-input:focus {
            outline: none;
            border-color: #3b87c8;
            box-shadow: 0 0 0 4px rgba(59,135,200,0.14);
        }
        .submit-btn {
            width: 100%;
            padding: 13px;
            border: none;
            border-radius: 11px;
            font-size: 0.98rem;
            font-weight: 700;
            color: #fff;
            cursor: pointer;
            background: linear-gradient(120deg, var(--primary) 0%, var(--primary-2) 100%);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-sm);
        }
        .checkbox-group {
            display: grid;
            gap: 9px;
            margin-bottom: 12px;
        }
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 11px 12px;
            border: 1px solid #dbe8f5;
            border-radius: 10px;
            background: #fbfdff;
            transition: background 0.2s, border-color 0.2s;
            cursor: pointer;
        }
        .checkbox-label:hover { border-color: #bcd5eb; }
        .checkbox-label.checked {
            background: #eef7ff;
            border-color: #9fc4e6;
        }
        .checkbox-label input {
            width: 18px;
            height: 18px;
            accent-color: var(--primary);
        }
        @media (max-width: 640px) {
            body { padding: 14px; }
            .content { padding: 18px 14px; }
            .question-stream { padding-left: 14px; }
            .question-card::before { left: -12px; }
            .question { font-size: 1.03rem; }
            .yes-no-buttons { flex-direction: column; }
            .prediction-actions { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="shell">
        <div class="container">
            <div class="header">
                <div class="header-top">
                    <h2>Medical Diagnosis</h2>
                    <span class="progress-label">Question <span id="q-num">1</span></span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" id="q-fill"></div>
                </div>
            </div>
            <div class="content" id="content">
                <div class="prediction-banner" id="prediction-banner">
                    <h3 id="prediction-title"></h3>
                    <p id="prediction-text"></p>
                    <div class="prediction-actions">
                        <button class="submit-btn" type="button" onclick="continueAfterPrediction()">Continue Questions</button>
                        <button class="secondary-btn" type="button" onclick="focusForAnswerChange()">Change Answers</button>
                    </div>
                </div>
                <div class="question-stream" id="question-stream">
                    <p class="loading-note" id="loading-note">Loading questions...</p>
                </div>
            </div>
        </div>
    </div>
    <script>
        let sessionId = '{{ session_id }}';
        let selectedOptions = [];
        let currentQuestionKey = null;
        let isSubmitting = false;
        let questionStore = {};
        let answerStore = {};
        let editingKey = null;
        let waitingForPredictionChoice = false;
        let pendingResult = null;

        function setVisualProgress(step) {
            const fill = document.getElementById('q-fill');
            const percent = Math.min(100, Math.max(6, step * 7));
            fill.style.width = percent + '%';
        }

        function getQuestionStream() {
            return document.getElementById('question-stream');
        }

        function getContentPane() {
            return document.getElementById('content');
        }

        function getActiveQuestionSection() {
            return document.querySelector('.question-section.active');
        }

        function hidePredictionBanner() {
            const banner = document.getElementById('prediction-banner');
            banner.classList.remove('show');
            banner.classList.remove('final');
            waitingForPredictionChoice = false;
            pendingResult = null;
        }

        function formatAnswer(answer) {
            if (Array.isArray(answer)) {
                return answer.join(', ');
            }
            return String(answer || '');
        }

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function escapeAttribute(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;');
        }

        function rememberQuestion(question) {
            questionStore[question.key] = question;
        }

        function renderYesNoButtons(answer, submitFn) {
            return `
                <div class="yes-no-buttons">
                    <button class="yes-btn ${answer === 'yes' ? 'selected-answer' : ''}" type="button" onclick="${escapeAttribute(`${submitFn}${JSON.stringify("yes")})`)}">Yes</button>
                    <button class="no-btn ${answer === 'no' ? 'selected-answer' : ''}" type="button" onclick="${escapeAttribute(`${submitFn}${JSON.stringify("no")})`)}">No</button>
                </div>
            `;
        }

        function renderSelectButtons(question, answer, submitFn) {
            return `
                <div class="options">
                    ${question.options.map(opt => `
                        <button class="option-btn ${answer === opt ? 'selected-answer' : ''}" type="button" onclick="${escapeAttribute(`${submitFn}${JSON.stringify(opt)})`)}">${escapeHtml(opt)}</button>
                    `).join('')}
                </div>
            `;
        }

        function renderMultiOptions(question, answer, editable) {
            const values = Array.isArray(answer) ? answer : [];
            return `
                <div class="checkbox-group">
                    ${question.options.map(opt => `
                        <label class="checkbox-label ${values.includes(opt) ? 'checked' : ''}">
                            <input type="checkbox" ${values.includes(opt) ? 'checked' : ''} ${editable ? '' : 'disabled'} onchange='toggleCheckbox(${JSON.stringify(opt)}, this)'>
                            <span>${escapeHtml(opt)}</span>
                        </label>
                    `).join('')}
                </div>
            `;
        }

        function renderQuestionSection(question, answer, mode) {
            const sectionClass = mode === 'active' ? 'question-section active' : mode === 'editing' ? 'question-section editing' : 'question-section answered';
            let controls = '';

            if (mode === 'answered') {
                controls = `
                    <div class="answer-preview">Your answer: ${escapeHtml(formatAnswer(answer))}</div>
                    <div class="card-actions">
                        <button class="edit-btn" type="button" onclick='startEdit(${JSON.stringify(question.key)})'>Change answer</button>
                    </div>
                `;
            } else if (question.type === 'text') {
                const action = mode === 'editing' ? `saveEditedText(${JSON.stringify(question.key)})` : 'submitText()';
                controls = `
                    <input type="text" class="text-input" id="text-answer-${escapeHtml(question.key)}" data-key="${escapeHtml(question.key)}" value="${escapeHtml(answer || '')}" placeholder="Type your answer..." autofocus onkeydown="handleTextKeydown(event, ${escapeAttribute(JSON.stringify(question.key))})">
                    <div class="card-actions">
                        <button class="submit-btn" type="button" onclick="${action}">${mode === 'editing' ? 'Save change' : 'Continue'}</button>
                        ${mode === 'editing' ? `<button class="secondary-btn" type="button" onclick='cancelEdit(${JSON.stringify(question.key)})'>Cancel</button>` : ''}
                    </div>
                `;
            } else if (question.type === 'yesno') {
                const submitFn = mode === 'editing' ? `saveEditedAnswer(${JSON.stringify(question.key)}, ` : 'submitAnswer(';
                controls = renderYesNoButtons(answer, submitFn);
                if (mode === 'editing') {
                    controls += `<div class="card-actions"><button class="secondary-btn" type="button" onclick='cancelEdit(${JSON.stringify(question.key)})'>Cancel</button></div>`;
                }
            } else if (question.type === 'select') {
                const submitFn = mode === 'editing' ? `saveEditedAnswer(${JSON.stringify(question.key)}, ` : 'submitAnswer(';
                controls = renderSelectButtons(question, answer, submitFn);
                if (mode === 'editing') {
                    controls += `<div class="card-actions"><button class="secondary-btn" type="button" onclick='cancelEdit(${JSON.stringify(question.key)})'>Cancel</button></div>`;
                }
            } else if (question.type === 'multi') {
                selectedOptions = Array.isArray(answer) ? [...answer] : [];
                controls = `
                    ${renderMultiOptions(question, answer, true)}
                    <div class="card-actions">
                        <button class="submit-btn" type="button" onclick="${mode === 'editing' ? `saveEditedMulti(${JSON.stringify(question.key)})` : 'submitMultiSelect()'}">${mode === 'editing' ? 'Save change' : 'Continue'}</button>
                        ${mode === 'editing' ? `<button class="secondary-btn" type="button" onclick='cancelEdit(${JSON.stringify(question.key)})'>Cancel</button>` : ''}
                    </div>
                `;
            }

            return `
                <div class="${sectionClass}" data-key="${escapeHtml(question.key)}">
                    <div class="question">${escapeHtml(question.question)}</div>
                    ${controls}
                </div>
            `;
        }

        function renderQuestionCard(question, answer, mode) {
            const wrapper = document.querySelector('.question-card[data-key="' + question.key + '"]') || document.createElement('div');
            wrapper.className = 'question-card';
            wrapper.dataset.key = question.key;
            wrapper.innerHTML = `
                <div class="question-meta">Question ${question.step}</div>
                ${renderQuestionSection(question, answer, mode)}
            `;
            return wrapper;
        }

        function replaceCard(question, answer, mode) {
            const stream = getQuestionStream();
            const card = renderQuestionCard(question, answer, mode);
            const existing = document.querySelector('.question-card[data-key="' + question.key + '"]');
            if (existing) {
                existing.replaceWith(card);
            } else {
                stream.appendChild(card);
            }
            return card;
        }

        function pruneCardsAfter(key) {
            const cards = Array.from(document.querySelectorAll('.question-card'));
            let remove = false;
            cards.forEach(card => {
                if (remove) {
                    card.remove();
                }
                if (card.dataset.key === key) {
                    remove = true;
                }
            });
        }

        function appendQuestionCard(data) {
            const stream = getQuestionStream();
            const loading = document.getElementById('loading-note');
            if (loading) loading.remove();
            if (getActiveQuestionSection()) return;
            rememberQuestion(data.question);
            data.question.step = data.step;
            const wrapper = replaceCard(data.question, answerStore[data.question.key] || null, 'active');
            currentQuestionKey = data.key || null;
            wrapper.scrollIntoView({ behavior: 'smooth', block: 'end' });
            const content = getContentPane();
            content.scrollTop = content.scrollHeight;
        }

        function showPredictionBanner(prediction) {
            const banner = document.getElementById('prediction-banner');
            banner.classList.remove('final');
            document.getElementById('prediction-title').textContent = 'We predicted your disease: ' + prediction.disease;
            document.getElementById('prediction-text').textContent = 'You can continue answering questions for a more complete check, or change your previous answers before going on.';
            banner.classList.add('show');
            waitingForPredictionChoice = true;
            banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function showFinalResultBanner(result) {
            const banner = document.getElementById('prediction-banner');
            pendingResult = result;
            banner.classList.add('final');
            document.getElementById('prediction-title').textContent = result && result.disease
                ? 'We detected a disease: ' + result.disease
                : 'Diagnosis is complete';
            document.getElementById('prediction-text').textContent = result && result.disease
                ? 'Do you want to see the result now, or change your answers first?'
                : 'The diagnosis flow is complete. You can review the result or change your answers first.';
            banner.classList.add('show');
            waitingForPredictionChoice = true;
            const actions = document.querySelector('.prediction-actions');
            actions.innerHTML = `
                <button class="submit-btn" type="button" onclick="goToResult()">See Result</button>
                <button class="secondary-btn" type="button" onclick="focusForAnswerChange()">Change Answers</button>
            `;
            banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function restorePredictionActions() {
            const actions = document.querySelector('.prediction-actions');
            actions.innerHTML = `
                <button class="submit-btn" type="button" onclick="continueAfterPrediction()">Continue Questions</button>
                <button class="secondary-btn" type="button" onclick="focusForAnswerChange()">Change Answers</button>
            `;
        }

        function continueAfterPrediction() {
            hidePredictionBanner();
            restorePredictionActions();
            loadQuestion();
        }

        function goToResult() {
            window.location.href = '/result?session_id=' + sessionId;
        }

        function focusForAnswerChange() {
            hidePredictionBanner();
            restorePredictionActions();
            const answered = document.querySelector('.question-card .edit-btn');
            if (answered) {
                answered.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        function startEdit(key) {
            hidePredictionBanner();
            fetch('/api/edit-start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ session_id: sessionId, key: key })
            }).then(r => r.json()).then(() => {
                pruneCardsAfter(key);
                editingKey = key;
                currentQuestionKey = key;
                const question = questionStore[key];
                replaceCard(question, answerStore[key], 'editing');
            });
        }

        function cancelEdit(key) {
            editingKey = null;
            replaceCard(questionStore[key], answerStore[key], 'answered');
            loadQuestion();
        }

        function lockCurrentQuestion(answer) {
            if (!currentQuestionKey || !questionStore[currentQuestionKey]) return;
            answerStore[currentQuestionKey] = answer;
            replaceCard(questionStore[currentQuestionKey], answer, 'answered');
        }

        function saveEditedAnswer(key, answer) {
            if (isSubmitting) return;
            isSubmitting = true;
            answerStore[key] = answer;
            fetch('/api/revise-answer', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sessionId,
                    key: key,
                    answer: answer
                })
            }).then(r => r.json()).then(data => {
                replaceCard(questionStore[key], answer, 'answered');
                editingKey = null;
                isSubmitting = false;
                if (data.status === 'predicted') {
                    showPredictionBanner(data.prediction);
                    return;
                }
                loadQuestion();
            }).catch(() => {
                isSubmitting = false;
                loadQuestion();
            });
        }

        function saveEditedText(key) {
            const active = document.querySelector('.question-section.editing[data-key="' + key + '"]');
            const input = active ? active.querySelector('input[type="text"]') : document.getElementById('text-answer-' + key);
            if (!input || !input.value.trim()) {
                alert('Please enter an answer');
                return;
            }
            saveEditedAnswer(key, input.value.trim());
        }

        function handleTextKeydown(event, key) {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            if (editingKey === key) {
                saveEditedText(key);
                return;
            }
            submitText();
        }

        function saveEditedMulti(key) {
            if (selectedOptions.length === 0) {
                alert('Please select at least one option');
                return;
            }
            saveEditedAnswer(key, [...selectedOptions]);
        }

        function loadQuestion() {
            fetch('/api/question?session_id=' + sessionId)
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'complete') {
                        showFinalResultBanner(data.result || null);
                        return;
                    }
                    if (data.status === 'error') {
                        document.getElementById('content').innerHTML = '<p style="color:red;">Error: ' + data.message + '</p>';
                        return;
                    }
                    document.getElementById('q-num').textContent = data.step;
                    setVisualProgress(data.step);
                    appendQuestionCard(data);
                    selectedOptions = [];
                    isSubmitting = false;
                })
                .catch(err => {
                    document.getElementById('content').innerHTML = '<p style="color:red;">Error loading question. Please refresh.</p>';
                    isSubmitting = false;
                });
        }

        function submitAnswer(answer) {
            if (isSubmitting) return;
            isSubmitting = true;
            hidePredictionBanner();
            const finalAnswer = Array.isArray(answer) ? [...answer] : answer;
            answerStore[currentQuestionKey] = finalAnswer;
            lockCurrentQuestion(finalAnswer);

            fetch('/api/answer', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sessionId,
                    key: currentQuestionKey,
                    answer: finalAnswer
                })
            }).then(r => r.json()).then(data => {
                isSubmitting = false;
                if (data.status === 'predicted') {
                    showPredictionBanner(data.prediction);
                    return;
                }
                loadQuestion();
            }).catch(() => {
                isSubmitting = false;
                loadQuestion();
            });
        }

        function submitText() {
            const active = getActiveQuestionSection();
            const input = active ? active.querySelector('input[type="text"]') : null;
            if (input && input.value.trim()) {
                submitAnswer(input.value.trim());
            } else {
                alert('Please enter an answer');
            }
        }

        function toggleCheckbox(option, checkbox) {
            const label = checkbox.parentElement;
            if (checkbox.checked) {
                label.classList.add('checked');
                if (!selectedOptions.includes(option)) {
                    selectedOptions.push(option);
                }
            } else {
                label.classList.remove('checked');
                selectedOptions = selectedOptions.filter(o => o !== option);
            }
        }

        function submitMultiSelect() {
            if (selectedOptions.length === 0) {
                alert('Please select at least one option');
                return;
            }
            submitAnswer(selectedOptions);
        }

        loadQuestion();
    </script>
</body>
</html>
"""

RESULT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diagnosis Result - Medical Expert System</title>
    <style>
        :root {
            --bg-1: #edf7ff;
            --bg-2: #f8fcff;
            --card: #ffffff;
            --ink: #0f172a;
            --muted: #516277;
            --line: #d9e5f2;
            --primary: #13578f;
            --primary-2: #2a79bf;
            --success: #0f766e;
            --warn-bg: #fff8e8;
            --warn-line: #ffd48f;
            --warn-ink: #7b4b00;
            --shadow-lg: 0 24px 54px rgba(19, 87, 143, 0.14);
            --shadow-sm: 0 12px 26px rgba(19, 87, 143, 0.12);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 12% 4%, rgba(42,121,191,0.15), transparent 38%),
                radial-gradient(circle at 88% 96%, rgba(15,118,110,0.12), transparent 40%),
                linear-gradient(165deg, var(--bg-1) 0%, var(--bg-2) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            width: 100%;
            max-width: 980px;
            margin: 0 auto;
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
        }
        .header {
            padding: 22px;
            background: linear-gradient(130deg, var(--primary) 0%, var(--primary-2) 62%, #0f766e 100%);
            color: #fff;
        }
        .header h1 {
            font-size: clamp(1.4rem, 2.4vw, 1.95rem);
            line-height: 1.2;
            margin-bottom: 6px;
        }
        .header p {
            opacity: 0.93;
            font-size: 0.95rem;
            line-height: 1.45;
        }
        .content {
            padding: 30px 24px 34px;
            display: grid;
            gap: 18px;
            min-height: 68vh;
            align-content: center;
        }
        .diagnosis-box {
            background: linear-gradient(180deg, #f8fbff 0%, #f3f9ff 100%);
            border: 1px solid #d2e6f8;
            border-left: 5px solid var(--primary-2);
            border-radius: 18px;
            padding: 24px;
            max-width: 760px;
            margin: 0 auto;
            width: 100%;
            box-shadow: var(--shadow-sm);
        }
        .diagnosis-title {
            font-size: clamp(1.55rem, 3vw, 2.15rem);
            color: var(--primary);
            font-weight: 700;
            line-height: 1.35;
            margin-bottom: 16px;
            text-align: center;
        }
        .symptoms-list {
            background: #fff;
            border: 1px solid #e2edf8;
            border-radius: 14px;
            padding: 16px;
        }
        .symptoms-list h4 {
            font-size: 0.95rem;
            margin-bottom: 8px;
            color: var(--ink);
        }
        .symptoms-list ul {
            list-style: none;
            display: grid;
            gap: 7px;
        }
        .symptoms-list li {
            position: relative;
            padding-left: 20px;
            color: var(--muted);
            line-height: 1.45;
            font-size: 0.94rem;
        }
        .symptoms-list li:before {
            content: "";
            position: absolute;
            left: 0;
            top: 8px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
        }
        .actions {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            max-width: 760px;
            width: 100%;
            margin: 0 auto;
        }
        .action-btn {
            padding: 13px 16px;
            border: none;
            border-radius: 11px;
            font-size: 0.95rem;
            font-weight: 700;
            text-decoration: none;
            text-align: center;
            color: #fff;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .treatment-btn { background: linear-gradient(130deg, #0f766e 0%, #0d9488 100%); }
        .restart-btn { background: linear-gradient(130deg, var(--primary) 0%, var(--primary-2) 100%); }
        .action-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-sm);
        }
        .disclaimer {
            background: var(--warn-bg);
            border: 1px solid var(--warn-line);
            border-radius: 12px;
            padding: 12px 14px;
            color: var(--warn-ink);
            font-size: 0.88rem;
            line-height: 1.5;
            max-width: 760px;
            width: 100%;
            margin: 0 auto;
        }
        .no-match {
            border: 1px solid #dbe8f5;
            border-radius: 14px;
            padding: 20px;
            text-align: center;
            background: #fbfdff;
        }
        .no-match h3 {
            color: var(--primary);
            margin-bottom: 8px;
        }
        .no-match p {
            color: var(--muted);
            line-height: 1.5;
        }
        @media (max-width: 700px) {
            body { padding: 14px; }
            .content { padding: 16px; }
            .actions { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Diagnosis Result</h1>
            <p>Review your likely match and next action references.</p>
        </div>

        <div class="content">
            {% if result and result.disease %}
            <div class="diagnosis-box">
                <div class="diagnosis-title">Likely condition: {{ result.disease }}</div>
                <div class="symptoms-list">
                    <h4>Matched symptoms</h4>
                    <ul>
                        {% for symptom in result.symptoms %}
                        <li>{{ symptom }}</li>
                        {% endfor %}
                    </ul>
                </div>
            </div>

            <div class="actions">
                <a href="{{ treatment_url }}" target="_blank" class="action-btn treatment-btn">View Treatment Info</a>
                <a href="{{ pdf_url }}" class="action-btn restart-btn">Download PDF</a>
                <a href="/" class="action-btn restart-btn">Start New Diagnosis</a>
            </div>
            {% else %}
            <div class="no-match">
                <h3>No Clear Diagnosis</h3>
                <p>The provided symptoms did not match a disease in the current database.</p>
                <p style="margin-top: 14px;">
                    <a href="/" class="action-btn restart-btn" style="display: inline-block; min-width: 220px;">Try Again</a>
                </p>
            </div>
            {% endif %}

            <div class="disclaimer">
                <strong>Medical Disclaimer:</strong> This expert system is for educational purposes only. It is not a substitute for professional medical advice.
            </div>
        </div>
    </div>
</body>
</html>
"""

TREATMENT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ disease }} - Treatment Reference</title>
    <style>
        :root {
            --bg-1: #edf7ff;
            --bg-2: #f8fcff;
            --card: #ffffff;
            --ink: #102033;
            --muted: #516277;
            --line: #d8e5f1;
            --primary: #13578f;
            --primary-2: #2a79bf;
            --accent: #0f766e;
            --shadow-lg: 0 24px 54px rgba(19, 87, 143, 0.14);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 5%, rgba(42,121,191,0.14), transparent 38%),
                radial-gradient(circle at 90% 95%, rgba(15,118,110,0.12), transparent 40%),
                linear-gradient(165deg, var(--bg-1) 0%, var(--bg-2) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1040px;
            margin: 0 auto;
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 18px 22px;
            background: linear-gradient(130deg, var(--primary) 0%, var(--primary-2) 62%, var(--accent) 100%);
            color: white;
        }
        .topbar h1 {
            font-size: clamp(1.35rem, 2.6vw, 1.9rem);
            line-height: 1.2;
        }
        .topbar p {
            font-size: 0.93rem;
            opacity: 0.94;
            margin-top: 4px;
        }
        .actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .action-btn {
            padding: 11px 14px;
            border-radius: 11px;
            text-decoration: none;
            color: white;
            font-weight: 700;
            font-size: 0.93rem;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(255,255,255,0.18);
        }
        .action-btn.secondary {
            background: rgba(10, 29, 53, 0.2);
        }
        .content {
            padding: 24px;
        }
        .article {
            background: #fff;
            border: 1px solid #e2edf8;
            border-radius: 16px;
            padding: 22px;
            line-height: 1.7;
            color: #1b2a3b;
        }
        .article h1, .article h2, .article h3 {
            color: var(--primary);
            margin: 18px 0 10px;
        }
        .article p, .article ul, .article ol {
            margin: 0 0 14px;
        }
        @media (max-width: 700px) {
            body { padding: 12px; }
            .topbar { align-items: flex-start; flex-direction: column; }
            .content { padding: 16px; }
            .article { padding: 16px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar">
            <div>
                <h1>{{ disease }}</h1>
                <p>Know more about diagnosis, treatment options, and prevention.</p>
            </div>
            <div class="actions">
                <a href="{{ pdf_url }}" class="action-btn">Download PDF</a>
                <a href="/" class="action-btn secondary">Back Home</a>
            </div>
        </div>
        <div class="content">
            <div class="article">{{ content|safe }}</div>
        </div>
    </div>
</body>
</html>
"""

PDF_PRINT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        @page {
            size: A4;
            margin: 18mm;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: #14263a;
            background: #ffffff;
        }
        .page {
            width: 100%;
        }
        .hero {
            padding: 22px 24px;
            border-radius: 18px;
            background: linear-gradient(130deg, #13578f 0%, #2a79bf 60%, #0f766e 100%);
            color: white;
            margin-bottom: 18px;
        }
        .hero h1 {
            margin: 0;
            font-size: 28px;
            line-height: 1.15;
        }
        .hero p {
            margin: 8px 0 0;
            font-size: 14px;
            opacity: 0.95;
        }
        .content {
            border: 1px solid #dbe8f4;
            border-radius: 16px;
            padding: 24px;
            background: #ffffff;
        }
        .summary {
            border: 1px solid #dbe8f4;
            border-radius: 16px;
            padding: 18px 20px;
            background: #f7fbff;
            margin-bottom: 16px;
        }
        .summary h2 {
            margin: 0 0 10px;
            color: #13578f;
            font-size: 18px;
        }
        .summary p, .summary li {
            font-size: 13px;
            line-height: 1.65;
            color: #203245;
        }
        .summary ul {
            margin: 8px 0 0;
            padding-left: 20px;
        }
        .content h1, .content h2, .content h3 {
            color: #13578f;
            break-after: avoid;
        }
        .content p, .content li {
            font-size: 13px;
            line-height: 1.7;
            color: #203245;
        }
        .content ul, .content ol {
            padding-left: 22px;
        }
        .footer-note {
            margin-top: 16px;
            padding: 12px 14px;
            border-radius: 12px;
            background: #fff8e8;
            border: 1px solid #ffd48f;
            color: #7b4b00;
            font-size: 12px;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="page">
        <div class="hero">
            <h1>{{ title }}</h1>
            <p>Medical Expert System disease reference</p>
        </div>
        {% if summary_html %}
        <div class="summary">{{ summary_html|safe }}</div>
        {% endif %}
        <div class="content">{{ content|safe }}</div>
        <div class="footer-note">
            This document is for educational use only and does not replace professional medical advice.
        </div>
    </div>
</body>
</html>
"""

# ============================================================
# FLASK ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template_string(MAIN_PAGE)

@app.route('/diagnosis')
def diagnosis():
    session_id = str(uuid.uuid4())
    sessions[session_id] = DiagnosisFlow()
    return render_template_string(DIAGNOSIS_PAGE, session_id=session_id)

@app.route('/api/question')
def get_question():
    session_id = request.args.get('session_id')

    if not session_id or session_id not in sessions:
        return jsonify({'status': 'error', 'message': 'Invalid session'})

    flow = sessions[session_id]
    question = flow.get_current_question()

    if not question:
        # Run diagnosis
        disease, symptoms = flow.run_diagnosis()
        sessions[session_id].result = {'disease': disease, 'symptoms': symptoms}
        return jsonify({
            'status': 'complete',
            'result': {
                'disease': disease,
                'symptoms': symptoms
            }
        })

    # Generate HTML for the question
    question_html = ''

    if question['type'] == 'text':
        question_html = f'''
        <div class="question-section">
            <div class="question">{question["question"]}</div>
            <input type="text" class="text-input" id="text-answer" placeholder="Type your answer..." autofocus>
            <button class="submit-btn" onclick="submitText()">Continue</button>
        </div>
        '''

    elif question['type'] == 'yesno':
        question_html = f'''
        <div class="question-section">
            <div class="question">{question["question"]}</div>
            <div class="yes-no-buttons">
                <button class="yes-btn" onclick="submitAnswer('yes')">Yes</button>
                <button class="no-btn" onclick="submitAnswer('no')">No</button>
            </div>
        </div>
        '''

    elif question['type'] == 'select':
        options_html = ''.join([
            f'<button class="option-btn" onclick=\'submitAnswer({json.dumps(opt)})\'>{html.escape(opt)}</button>'
            for opt in question['options']
        ])
        question_html = f'''
        <div class="question-section">
            <div class="question">{question["question"]}</div>
            <div class="options">
                {options_html}
            </div>
        </div>
        '''

    elif question['type'] == 'multi':
        options_html = ''.join([
            f'''
            <label class="checkbox-label">
                <input type="checkbox" onchange='toggleCheckbox({json.dumps(opt)}, this)'>
                <span>{html.escape(opt)}</span>
            </label>
            '''
            for opt in question['options']
        ])
        question_html = f'''
        <div class="question-section">
            <div class="question">{question["question"]}</div>
            <div class="checkbox-group">
                {options_html}
            </div>
            <button class="submit-btn" onclick="submitMultiSelect()">Continue</button>
        </div>
        '''

    return jsonify({
        'status': 'question',
        'step': len(flow.answers) + 1,
        'html': question_html,
        'key': question.get('key', ''),
        'question': question
    })

@app.route('/api/answer', methods=['POST'])
def submit_answer():
    data = request.json
    session_id = data.get('session_id')
    key = data.get('key')
    answer = data.get('answer')

    if session_id in sessions:
        flow = sessions[session_id]
        if key:
            flow.submit_answer(key, answer)
            disease, symptoms = diagnose_from_answers(flow.answers)
            if disease and flow.prediction_prompted != disease:
                flow.prediction_prompted = disease
                return jsonify({
                    'status': 'predicted',
                    'prediction': {
                        'disease': disease,
                        'symptoms': symptoms
                    }
                })
            flow.prediction_prompted = disease

    return jsonify({'status': 'ok'})

@app.route('/api/edit-start', methods=['POST'])
def edit_start():
    data = request.json
    session_id = data.get('session_id')
    key = data.get('key')

    if session_id in sessions and key:
        sessions[session_id].start_edit(key)
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'error', 'message': 'Invalid session or key'}), 400

@app.route('/api/revise-answer', methods=['POST'])
def revise_answer():
    data = request.json
    session_id = data.get('session_id')
    key = data.get('key')
    answer = data.get('answer')

    if session_id in sessions and key:
        flow = sessions[session_id]
        flow.revise_answer(key, answer)
        disease, symptoms = diagnose_from_answers(flow.answers)
        if disease and flow.prediction_prompted != disease:
            flow.prediction_prompted = disease
            return jsonify({
                'status': 'predicted',
                'prediction': {
                    'disease': disease,
                    'symptoms': symptoms
                }
            })
        flow.prediction_prompted = disease
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'error', 'message': 'Invalid session or key'}), 400

@app.route('/result')
def result():
    session_id = request.args.get('session_id')

    if session_id in sessions:
        flow = sessions[session_id]
        result_data = flow.result

        treatment_url = ''
        if result_data and result_data.get('disease'):
            disease = result_data['disease']
            if get_disease_content(disease):
                treatment_url = url_for('treatment_info', disease=disease, session_id=session_id)
            pdf_url = url_for('download_disease_pdf', disease=disease, session_id=session_id)
        else:
            pdf_url = ''

        return render_template_string(RESULT_PAGE,
            result=result_data,
            treatment_url=treatment_url,
            pdf_url=pdf_url
        )

    return render_template_string(RESULT_PAGE, result=None, pdf_url='', treatment_url='')

@app.route('/treatment-info/<path:disease>')
def treatment_info(disease):
    content = get_disease_content(disease)
    if not content:
        abort(404)
    session_id = request.args.get('session_id', '')
    return render_template_string(
        TREATMENT_PAGE,
        disease=disease,
        pdf_url=url_for('download_disease_pdf', disease=disease, session_id=session_id) if session_id else url_for('download_disease_pdf', disease=disease),
        content=content
    )

@app.route('/treatment/<path:filename>')
def treatment_file(filename):
    file_path = get_treatment_html_path(filename)
    if not file_path:
        abort(404)
    disease = Path(filename).stem
    content = extract_treatment_body(file_path.read_text(encoding='utf-8', errors='ignore'))
    session_id = request.args.get('session_id', '')
    return render_template_string(
        TREATMENT_PAGE,
        disease=disease,
        pdf_url=url_for('download_disease_pdf', disease=disease, session_id=session_id) if session_id else url_for('download_disease_pdf', disease=disease),
        content=content
    )


@app.route('/download-pdf/<path:disease>')
def download_disease_pdf(disease):
    content = get_disease_content(disease)
    if not content:
        abort(404)
    session_id = request.args.get('session_id', '')
    summary_html = ''

    if session_id and session_id in sessions:
        flow = sessions[session_id]
        patient_name = flow.answers.get('name', '').strip()
        symptoms = []
        if flow.result and flow.result.get('symptoms'):
            symptoms = flow.result.get('symptoms', [])

        summary_parts = ['<h2>Patient Summary</h2>']
        if patient_name:
            summary_parts.append(f'<p><strong>Patient name:</strong> {html.escape(patient_name)}</p>')
        summary_parts.append(f'<p><strong>Predicted disease:</strong> {html.escape(disease)}</p>')
        if symptoms:
            summary_parts.append('<p><strong>Matching symptoms:</strong></p>')
            summary_parts.append('<ul>')
            summary_parts.extend(f'<li>{html.escape(symptom)}</li>' for symptom in symptoms)
            summary_parts.append('</ul>')
        summary_html = ''.join(summary_parts)

    pdf_buffer = build_browser_pdf(f"{disease} Reference", content, summary_html=summary_html)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{disease}.pdf",
        mimetype="application/pdf"
    )

# ============================================================
# MAIN
# ============================================================

def open_browser():
    """Open browser after server starts"""
    time.sleep(2)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("=" * 60)
    print("MEDICAL EXPERT SYSTEM - WEB VERSION")
    print("=" * 60)
    print()
    print("Starting local web server...")
    print()
    print("The application will open in your default browser.")
    print()
    print("If it doesn't open automatically, go to:")
    print("http://localhost:5000")
    print()
    print("Press Ctrl+C to stop the server.")
    print("=" * 60)

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000)
