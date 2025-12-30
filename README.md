# 한국형 Paradox 시뮬 데모 프로토타입

이 프로젝트는 **한국형 Paradox 감성의 정치 시뮬레이션**을 검증하기 위한 데모 프로토타입이다.  
세력 균형과 사건 로그를 기반으로, **AI 요약이 게임 연출에 어떤 역할을 할 수 있는지**를 보여준다.

완성된 게임이 아닌 **설계·연출 검증용 프로토타입**이며, 모든 시뮬레이션 결과는 **seed 기반으로 재현 가능**하다.  
드라마틱 요약과 연대기 요약을 **동일한 시뮬 결과에서 비교**할 수 있도록 구성되어 있다.  
UI는 기능 검증을 위한 **최소 데모 수준**만 제공된다.

---

## 핵심 특징

- 세력 기반 정치 시뮬레이션 + 사건 로그
- 핵심 인물 5명 + 이벤트 시스템
- seed 기반 재현성 보장
- 드라마틱 상황 요약 (`/ai/explain`)
- 연대기 요약 (`/ai/chronicle`)
- LLM 호출 없는 rule 기반 요약 + LLM 확장 가능 구조

---

## 빠른 시작 (데모 UI)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- 브라우저 접속: `http://127.0.0.1:8000/`
- 시나리오: `baseline`, `famine`, `deficit`, `warlord`
추천 데모 흐름:
- `scenario=warlord`, `seed=42`, `turns=120` 설정
- Run 버튼으로 로그 생성
- Explain 버튼으로 위기 상황 요약(드라마틱 3문장)
- Chronicle 버튼으로 10년간의 연대기 요약(6~10줄)

같은 시뮬 결과를 두 가지 톤(연출용 / 기록용)으로 비교하는 것이 핵심 포인트다.

---

## API 요약

- `POST /api/run`: 시뮬 실행 후 로그 생성
- `POST /api/snapshot`: 로그 기반 스냅샷 로드
- `POST /api/next_turn`: 다음 턴 진행
- `POST /ai/explain`: 드라마틱 요약
- `POST /ai/chronicle`: 연대기 요약
- `POST /api/pending_decision`, `POST /api/decide`: 결단 이벤트 처리
- `POST /api/set_budget`: 예산 배분 이벤트 처리

---

## CLI 스크립트

```bash
python -m scripts.run_sim --scenario warlord --seed 42 --turns 120 --out logs/run_warlord_42.jsonl
python -m scripts.demo_run --scenario warlord --seed 42 --turns 120 --out out/demo_report.md
python -m scripts.verify_all
```

---

## 테스트

```bash
pytest
```

---

## 범위와 한계

이 프로젝트는 완성된 게임이 아니다.  
UI/콘텐츠 볼륨보다 시뮬 구조와 연출 검증에 초점을 둔다.  
실제 게임 적용 시에는 별도의 UX/밸런스 설계가 필요하다.
