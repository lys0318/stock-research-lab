# 차트 기법 전략 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실험 기록 삭제, 차트 휠 확대, 차트 기법 전략 8개, 전략 비교를 추가한다.

**Architecture:** 전략은 `lab/strategies.py` 레지스트리(이름·분류·설명·매개변수·규칙 함수)로 두고 규칙은 보유 상태 배열을 반환한다. `engine.simulate`는 hold·model 외 모든 전략을 상태 기반으로 체결한다. API는 `/api/strategies`, `/api/compare`, `DELETE /api/runs/{id}`를 더한다.

**Tech Stack:** Python 3.12, pandas, FastAPI, pydantic / React 19, TypeScript, Plotly.

Spec: `docs/superpowers/specs/2026-09-26-chart-strategies-design.md`

## Global Constraints
- 신호는 t일 종가까지의 데이터만 사용, t+1 시가 체결.
- 기존 결과·설정(`ma_window`) 호환.
- 커밋 메시지는 한국어.

---

### Task 1: 전략 레지스트리와 규칙 (`lab/strategies.py`, `lab/engine.py`)
- Test `tests/test_strategies.py`: 공통 미래 불변, 골든크로스, RSI 유지, 펌핑 보유·손절, 역헤드앤숄더 합성 돌파·목표가·marks, 매개변수 검증.
- Produces: `STRATEGIES`, `resolve(strategy, params, config) -> dict`, `signals(frame, strategy, params) -> (np.ndarray[bool], list[dict])`, `catalog() -> list[dict]`.
- 커밋 `차트 기법 전략 8개 추가`

### Task 2: API — 매개변수 검증, 전략 목록, 비교, 삭제 (`lab/api.py`, `lab/store.py`)
- Test: `/api/strategies`, `/api/compare` 11행, 잘못된 매개변수 422, DELETE 헤더·행·파일.
- 커밋 `전략 비교와 실험 기록 삭제 API 추가`

### Task 3: 화면 (`web/src/*`)
- 전략 select·매개변수·비교표·자세히 실행, 기록 삭제(체크박스·선택 삭제), 휠 확대·드래그 이동, 헤드앤숄더 표시.
- 검증: `npx tsc --noEmit`, 브라우저 확인.
- 커밋 `화면에 차트 기법 전략·전략 비교·기록 삭제·휠 확대 추가` 후 push
