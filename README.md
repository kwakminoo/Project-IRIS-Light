# Iris Light

원본 Iris의 **메인 HUD UI** + **Ollama 클라우드 채팅** 데스크톱 앱입니다.

## 실행

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
run.bat
```

Ollama가 실행 중이어야 합니다. 클라우드 모델 예:

```bat
ollama run gemma4:31b-cloud
```

앱에서 입력창 오른쪽 **모델 콤보**로 Ollama **무료 클라우드 모델**을 선택할 수 있습니다.  
마지막으로 선택한 모델은 `~/.iris-light/iris_light.db`에 저장되어, 앱을 다시 켜도 유지됩니다.

## 포함 / 미포함

| 포함 | 미포함 |
|------|--------|
| 구체·채팅·파형·좌측 러닝윈도우·아이콘 그리드 | STT/TTS·Hermes 전용 이메일 |
| Ollama 모델 선택·채팅·thinking 로그 | 자체 웹검색/컴퓨터유즈/라우터 |
| 프로필·설정·모니터·알림 | |
| **Iris Wiki** (Obsidian vault + 로컬 wiki) | |
| **이메일** (Gmail/Naver IMAP·SMTP, 다계정) | |
