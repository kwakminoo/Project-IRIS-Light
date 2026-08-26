---
name: iris-learning
description: >
  Start or stop Iris 업무 학습 (demonstration recording for computer-use automation).
  Use when: 업무 학습 시작, 내가 하는 거 기록해, 이 작업 배워줘, 화면 조작 녹화해,
  작업 가르쳐줘, 학습 시작, start learning, record my workflow,
  학습 끝, 기록 멈춰, 녹화 종료, stop learning, stop recording.
  To RUN an already-learned workflow (배운 업무 실행): use learning.run instead.
---

# Iris 업무 학습

## Steps

1. `iris_invoke` → `learning.status` 로 현재 상태 확인 (`state`: idle / recording / processing / error)
2. **시작 요청** + `state=idle`:
   - `iris_invoke` → `learning.start`
   - 응답: "화면에서 작업을 보여주세요. 끝나면 '학습 끝'이라고 말씀해 주세요."
3. **종료 요청** + `state=recording`:
   - `iris_invoke` → `learning.stop`
   - 응답: "녹화를 종료했습니다. VLM이 분석 중이니 잠시 기다려 주세요."
4. `state=processing`:
   - 아직 이전 학습이 처리 중입니다. 완료될 때까지 기다려 주세요.
5. `state=error`:
   - `iris_invoke` → `learning.status` 재확인 후 사용자에게 오류 내용 전달

## Do not

- 이미 배운 업무 **실행** 요청이면 `learning.run`을 쓰고 이 스킬을 쓰지 말 것.
- `learning.start`를 `state=idle` 확인 없이 바로 호출하지 말 것.
