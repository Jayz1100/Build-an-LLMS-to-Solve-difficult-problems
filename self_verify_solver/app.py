
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web App Interface for Self-Verify Solver
---------------------------------------
运行方式：
  1) python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
  2) pip install -r requirements.txt
  3) uvicorn app:app --reload
  4) 打开浏览器 http://127.0.0.1:8000
"""
import json, re, asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from ollama import AsyncClient

# =============================
# 1) 全局配置
# =============================
MODEL_SOLVER = "deepseek-r1:1.5b"
MODEL_VERIFIER = "deepseek-r1:1.5b"
MODEL_FIXER = "deepseek-r1:1.5b"

TEMPERATURE_SOLVER = 0.0
TEMPERATURE_VERIFIER = 0.0
TEMPERATURE_FIXER = 0.0

SEED = 42            # 结果可复现
MAX_ITERS = 3        # 最大修复轮数
TASK_TYPES = {"mcq", "numeric", "proof_outline", "short_answer"}

# =============================
# 2) Prompt 模板
# =============================
SOLVER_SYSTEM = (
    "You are a problem solver. Provide ONLY a single-line JSON object as output. "
    "Do not include chain-of-thought. Keep reasoning internal."
)

SOLVER_FEWSHOT = {
    "mcq":     "{\"answer_type\":\"mcq\",\"final_answer_letter\":\"B\",\"key_checks\":[\"letter in {A,B,C,D}\"],\"confidence\":0.78}",
    "numeric": "{\"answer_type\":\"numeric\",\"final_answer_value\":\"42\",\"key_checks\":[\"units consistent\"],\"confidence\":0.75}",
    "proof_outline": "{\"answer_type\":\"proof_outline\",\"final_claim\":\"g(n) is divisible by 3\",\"key_lemmas\":[\"mod arithmetic\"],\"key_checks\":[\"no gap\"],\"confidence\":0.70}",
    "short_answer":  "{\"answer_type\":\"short_answer\",\"final_answer_text\":\"the graph is bipartite\",\"key_checks\":[\"no odd cycle\"],\"confidence\":0.72}",
}

SOLVER_USER_TEMPLATE = (
    "Task type: {task_type}\n"
    "Provide your final answer in STRICT JSON (one line).\n"
    "Constraints:\n"
    "- Do NOT include any chain-of-thought.\n"
    "- Keep output to ONE line JSON.\n"
    "Example for {task_type}: {fewshot}\n\n"
    "Problem:\n{problem}\n"
)

VERIFIER_SYSTEM = (
    "You are a strict solution verifier. Accept a problem and a candidate JSON answer. "
    "Check ONLY for structure, consistency, and obvious logical issues; do NOT provide chain-of-thought. "
    "Output a ONE-LINE JSON bug report: {\"verdict\":\"pass|fail\",\"bugs\":[...],\"bug_codes\":[...],\"advice\":[...]}."
)

VERIFIER_USER_TEMPLATE = (
    "Problem:\n{problem}\n\n"
    "Candidate JSON (one line):\n{candidate}\n\n"
    "Validation rules (non-exhaustive):\n"
    "- mcq: final_answer_letter must be one of A,B,C,D.\n"
    "- numeric: final_answer_value simplified (no explanatory text).\n"
    "- proof_outline: final_claim present; key_lemmas/key_checks concise.\n"
    "- short_answer: final_answer_text concise; avoid hedging.\n"
    "- confidence in [0,1].\n"
    "Return ONE-LINE JSON as specified."
)

FIXER_SYSTEM = (
    "You are a fixer that revises the previous JSON answer using a bug report. "
    "Return ONLY ONE-LINE JSON with the same schema as the solver's type. No chain-of-thought."
)

FIXER_USER_TEMPLATE = (
    "Problem:\n{problem}\n\n"
    "Previous JSON answer:\n{candidate}\n\n"
    "Bug report:\n{bug_report}\n\n"
    "Revise your answer to FIX the bugs. Keep format STRICT and concise."
)

# =============================
# 工具函数
# =============================
JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)

def extract_json(line: str) -> Dict[str, Any]:
    """从模型输出中提取并解析单个 JSON 对象（单行/多行容错）。"""
    try:
        data = json.loads(line)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = JSON_OBJ_RE.search(line)
    if m:
        return json.loads(m.group(0))
    raise ValueError("No valid JSON object found")

async def call_llm(client: AsyncClient, model: str, system: str, user: str, temperature: float = 0.0) -> Dict[str, Any]:
    resp = await client.chat(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        options={"temperature": temperature, "seed": SEED},
    )
    return extract_json(resp["message"]["content"])

# =============================
# 自验证流水线
# =============================
from dataclasses import dataclass
@dataclass
class SolveResult:
    ok: bool
    final_answer: Dict[str, Any]
    iters: int

async def solve_one(problem: str, task_type: str = "mcq", max_iters: int = MAX_ITERS) -> SolveResult:
    assert task_type in TASK_TYPES, f"task_type must be one of {TASK_TYPES}"
    client = AsyncClient()
    candidate = None
    verifier_out = {}

    for it in range(1, max_iters + 1):
        if candidate is None:
            user = SOLVER_USER_TEMPLATE.format(task_type=task_type, fewshot=SOLVER_FEWSHOT[task_type], problem=problem)
            cand = await call_llm(client, MODEL_SOLVER, SOLVER_SYSTEM, user, TEMPERATURE_SOLVER)
        else:
            bug_report_json = json.dumps(verifier_out, ensure_ascii=False)
            user = FIXER_USER_TEMPLATE.format(problem=problem, candidate=json.dumps(candidate, ensure_ascii=False), bug_report=bug_report_json)
            cand = await call_llm(client, MODEL_FIXER, FIXER_SYSTEM, user, TEMPERATURE_FIXER)

        verifier_user = VERIFIER_USER_TEMPLATE.format(problem=problem, candidate=json.dumps(cand, ensure_ascii=False))
        verifier_out = await call_llm(client, MODEL_VERIFIER, VERIFIER_SYSTEM, verifier_user, TEMPERATURE_VERIFIER)
        verdict = str(verifier_out.get("verdict", "fail")).lower()
        if verdict == "pass":
            return SolveResult(ok=True, final_answer=cand, iters=it)
        candidate = cand

    return SolveResult(ok=False, final_answer=candidate or {}, iters=max_iters)

# =============================
# FastAPI 页面
# =============================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/solve", response_class=HTMLResponse)
async def solve(request: Request, problem: str = Form(...), task_type: str = Form(...)):
    res = await solve_one(problem, task_type)
    return templates.TemplateResponse("index.html", {"request": request, "problem": problem, "task_type": task_type, "result": res})

# 额外：JSON API，方便前端调用
@app.post("/api/solve", response_class=JSONResponse)
async def api_solve(payload: Dict[str, Any]):
    problem = payload.get("problem", "")
    task_type = payload.get("task_type", "mcq")
    max_iters = int(payload.get("max_iters", MAX_ITERS))
    res = await solve_one(problem, task_type, max_iters=max_iters)
    return {"ok": res.ok, "final_answer": res.final_answer, "iters": res.iters, "meta": {"model": MODEL_SOLVER}}
