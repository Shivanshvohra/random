# nodes/commit_and_pr_node.py
import requests

def _commit_and_push(repo_url: str, branch_name: str, commit_message: str, local_repo_path: str) -> str:
    try:
        response = requests.post("http://localhost:8081/run", json={
            "repoUrl": repo_url,
            "branchName": branch_name,
            "commitMessage": commit_message,
            "local_repo_path": local_repo_path
        })
        if response.ok:
            return "✅ Commit and push completed successfully!"
        return f"❌ Spring Boot error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"❌ Exception during commit_and_push: {e}"

def _create_pull_request(title: str, body: str, base: str, head: str) -> str:
    try:
        response = requests.post("http://localhost:8081/create-pr", json={
            "title": title,
            "body": body,
            "base": base,
            "head": head
        })
        if response.ok:
            return "✅ Pull request created successfully!"
        return f"❌ Spring Boot error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"❌ Exception during create_pull_request: {e}"

def node_commit_and_pr(state: dict) -> dict:
    print("📦 [Node 2] Running commit_and_pr...")

    repo_url = state["repo_url"]
    branch_name = state["branch_name"]
    commit_message = state["commit_message"]
    local_repo_path = state["local_repo_path"]

    title = state.get("pr_title", "Auto Fix PR")
    body = state.get("pr_body", "This PR contains automated fixes.")
    base = state.get("base_branch", "main")
    head = branch_name

    commit_result = _commit_and_push(repo_url, branch_name, commit_message, local_repo_path)
    pr_result = _create_pull_request(title, body, base, head)

    state["commit_result"] = commit_result
    state["pr_result"] = pr_result
    return state
