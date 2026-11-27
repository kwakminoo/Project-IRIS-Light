# Document Intelligence 계약

- `PreparedAttachments.model_content()`는 첨부 ID, 상대 파일명, MIME, 페이지 상태, 일부 읽음 표시, 추출 내용을 보낸다. 호스트 절대 경로는 Desktop의 `AttachmentStore`와 로컬 참조 테이블에 저장한다. 이전 대화의 자동 경로 표기를 추론 직전에 제거하고 사용자가 입력한 경로와 문서 본문을 보존한다.
- `content_extract(attachment_id, relative_path?, page_from?, page_to?, ocr_language?)`에서 폴더 안 파일은 인덱싱한 상대 경로를 지정한다. Host는 활성 대화와 신뢰된 Workspace, 파일 존재, 원본 경로의 변경, 심볼릭 링크·정션·경로 탈출을 확인한다. 기존 명시적 `source`, `path`, `url`은 호환 입력이다. 로컬 파일 경로에는 기존 읽기 정책을 적용한다.
- 페이지는 1부터 시작한다. PyMuPDF로 선택 구간만 읽고, 텍스트가 비어 있는 레거시 문서에는 pypdf 호환 경로를 사용한다. PDF는 페이지별 `text`, `ocr`, `hybrid`, `vision`, `empty`, `failed`, `unread` 상태를 갖는다. 렌더링 크기와 문서 페이지 수 및 모델 텍스트 길이에 상한을 둔다.
- 빈 PDF, 암호화 PDF, 손상 PDF, 잘못된 페이지 범위, 렌더링 실패, OCR 실행 파일·언어팩·타임아웃·글자 없음·일반 실패, 파일 접근, 취소에는 별도 `error_code`가 있다. 사용자가 보는 오류 문자열과 페이지별 안전한 상태를 함께 반환한다.
- 첨부 ID로 호출하는 `content.dump_lab_scripts`는 로컬 Vision 경계를 적용하고 파일 또는 저장 오류에 호스트 경로를 포함하지 않는다.
- Tesseract는 설치된 데이터와 실행 파일만 사용한다. `ocr_language`는 `kor+eng`, `kor`, `eng`를 받는다. OCR subprocess가 취소되거나 제한 시간에 도달하면 종료한다. 이미지의 자동 분석은 로컬 OCR을 우선하고, 비전 fallback은 앞서 검증한 로컬 엔드포인트에서 실행한다. `vision_analyze_attachment`로 현재 대화에 있는 PDF 한 페이지나 이미지 한 장을 다시 분석할 수 있다.
- 창을 닫을 때 실행 중인 `AttachmentWorker`가 있으면 취소를 요청하고 스레드가 완전히 끝난 후 창을 닫는다. 이전 대화의 늦은 콜백에는 기존 턴 식별자를 적용한다.

로컬 의미 캐시, 장문 정량 벤치, 외부 Vision용 사용자 동의와 전송 계약은 잔여 범위다. [검증 인수인계](wave17-fc-validation-handoff.md)
