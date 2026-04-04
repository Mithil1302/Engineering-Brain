#!/usr/bin/env python3
"""KA-CHOW CLI client. Streams Q&A responses to terminal with ANSI colors."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

CONFIG_PATH = Path.home() / ".kachow" / "config.json"
SESSION_PATH = Path.home() / ".kachow" / "session"

# ANSI color codes
ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[2m"      # citations
ANSI_CYAN = "\033[36m"    # follow-ups


def load_config() -> dict:
    """Load configuration from ~/.kachow/config.json."""
    if not CONFIG_PATH.exists():
        print("Error: ~/.kachow/config.json not found", file=sys.stderr)
        print("Create it with: {\"api_url\": \"...\", \"token\": \"...\", "
              "\"default_repo\": \"org/repo\"}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_session_id() -> str:
    """Load session ID from ~/.kachow/session or generate new one.
    
    Subtask 11.3.2: Validates that file content is non-empty after .strip()
    before returning. A blank file generates a new UUID.
    """
    if SESSION_PATH.exists():
        session_id = SESSION_PATH.read_text().strip()
        if session_id:  # 11.3.2: validate non-empty after strip
            return session_id
    # Generate new session_id if file doesn't exist or is blank
    session_id = str(uuid.uuid4())
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(session_id)
    return session_id


def print_dim(text: str) -> None:
    """Print text in dim ANSI color."""
    print(f"{ANSI_DIM}{text}{ANSI_RESET}")


def print_cyan(text: str) -> None:
    """Print text in cyan ANSI color."""
    print(f"{ANSI_CYAN}{text}{ANSI_RESET}")


async def ask(question: str, config: dict, session_id: str) -> None:
    """Send question and stream response to stdout.
    
    Implements SSE parsing with proper buffer handling for partial chunks.
    """
    url = f"{config['api_url'].rstrip('/')}/adapters/cli/ask"
    headers = {
        "Authorization": f"Bearer {config['token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "question": question,
        "repo": config.get("default_repo", ""),
        "session_id": session_id,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        async with client.stream("POST", url, json=payload,
                                  headers=headers) as response:
            # 11.3.9: Check 401 BEFORE raise_for_status for clear error message
            if response.status_code == 401:
                print("Error: invalid token", file=sys.stderr)
                sys.exit(1)
            response.raise_for_status()

            buffer = ""
            follow_ups = []

            async for chunk in response.aiter_text():
                # 11.3.3: SSE parsing with buffer accumulation
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    if not event_str.startswith("data: "):
                        continue
                    raw = event_str[6:]
                    
                    # 11.3.5: Check [DONE] BEFORE json.loads
                    if raw == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if data["type"] == "error":
                        print(f"\nError: {data.get('message')}", file=sys.stderr)
                        return

                    elif data["type"] == "token":
                        # 11.3.4: flush=True for progressive terminal output
                        print(data["text"], end="", flush=True)

                    elif data["type"] == "metadata":
                        print()  # newline after last token
                        # Citations (dim)
                        citations = data.get("citations", [])
                        if citations:
                            print()
                            print_dim("Sources:")
                            for c in citations:
                                print_dim(f"  {c.get('display', c.get('source_ref', ''))}")
                        # Follow-ups (cyan)
                        follow_ups = data.get("follow_ups", [])
                        if follow_ups:
                            print()
                            print_cyan("Suggested follow-ups:")
                            for i, q in enumerate(follow_ups, 1):
                                print_cyan(f"  {i}. {q}")

            # Interactive follow-up selection
            if follow_ups:
                try:
                    choice = input(
                        f"\nSelect (1-{len(follow_ups)}) or press Enter to skip: "
                    ).strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(follow_ups):
                            selected = follow_ups[idx]
                            print(f"\n> {selected}\n")
                            # 11.3.7: Recursive call with SAME session_id
                            await ask(selected, config, session_id)
                except EOFError:
                    # 11.3.6: Handle piped input mode
                    pass


def main() -> None:
    """Main entry point for CLI client."""
    try:
        config = load_config()
        session_id = load_session_id()

        if len(sys.argv) < 2:
            print("Usage: kachow <question>", file=sys.stderr)
            print("       kachow \"What does the payments service do?\"", file=sys.stderr)
            sys.exit(1)

        question = " ".join(sys.argv[1:])
        print()  # blank line before answer
        asyncio.run(ask(question, config, session_id))

    except KeyboardInterrupt:
        # 11.3.8: Clean newline then exit code 0 for intentional stop
        print()
        sys.exit(0)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
