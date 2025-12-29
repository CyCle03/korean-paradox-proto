# 한국형 Paradox 시뮬 엔진 프로토타입

Python 3.11 기준의 룰 기반 시뮬레이션 엔진 + 이벤트 시스템 검증용 프로토타입입니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행 (CLI)

```bash
python -m scripts.run_sim --turns 120 --seed 42 --out logs/run.jsonl
```

- `logs/run.jsonl`에 각 턴 상태와 이벤트가 기록됩니다.
- 종료 시 요약 지표(파산 횟수, 폭동 횟수, 평균 민심, 최종 세력분포)가 출력됩니다.

## 실행 (FastAPI)

```bash
uvicorn sim.api:app --reload
```

- `GET /state` 현재 상태
- `POST /step` 1턴 진행
- `POST /run?turns=120&seed=42` 배치 실행

## 실행 (AI 요약 API)

```bash
uvicorn app.main:app --reload
```

- `POST /ai/explain`
- `POST /ai/chronicle`

환경변수:

- `OPENAI_API_KEY` 설정 시 LLM 모드 사용
- `OPENAI_MODEL` 기본값: `gpt-4o-mini`

요청 예시:

```bash
curl -X POST http://127.0.0.1:8000/ai/explain \\
  -H 'Content-Type: application/json' \\
  -d '{\"scenario\":\"warlord\",\"seed\":42,\"turn_window\":20,\"log_path\":null}'
```

## 테스트

```bash
pytest
```

## 프로젝트 구조

- `sim/state.py` 상태 모델과 클램프 유틸
- `sim/engine.py` 턴 기반 규칙 계산
- `sim/events.py` 이벤트 10개 및 선택 로직
- `scripts/run_sim.py` JSONL 기록 CLI
- `app/main.py` AI 요약 API 엔드포인트
- `ai/summarize.py` 로그 로딩 및 요약 로직
- `ai/prompts.py` LLM 프롬프트 템플릿
- `tests/` pytest 모음
