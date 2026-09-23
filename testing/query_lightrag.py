#!/usr/bin/env python3
"""
query_lightrag.py

Evaluates LightRAG on multiple-choice questions from parsed_questions.json.
Uses an AI agent querying a LightRAG server using prompt.txt as instructions.
Grades responses as:
  1: Correct answer (matches single letter option)
  0: Wrong answer (single letter option that does not match)
 -1: Agent unable to find information, not confident, or returned non-single letter answer (e.g. 'sorry i cant help', '-1')

Saves results to a JSON file containing the question number and response status.
"""

import os
import sys
import json
import time
import argparse
import requests
from typing import Optional, Dict, Any, List, Tuple


def parse_args():
    parser = argparse.ArgumentParser(
        description="Query LightRAG server with multiple choice questions and evaluate single-letter responses."
    )
    parser.add_argument(
        "--questions-file", "-f",
        default="parsed_questions.json",
        help="Path to parsed questions JSON file (default: parsed_questions.json)"
    )
    parser.add_argument(
        "--prompt-file", "-p",
        default="prompt.txt",
        help="Path to prompt template file (default: prompt.txt)"
    )
    parser.add_argument(
        "--output-file", "-o",
        default="results.json",
        help="Path to output results JSON file (default: results.json)"
    )
    parser.add_argument(
        "--server-url", "-s",
        default=os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:9621/query"),
        help="LightRAG server query URL (default: http://localhost:9621/query or LIGHTRAG_SERVER_URL env var)"
    )
    parser.add_argument(
        "--mode", "-m",
        default="hybrid",
        choices=["hybrid", "local", "global", "naive", "mix"],
        help="LightRAG query retrieval mode (default: hybrid)"
    )
    parser.add_argument(
        "--api-key", "-k",
        default=os.getenv("LIGHTRAG_API_KEY", None),
        help="Optional API Key for LightRAG server (or LIGHTRAG_API_KEY env var)"
    )
    parser.add_argument(
        "--index", "-i",
        type=int,
        default=None,
        help="Evaluate a specific question by 1-based index in parsed_questions.json (1 to N)"
    )
    parser.add_argument(
        "--question-id", "-q",
        type=int,
        default=None,
        help="Evaluate question(s) matching this question id (e.g., -q 1)"
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=None,
        help="Start question 1-based index (inclusive)"
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=None,
        help="End question 1-based index (inclusive)"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of questions to evaluate"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for LightRAG server requests (default: 60)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between requests (default: 0.0)"
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Save only question_number and response_status in JSON (exclude debug fields)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict single-character evaluation (disable markdown/punctuation stripping)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file instead of merging with prior results"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock/offline mode without calling LightRAG server"
    )
    return parser.parse_args()


def load_prompt_template(prompt_path: str) -> str:
    """Loads prompt template from file, creating a default if missing."""
    if not os.path.exists(prompt_path):
        default_prompt = (
            "You are an AI assistant answering multiple-choice questions based strictly on the provided knowledge base.\n\n"
            "Question:\n{question}\n\n"
            "Options:\n{options}\n\n"
            "Instructions:\n"
            "1. Review the question and options above.\n"
            "2. If the relevant information is found in the knowledge base and you are confident in the answer, "
            "respond with ONLY the single uppercase letter of the correct option (e.g. A, B, C, or D). "
            "Do NOT include any explanations, surrounding text, markdown formatting, or punctuation.\n"
            "3. If the information is not in the knowledge base, or if you are not confident that you can answer the question correctly, "
            "respond with \"-1\" or \"sorry i cant help\"."
        )
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(default_prompt)
        print(f"Created default prompt template at {prompt_path}")
        return default_prompt

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def format_prompt(template: str, question: dict) -> str:
    """Formats the prompt with question text and options."""
    q_id = str(question.get("id", ""))
    q_text = str(question.get("question", "")).strip()
    options_dict = question.get("options", {})
    options_lines = [f"{k}. {v}" for k, v in sorted(options_dict.items())]
    options_text = "\n".join(options_lines)

    if "{question}" in template:
        res = template.replace("{question}", q_text)
        res = res.replace("{options}", options_text)
        res = res.replace("{id}", q_id)
        return res
    else:
        return (
            f"{template.strip()}\n\n"
            f"Question {q_id}: {q_text}\n"
            f"Options:\n{options_text}\n\n"
            f"Answer:"
        )


def query_lightrag(
    prompt: str,
    server_url: str,
    mode: str = "hybrid",
    api_key: Optional[str] = None,
    timeout: int = 60,
    mock: bool = False,
    mock_response: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Queries the LightRAG server.
    Returns (raw_response_text, error_message).
    """
    if mock:
        return mock_response or "B", None

    # Ensure URL ends with /query if host only
    url = server_url.rstrip("/")
    if not url.endswith("/query") and not url.endswith("/query/stream"):
        url = f"{url}/query"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "query": prompt,
        "mode": mode,
        "stream": False
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}: {resp.text}"

        try:
            data = resp.json()
            if isinstance(data, dict):
                # Standard LightRAG response is {"response": "..."}
                if "response" in data:
                    return str(data["response"]), None
                elif "data" in data:
                    return str(data["data"]), None
                elif "content" in data:
                    return str(data["content"]), None
                elif "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if isinstance(choice, dict):
                        if "message" in choice and "content" in choice["message"]:
                            return str(choice["message"]["content"]), None
                        if "text" in choice:
                            return str(choice["text"]), None
            return resp.text, None
        except ValueError:
            return resp.text, None

    except requests.exceptions.RequestException as e:
        return None, f"Request error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


def evaluate_response(
    raw_response: Optional[str],
    correct_answer: Optional[str],
    valid_options: List[str],
    strict: bool = False
) -> Tuple[int, str]:
    """
    Evaluates the response according to rules:
      1: true (correct single letter answer matching correct_answer)
      0: wrong (single letter answer that does not match correct_answer)
     -1: agent was unable to find info / not confident / non-single letter answer / error
    """
    if raw_response is None:
        return -1, ""

    text = str(raw_response).strip()
    if not text:
        return -1, ""

    # Explicit failure indicator or inability
    if text == "-1" or "sorry i cant help" in text.lower() or "sorry, i can't help" in text.lower():
        return -1, text

    if strict:
        candidate = text
    else:
        # Strip common markdown formatting (e.g. **A**, [A], `A`, "A") and trailing period
        candidate = text.strip('*_`\'"()[]{}').rstrip('.').strip()

    # Must be a single letter
    if len(candidate) == 1 and candidate.isalpha():
        letter = candidate.upper()
        # If valid options are specified, verify it's one of the options
        if valid_options and letter not in [opt.upper() for opt in valid_options]:
            return 0, letter

        if correct_answer:
            if letter == correct_answer.strip().upper():
                return 1, letter
            else:
                return 0, letter
        else:
            # If no ground truth answer exists for this question, cannot verify correctness
            return -1, letter

    # Non single-letter answer (explanation, conversational reply, or failure)
    return -1, text


def load_existing_results(output_file: str) -> Dict[int, Dict[str, Any]]:
    """Loads existing results from JSON to support incremental updates keyed by global index."""
    if not os.path.exists(output_file):
        return {}
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                result_map = {}
                for idx, item in enumerate(data, 1):
                    # Prefer explicit question_index if present, otherwise position in array
                    q_idx = item.get("question_index", idx)
                    result_map[int(q_idx)] = item
                return result_map
            elif isinstance(data, dict):
                return {int(k): v if isinstance(v, dict) else {"question_number": int(k), "response_status": v}
                        for k, v in data.items() if str(k).isdigit()}
    except Exception as e:
        print(f"Warning: Could not read existing results from {output_file}: {e}")
    return {}


def save_results(results_map: Dict[int, Dict[str, Any]], output_file: str):
    """Saves results ordered by question index."""
    sorted_results = [results_map[k] for k in sorted(results_map.keys())]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(sorted_results, f, indent=4)


def main():
    args = parse_args()

    # 1. Load questions
    if not os.path.exists(args.questions_file):
        print(f"Error: Questions file '{args.questions_file}' not found.")
        sys.exit(1)

    with open(args.questions_file, "r", encoding="utf-8") as f:
        all_questions = json.load(f)

    if not isinstance(all_questions, list):
        print("Error: Questions file must contain a JSON array of questions.")
        sys.exit(1)

    # Attach 1-based global index and filter
    questions_to_run = []
    for g_idx, q in enumerate(all_questions, 1):
        q_id = q.get("id")
        if q_id is None:
            continue
        if args.index is not None and g_idx != args.index:
            continue
        if args.question_id is not None and q_id != args.question_id:
            continue
        if args.start_index is not None and g_idx < args.start_index:
            continue
        if args.end_index is not None and g_idx > args.end_index:
            continue
        questions_to_run.append((g_idx, q))

    if args.limit is not None and args.limit > 0:
        questions_to_run = questions_to_run[:args.limit]

    if not questions_to_run:
        print("No questions matched the specified criteria.")
        sys.exit(0)

    # 2. Load prompt template
    prompt_template = load_prompt_template(args.prompt_file)

    # 3. Load or initialize results mapping
    results_map = {} if args.overwrite else load_existing_results(args.output_file)

    print(f"Starting LightRAG evaluation for {len(questions_to_run)} question(s)...")
    print(f"Server URL: {args.server_url} (mode: {args.mode})")
    print(f"Output File: {args.output_file}\n" + "-" * 60)

    counts = {1: 0, 0: 0, -1: 0}

    for idx, (g_idx, q) in enumerate(questions_to_run, 1):
        q_id = q.get("id")
        correct_answer = q.get("correct_answer")
        options = list(q.get("options", {}).keys())

        # Format prompt
        formatted_prompt = format_prompt(prompt_template, q)

        # Query LightRAG
        raw_response, err = query_lightrag(
            prompt=formatted_prompt,
            server_url=args.server_url,
            mode=args.mode,
            api_key=args.api_key,
            timeout=args.timeout,
            mock=args.mock
        )

        if err:
            print(f"[{idx}/{len(questions_to_run)}] [#{g_idx}] Q{q_id} Server Warning: {err}")

        # Evaluate response
        status, parsed_ans = evaluate_response(
            raw_response=raw_response,
            correct_answer=correct_answer,
            valid_options=options,
            strict=args.strict
        )
        counts[status] += 1

        # Format output record
        record: Dict[str, Any] = {
            "question_number": q_id,
            "response_status": status
        }
        if not args.compact:
            record["question_index"] = g_idx
            record["agent_response"] = raw_response.strip() if raw_response else None
            record["correct_answer"] = correct_answer

        results_map[g_idx] = record

        # Status text for console
        status_label = {1: "1 (TRUE)", 0: "0 (WRONG)", -1: "-1 (UNABLE/ERROR)"}[status]
        agent_display = f"'{parsed_ans}'" if parsed_ans else "(no answer)"
        print(f"[{idx}/{len(questions_to_run)}] [#{g_idx}] Q{q_id} -> Status: {status_label} | Agent: {agent_display} | Expected: '{correct_answer}'")

        # Save incrementally
        save_results(results_map, args.output_file)

        if args.delay > 0 and idx < len(questions_to_run):
            time.sleep(args.delay)

    # Print summary statistics
    total = len(questions_to_run)
    c1, c0, cm1 = counts[1], counts[0], counts[-1]
    answered = c1 + c0
    acc_answered = (c1 / answered * 100) if answered > 0 else 0.0
    acc_total = (c1 / total * 100) if total > 0 else 0.0

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print(f"Total Evaluated: {total}")
    print(f"  - Correct (1)             : {c1:4d} ({c1/total*100:5.1f}%)")
    print(f"  - Wrong   (0)             : {c0:4d} ({c0/total*100:5.1f}%)")
    print(f"  - Unable/Uncertain (-1)   : {cm1:4d} ({cm1/total*100:5.1f}%)")
    print(f"Accuracy on attempted questions (1 vs 0): {acc_answered:.1f}% ({c1}/{answered})")
    print(f"Overall accuracy (including -1 as miss) : {acc_total:.1f}% ({c1}/{total})")
    print(f"Results successfully saved to: {args.output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
