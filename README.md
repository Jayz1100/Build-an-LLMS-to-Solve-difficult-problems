# Build-an-LLMS-to-Solve-difficult-problems
## 简介 这是一个基于 FastAPI + Ollama 的异步评分系统，用于批量处理题目评分， 支持求解 → 验证 → 修复的多轮流程，最终产出严格 JSON 格式的结果。  ## 功能 - 异步并发，大幅提升运行速度 - JSON Schema 校验，保证输出格式 - 错误修复机制，提高健壮性  ## 使用方法 ```bash pip install -r requirements.txt uvicorn app:app --reload
