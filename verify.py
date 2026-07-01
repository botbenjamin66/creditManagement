VERIFY_TOOL = {
    "name": "submit_verification",
    "description": "Return your independent per-section audit of the analysis just submitted. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "One entry per analysis section you audited.",
                "items": {
                    "type": "object",
                    "properties": {
                        "section":    {"type": "string",
                                       "description": "The section key exactly as given (e.g. 'business_model', 'financials')."},
                        "verdict":    {"type": "string",
                                       "enum": ["supported", "partially_supported", "unsupported", "contradicted"],
                                       "description": "supported = key facts backed by a retrieved source / reference data; partially_supported = some claims grounded, some not; unsupported = central claims appear nowhere in what was actually retrieved; contradicted = a number conflicts with a source or the reference data."},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                                       "description": "Honest grounding: high only when anchored in disclosed figures, low when largely inferred."},
                        "issues":     {"type": "array", "items": {"type": "string"},
                                       "description": "The specific unsupported or contradicted claims (number + what is wrong). Empty list if none."},
                        "corrected_text": {"type": "string",
                                       "description": "ONLY if verdict is unsupported or contradicted: a corrected version of the section text that removes/repairs the bad claims and marks missing figures [Not public]. Keep the same length band and style. Empty string otherwise."},
                    },
                    "required": ["section", "verdict", "confidence", "issues"],
                },
            },
            "overall": {"type": "string",
                        "description": "One-line overall reliability verdict for the whole report."},
        },
        "required": ["findings"],
    },
}

VERIFY_PROMPT = """You now switch role. You are an independent, skeptical fact-checker reviewing the analysis you just submitted. You are NOT the author defending it — your job is to catch every unsupported or wrong claim before it reaches an investor.

You still have access above to every source you retrieved and to the VERIFIED REFERENCE DATA. Audit the analysis against ONLY that material. You may run up to a few web searches to settle a specific doubtful number, but do not invent new content.

For EVERY section of the analysis:
- Check each number (value, unit, year) and each named fact against the retrieved sources and the reference data.
- verdict = supported only when the section's key facts are actually backed by a retrieved source or the reference data.
- verdict = contradicted when a number conflicts with a source or the reference data — name the conflict.
- verdict = unsupported when a central claim appears nowhere in what you actually retrieved (i.e. it was produced from memory).
- Set confidence honestly: high only when grounded in disclosed figures, low when largely inferred.
- List the specific problem claims in `issues`.
- When verdict is unsupported or contradicted, provide `corrected_text`: rewrite the section keeping only what the sources support, repair wrong numbers, and mark genuinely missing figures with [Not public]. Never replace a missing number with a new guess.

Be specific and be strict — flagging a real problem is far better than waving it through. Call submit_verification exactly once and write nothing else."""


def run_verification(client, model, base_messages, assistant_content,
                     submit_tool_use_id, web_search_tool, max_tokens=6000):
    try:
        convo = list(base_messages) + [
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": submit_tool_use_id,
                 "content": "Analysis received. Now audit it."},
                {"type": "text", "text": VERIFY_PROMPT},
            ]},
        ]
        tools = [web_search_tool, VERIFY_TOOL] if web_search_tool else [VERIFY_TOOL]
        msg = client.messages.create(
            model=model, max_tokens=max_tokens, thinking={"type": "adaptive"},
            tools=tools, messages=convo)
        findings = next((b.input for b in msg.content
                         if getattr(b, "type", None) == "tool_use"
                         and getattr(b, "name", "") == "submit_verification"), None)
        if not findings:
            return {}
        by_key = {f["section"]: f for f in (findings.get("findings") or []) if f.get("section")}
        return {"by_key": by_key, "overall": findings.get("overall", ""), "extra_msg": msg}
    except Exception as ex:
        print(f"[verify] run_verification failed: {ex}")
        return {}


def apply_verification(data, verdicts):
    by_key = (verdicts or {}).get("by_key") or {}
    for key, sec in (data.get("sections") or {}).items():
        f = by_key.get(key)
        if not isinstance(sec, dict) or not f:
            continue
        verdict = f.get("verdict", "")
        sec["verify_verdict"] = verdict
        sec["verify_issues"] = [i for i in (f.get("issues") or []) if i]
        if f.get("confidence"):
            sec["confidence"] = f["confidence"]
        corrected = (f.get("corrected_text") or "").strip()
        if verdict in ("unsupported", "contradicted") and len(corrected) > 30:
            sec["text"] = corrected
    if verdicts and verdicts.get("overall"):
        data["_verify_overall"] = verdicts["overall"]
    return data
