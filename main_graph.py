from langgraph.graph import StateGraph, END
from nodes.fixer_node import node_fixer
from nodes.testing_node import testing_node
from nodes.commit_and_pr_node import node_commit_and_pr

def restore_original_code(state: dict):
    print("🧼 Restoring original code because max retries exceeded...")
    path_map = state.get("original_code_path_map", {})
    backup = state.get("original_code_backup", {})

    for filename, original_content in backup.items():
        abs_path = path_map.get(filename)
        if abs_path:
            try:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(original_content)
                print(f"✅ Restored: {filename}")
            except Exception as e:
                print(f"❌ Failed to restore {filename}: {e}")


def router(state: dict) -> str:
    if state.get("decision") == "DEPLOY":
        # return "commit_and_pr"
        return END
    elif state.get("decision") == "NEEDS_REVIEW":
        # return "commit_and_pr"
        return END
    elif state.get("retries", 0) >= 3:
        restore_original_code(state)
        print("🚫 Max retries reached. Ending pipeline.")
        return END
    else:
        state["retries"] = state.get("retries", 0) + 1
        print(f"🔁 Retry #{state['retries']} - Sending back to fixer")
        return "fix_code"

builder = StateGraph(dict)

builder.add_node("fix_code", node_fixer)
builder.add_node("test_code", testing_node)
# builder.add_node("commit_and_pr", node_commit_and_pr)

builder.set_entry_point("fix_code")
builder.add_edge("fix_code", "test_code")
builder.add_conditional_edges("test_code", router, {
    # "commit_and_pr": "commit_and_pr",
    "fix_code": "fix_code",
    END: END
})
# builder.add_edge("commit_and_pr", END)

app = builder.compile()

initial_state = {
    "springboot_path": "/Users/shivanshvohra/IdeaProjects/test-project-poc",
    "repo_url": "https://github.com/Shivanshvohra/springboot-ai-fixer-test",
    "retries": 1,
}
final_state = app.invoke(initial_state)
# print("🏁 Final state:")
# for k, v in final_state.items():
#     if k in ["original_code", "fixed_code", "file_index", "original_code_backup"]:
#         print(f"{k}: <redacted>")
#     else:
#         print(f"{k}: {v}")
