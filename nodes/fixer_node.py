# node_fixer_advanced.py – LangGraph Node 1 with procedural memory and robust fix logic

import os
import re
import shutil
import hashlib
from datetime import datetime
from typing import Dict, List, Set, Tuple
import google.generativeai as genai

# === Gemini Configuration ===
genai.configure(api_key=os.getenv("GEMINI_API_KEY", "AIzaSyDt-QChgdH6i64MACm1vvROAFHqBIOo-30"))
model = genai.GenerativeModel(
    "gemini-2.0-flash-exp",
    generation_config={
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 2000,
    },
)

HASH_ALGO = hashlib.md5

def md5(text: str) -> str:
    return HASH_ALGO(text.encode()).hexdigest()

def create_backup(file_path: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path

def find_error_log(start_dir: str) -> str:
    for root, _, files in os.walk(start_dir):
        if "error.log" in files:
            return os.path.join(root, "error.log")
        elif "customs-engine.log" in files:
            return os.path.join(root, "customs-engine.log")
    raise FileNotFoundError("Could not locate error.log in the project directory.")

def find_all_java_files(project_dir: str) -> List[str]:
    for root, _, files in os.walk(project_dir):
        for file in files:
            if file.endswith(".java"):
                yield os.path.join(root, file)

CLASS_RE = re.compile(r"\bclass\s+(\w+)")
IMPORT_RE = re.compile(r"^import\s+([\w\.]+)\s*;", re.MULTILINE)
CALL_RE = re.compile(r"new\s+(\w+)\(|(\w+)\.")

def build_file_entry(file_path: str) -> Dict:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    class_match = CLASS_RE.search(content)
    class_name = class_match.group(1) if class_match else os.path.splitext(os.path.basename(file_path))[0]
    imported = IMPORT_RE.findall(content)
    called_raw = CALL_RE.findall(content)
    called = [c[0] or c[1] for c in called_raw if (c[0] or c[1])]
    return {
        "path": file_path,
        "content": content,
        "class": class_name,
        "imports": imported,
        "calls": called,
        "last_modified": os.path.getmtime(file_path),
        "checksum": md5(content),
    }

def build_file_index(project_dir: str) -> Dict[str, Dict]:
    return {os.path.basename(fp): build_file_entry(fp) for fp in find_all_java_files(project_dir)}

def refresh_file_index(file_index: Dict[str, Dict]) -> Dict[str, Dict]:
    for filename, info in list(file_index.items()):
        path = info["path"]
        if not os.path.exists(path):
            del file_index[filename]
            continue
        mtime = os.path.getmtime(path)
        if mtime != info["last_modified"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            checksum = md5(content)
            if checksum != info["checksum"]:
                file_index[filename] = build_file_entry(path)
    return file_index

STACK_TRACE_RE = re.compile(r"\bat\s+[\w\.$]+\((\w+\.java):\d+\)")

def extract_filenames_from_error(error_text: str) -> Set[str]:
    return set(STACK_TRACE_RE.findall(error_text))

def fan_out(files: Set[str], file_index: Dict[str, Dict], depth: int = 1) -> Set[str]:
    expanded = set(files)
    frontier = set(files)
    for _ in range(depth):
        next_frontier = set()
        for fname in frontier:
            info = file_index.get(fname)
            if not info:
                continue
            for neighbor_class in info["imports"] + info["calls"]:
                neighbor_file = f"{neighbor_class}.java" if not neighbor_class.endswith(".java") else neighbor_class
                if neighbor_file in file_index and neighbor_file not in expanded:
                    next_frontier.add(neighbor_file)
        frontier = next_frontier
        expanded.update(frontier)
    return expanded

def get_relevant_files(error_text: str, file_index: Dict[str, Dict], depth: int = 2) -> Dict[str, Dict]:
    initial = extract_filenames_from_error(error_text)
    if not initial:
        return file_index
    selected_names = fan_out(initial, file_index, depth)
    return {name: file_index[name] for name in selected_names if name in file_index}

def extract_code_context(source_files: Dict[str, Dict]) -> str:
    out = []
    for filename, info in source_files.items():
        out.append(f"\n--- {filename} ---\n{info['content']}")
    return "".join(out)

def apply_fixes_to_code(response_text: str, source_files: Dict[str, Dict], file_index: Dict[str, Dict]):
    print("\n" + "=" * 60)
    print("GEMINI ANALYSIS & FIXES:")
    print("=" * 60)
    print(response_text.strip())

    response_lines = response_text.split("\n")
    current_filename = None
    i = 0
    while i < len(response_lines):
        line = response_lines[i].strip()

        if line.startswith("FILENAME:") or line.endswith(".java"):
            current_filename = line.split(":", 1)[-1].strip() if ":" in line else line
            print(f"\n🔧 Processing: {current_filename}")
            i += 1
            continue

        if line.startswith("```java") or line.startswith("```"):
            if current_filename is None:
                print("⚠️ Code block without a filename — skipping.")
                i += 1
                continue

            suggested_basename = os.path.basename(current_filename)
            matched_key = next(
                (k for k in source_files if os.path.basename(k).lower() == suggested_basename.lower()),
                None
            )

            i += 1
            code_lines = []
            while i < len(response_lines) and not response_lines[i].strip().startswith("```"):
                code_lines.append(response_lines[i])
                i += 1
            fixed_code = "\n".join(code_lines)

            if matched_key:
                file_path = source_files[matched_key]["path"]
                print(f"[DEBUG] New code preview (first 300 chars):\n{fixed_code[:300]}")
                create_backup(file_path)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                file_index[matched_key] = {
                    **file_index[matched_key],
                    "content": fixed_code,
                    "last_modified": os.path.getmtime(file_path),
                    "checksum": md5(fixed_code),
                }
                print(f"✅ Fixed: {file_path}")
            else:
                print(f"⚠️ Gemini suggested unknown file: {current_filename} — Skipping.")

            current_filename = None  # reset after processing

        i += 1

def node_fixer(state: Dict) -> Dict:
    print("🔧 [Node 1] Running Gemini fixer…")

    start_dir = state.get("springboot_path", os.getcwd())
    repo_url = state.get("repo_url", "https://github.com/Shivanshvohra/springboot-ai-fixer-test")

    error_log_path = find_error_log(start_dir)
    with open(error_log_path, "r", encoding="utf-8", errors="ignore") as f:
        error_log = f.read()
    error_log = error_log[-5000:]

    project_dir = error_log_path
    for _ in range(10):
        project_dir = os.path.dirname(project_dir)
        if os.path.exists(os.path.join(project_dir, "src")) or os.path.exists(os.path.join(project_dir, "pom.xml")):
            break


    file_index = state.get("file_index")
    if file_index is None:
        file_index = build_file_index(project_dir)
    else:
        file_index = refresh_file_index(file_index)
    state["file_index"] = file_index

    relevant_files = get_relevant_files(error_log, file_index, depth=2)

    extra_note = (
        f"\nNOTE FROM VALIDATION AGENT:Previous fix was rejected during automated testing.You MUST address this feedback.\n{state['test_failure_reason']}\n"
        if "test_failure_reason" in state else ""
    )

    prompt = f"""SPRING BOOT ERROR ANALYSIS AND AUTO‑FIX

{extra_note}
ERROR LOG:
{error_log}

SOURCE CODE:
{extract_code_context(relevant_files)}

TASK: Analyze the error and provide FIXED CODE for each problematic file.

REQUIREMENTS:
- Reflect on why the previous fix failed (if any).
- Identify the exact root cause based on the latest error message.
- Only modify files listed in the SOURCE CODE section. Do not suggest new filenames.
- Provide complete, compilable code for each changed file.
- Use proper Spring Boot annotations and best practices.
- Ensure all necessary imports are included.
- Preserve the API contract; validate or handle bad input instead of changing types.
- If you must add an exception handler, do so ONLY in GlobalExceptionHandler.java.
- DO NOT CREATE NEW FILES.
- Format each fix exactly as:

FILENAME: [filename]
```java
[complete corrected code]

"""

    chat = model.start_chat()
    print(extra_note)
    response = chat.send_message(prompt)
    apply_fixes_to_code(response.text, relevant_files, file_index)

    if "original_code_backup" not in state:
        state["original_code_backup"] = {
            fname: info["content"] for fname, info in file_index.items()
        }
        state["original_code_path_map"] = {
            fname: info["path"] for fname, info in file_index.items()
        }

    state["relevant_files"] = {
        fname: file_index[fname] for fname in relevant_files
    }

    state.update(
        {
            "repo_url": repo_url,
            "branch_name": f"auto-fix-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "commit_message": "Auto fix: Resolved errors from error.log",
            "local_repo_path": project_dir,
            "original_code": "\n\n".join(
                f"// FILE: {fname}\n{code}" for fname, code in state["original_code_backup"].items()
            ),
            "fixed_code": "\n\n".join(
                f"// FILE: {fname}\n{file_index[fname]['content']}"
                for fname in file_index if fname in state["original_code_backup"]
            ),
            "original_error": error_log,
        }
    )
    return state
