
# 自验证高难题求解器 · FastAPI 版

## 快速开始
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
# 浏览器打开 http://127.0.0.1:8000
```

## 说明
- 前端使用 Jinja2 模板（`templates/index.html`），无需单独构建即可运行。
- 后端使用 FastAPI，`/solve` 渲染网页，`/api/solve` 提供 JSON API 以便将来接 React/前端应用。
- 需要本地运行 Ollama 并已拉取模型：
  ```bash
  ollama run deepseek-r1:1.5b
  ```

## 目录结构
```
self_verify_solver/
├── app.py
├── requirements.txt
├── README.md
└── templates/
    └── index.html
```

## 注意
- 这是一个“求解→验证→修复”的最小可用演示，适用于 MCQ / Numeric / Proof Outline / Short Answer 四类任务的结构化 JSON 输出。
- 如需扩展到更复杂题型，可在 `TASK_TYPES`、Prompt 模板与 `solve_one` 流程中按需添加。
