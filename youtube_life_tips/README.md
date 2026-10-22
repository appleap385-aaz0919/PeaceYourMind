# 생활꿀팁 YouTube Shorts

이 자동화는 이 폴더 안의 Codex CLI, 파일 우편함, Windows 작업 스케줄러만 사용합니다. Codex CLI는 이미 설치된 `D:\Tools\Codex`를 사용합니다. 예약 실행 중 Codex 데스크톱의 Scheduled 작업을 따로 띄우지 않으며, 일이 있을 때만 Codex 세션을 순서대로 실행합니다.

## 매일 실행

- Windows 작업 스케줄러가 사용자가 로그인할 때 저메모리 파일 감시기를 시작하고, 매일 오전 5시(한국 시간)에 오늘 날짜의 요청 파일을 만듭니다.
- 메인 작성, 독립 검수, 시각 자료 제작, 최종 감사 단계를 별도 Codex CLI 실행으로 처리합니다. 단계 사이의 전달 내용은 `work/mailbox/runs/`와 `work/daily/`의 파일로 남습니다.
- 모든 확인이 통과하면 영상을 생활꿀팁 전용 YouTube 채널에 비공개로 올리고 오전 7시에 공개되도록 예약합니다. 오전 6시 30분 이후에는 그날 게시를 건너뜁니다.
- 최종 결과(예약 성공, 건너뜀, 실패)는 `appleap385@gmail.com`에서 게재 결과 수신 메일 `aaz0919@naver.com`으로 발송합니다. 처음 한 번 `.\configure_email.ps1`을 실행해 Gmail 앱 비밀번호를 숨김 입력하고 테스트 메일을 확인해야 합니다. 비밀번호는 현재 Windows 계정에서만 복호화되는 DPAPI 형식으로 `state/`에 저장됩니다.
- PC가 오전 5시에 꺼져 있거나 절전 중이거나 Windows 사용자 세션이 로그인되어 있지 않아 시작하지 못한 경우, 인터넷·Codex 한도·ImageGen·TTS·렌더링·OAuth 중 하나라도 준비되지 않은 경우에는 해당 날짜를 건너뛰며 다음 날 보충하지 않습니다.
- Windows 사용자 계정은 로그인 상태로 두어야 하지만 화면은 `Win+L`로 잠가도 됩니다. PC는 켜져 있고 절전·최대 절전 상태가 아니며 인터넷에 연결되어야 합니다. 재부팅 후에는 Windows에 다시 로그인해야 감시기가 시작됩니다.
- Codex CLI는 단계가 실행되는 동안만 프로세스로 뜹니다. 감시기는 로그인 상태에서 가벼운 파일 확인만 수행합니다. Codex 데스크톱 앱의 창을 계속 열어둘 필요는 없습니다. CLI 로그인과 사용 한도는 필요합니다.

## 계절 우선 주제 선정

한국 계절에 맞는 생활 정보를 먼저 검색합니다. 봄은 3~5월, 여름은 6~8월, 가을은 9~11월, 겨울은 12~2월로 봅니다. 현재 계절에 맞고 신뢰할 수 있는 출처 두 곳 이상이 뒷받침하는 주제가 있으면 이를 우선 구성합니다. 그런 주제를 충분히 확인할 수 없을 때만 계절과 무관한 생활 팁으로 전환하며, 결과에 대체 사유를 기록합니다. 계절에 억지로 맞추거나 근거를 만들어내지 않으며, 검수 세션에서도 이 선택을 다시 확인합니다.

모든 영상은 새 한국어 대본과 새 ImageGen 장면으로 만듭니다. ImageGen은 하루 한 번만 사용합니다. 한도 초과나 생성 실패 때 다른 이미지 API, 내려받은 사진, 코드 그림으로 대신하지 않고 그 날짜를 건너뜁니다. Gemini API를 사용하지 않습니다. 내레이션은 `edge-tts` Python 클라이언트로 Microsoft의 온라인 한국어 TTS 서비스를 호출하고, 렌더링은 720x1280, 15fps, FFmpeg 한 스레드로 제한합니다. 이 방식은 별도 Cloud TTS API 키나 사용량 과금을 설정하지 않아도 되지만 인터넷 연결이 필요하고, Google Cloud TTS처럼 정식 API로 관리되는 경로보다 서비스 호환성이 바뀔 수 있습니다.

## 현재 설정

이 PC에는 생활꿀팁 채널 ID와 OAuth 토큰이 설정되어 있고, 오전 5시 큐 작업과 로그인 시 시작하는 파일 감시기가 Windows 작업 스케줄러에 등록되어 있습니다. 이메일 알림만 아직 앱 비밀번호 입력과 테스트가 필요합니다. 아래 최초 설정 항목은 PC를 새로 설정할 때 참고하세요.

## 최초 설정 또는 복구

이 프로젝트에는 별도 YouTube 채널 ID와 OAuth 파일이 아직 설정되어 있지 않습니다. 아래 설정을 끝내기 전에는 작업을 등록하지 않습니다.

1. PowerShell에서 `youtube_life_tips` 폴더로 이동해 `.\setup_codex.ps1`을 실행합니다. 기존 `D:\Tools\Codex`의 CLI 경로와 ChatGPT 로그인 상태만 확인하며 프로젝트 안에 CLI를 설치하지 않습니다.
2. `config.local.example.json`을 `state/config.local.json`으로 복사하고 생활꿀팁 전용 YouTube 채널 ID를 입력합니다. PIM 채널 ID는 쓰지 않습니다.
3. 생활꿀팁 채널을 관리하는 Google 계정의 OAuth 데스크톱 클라이언트 JSON을 `state/google_oauth_client.json`에 복사하고, 해당 Google 계정으로 OAuth 테스트 사용자 등록 및 `youtube.upload`, `youtube.readonly` 권한 설정을 완료합니다.
4. 이 폴더에서 `python authorize_youtube.py`를 실행하고 브라우저에서 해당 계정을 인증합니다. 출력된 채널 ID가 `state/config.local.json`의 ID와 정확히 같은지 확인합니다. 자격 증명과 토큰은 `state/` 아래에만 두며 Git에 올리지 않습니다.
5. Python 3, `ffmpeg`, `ffprobe`, 기존 `work/vendor` Edge TTS 및 Pillow가 준비되어 있는지 확인합니다.
6. 등록 전 점검: `python codex_mailbox.py doctor --require-youtube`
7. 점검이 통과하면 PowerShell에서 `.\register_tasks.ps1`을 실행합니다. 감시기와 오전 5시 작업이 등록됩니다. 해제할 때는 `.\unregister_tasks.ps1`을 실행합니다.

작업 등록 스크립트는 모든 사전 점검이 통과하지 않으면 작업을 하나도 등록하지 않습니다. Windows 시간대가 `Korea Standard Time`인지도 확인합니다. 작업 결과는 `work/mailbox/outbox/YYYY-MM-DD.json`, 감시 로그는 `work/mailbox/logs/watcher.log`, 이메일 오류는 `work/mailbox/logs/email.log`에서 확인할 수 있습니다. 이메일 설정은 YouTube OAuth 설정 후 `.\configure_email.ps1`을 실행해 완료합니다. Google 계정 비밀번호가 아니라 Google 앱 비밀번호를 입력하며, 입력값은 화면에 표시되지 않습니다.

## 제작·저작권 원칙

- 웹 검색은 사실 확인과 주제 조사에만 사용하고, 출처 문장이나 사진·영상·음성은 복사하지 않습니다. 출처 링크는 설명란에 기록하며 영상 화면에는 표시하지 않습니다.
- 참고 영상은 일반적인 편집 리듬만 참고할 수 있습니다. 프레임, 썸네일, 문장, 음성, 장면 구성은 가져오거나 재현하지 않습니다.
- 의료 진단·치료, 법률·금융 조언, 위험한 화학 혼합, 전기·가스 수리 등 위험한 주제는 자동 게시하지 않습니다.
- 생성 영상, OAuth 정보, 매일 작업 산출물은 커밋하거나 푸시하지 않습니다.
