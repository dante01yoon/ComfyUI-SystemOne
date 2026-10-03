"""Queue an API-format example once per prompt and print each System One preview and saved image."""
import argparse
import copy
import json
import time
import urllib.request


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def run(base, workflow, timeout=600):
    prompt_id = call(base, "/prompt", {"prompt": workflow})["prompt_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        entry = call(base, f"/history/{prompt_id}").get(prompt_id)
        if entry and entry["status"].get("completed") is not None:
            return entry
        time.sleep(0.5)
    raise TimeoutError(prompt_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow")
    parser.add_argument("--prompt-node", required=True)
    parser.add_argument("--prompts", nargs="+", required=True)
    parser.add_argument("--set", action="append", default=[], help="node.input=json overrides")
    parser.add_argument("--base", default="http://127.0.0.1:8199")
    args = parser.parse_args()
    template = json.load(open(args.workflow))
    for override in args.set:
        target, value = override.split("=", 1)
        node, field = target.split(".")
        template[node]["inputs"][field] = json.loads(value)
    for text in args.prompts:
        workflow = copy.deepcopy(template)
        workflow[args.prompt_node]["inputs"]["value"] = text
        started = time.time()
        entry = run(args.base, workflow)
        print(f"=== {text}  [{entry['status']['status_str']}, {time.time() - started:.1f}s]")
        for node_id, output in entry["outputs"].items():
            for line in output.get("text", []):
                print(f"[{workflow[node_id]['class_type']}]\n{line}")
            for image in output.get("images", []):
                print(f"image: {image['subfolder']}/{image['filename']}")


if __name__ == "__main__":
    main()
