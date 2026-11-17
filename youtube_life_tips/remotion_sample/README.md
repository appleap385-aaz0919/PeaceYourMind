# 생활꿀팁 Remotion 샘플

나무 서랍의 접촉면에 고체 양초를 바르는 방법을 설명하는 84.8초 세로 영상입니다. 원본 SVG 애니메이션, 기존 Edge TTS, 로컬 한글 글꼴을 사용합니다. 실물을 직접 시험한 전후 촬영이 아니며 예약 제작기에 연결하지 않은 샘플입니다.

이 폴더에서 실행합니다.

```powershell
npm ci
npm run prepare:sample
npm run dev
npm run lint
npm run render:sample
npm run review:sample
```

`prepare_sample.py`는 오전에 검토된 출처 기록을 보존하고 대본의 단일 윤문 확인 후 음성과 장면 시간을 준비합니다. 내용·음성 설정이 같은 클립은 재사용합니다. 대본을 수정할 때는 `DRAFT`의 내용 검증과 프로젝트 `humanize-korean` 절차를 먼저 수행한 뒤 `FINAL`과 장면 분할을 갱신합니다.

`render.mjs`는 Remotion의 기본 번들 브라우저를 사용하고 브라우저 동시 작업과 FFmpeg 스레드를 각각 1로 제한합니다. `review_sample.py`는 실제 MP4 전체 디코딩, 규격·음성·길이 검사와 20개 화면 추출을 수행합니다. 추출 화면의 구조·동작·가독성 검토는 별도로 수행하며 자동 규격 검사만으로 승인하지 않습니다.

완성 파일은 `../work/samples/2026-11-10-remotion/life-tip-drawer-remotion.mp4`, 검토 기록은 같은 폴더의 `review.json`입니다. 이 프로젝트에는 업로드 명령이 없습니다. TikTok 전달 사본은 기존 `save_tiktok_copy` 함수로 날짜별 폴더에 저장했습니다.

스킬 사용 범위와 공급자·출력 규칙은 [프로젝트 정책](../VIDEO_SKILLS.md)을 따릅니다. 런타임은 이 폴더에만 설치하며 생성 음성·로컬 글꼴·영상은 Git에서 제외합니다. Remotion 상업 이용 조건은 [공식 안내](https://www.remotion.dev/docs/license)를 확인합니다.


## AI 실사풍 시연 샘플

후속 요청으로 `TshirtBag` 구성을 추가했습니다. 도형 설명 대신 원본 ImageGen 사진 12장으로 손의 작업과 상태 변화를 보여줍니다. `AI 재현`을 화면에 표시합니다. 앞뒤 조각 구분이 틀렸던 7번 장면은 한 차례 부분 수정했고 나머지 장면은 보존했습니다. 이 샘플도 업로드하지 않습니다.

```powershell
python -X utf8 prepare_tshirt_sample.py
npm run lint
node render.mjs --tshirt
python -X utf8 review_sample.py --tshirt
```

원본·완성 MP4·검수 자료는 `../work/samples/2026-11-10-tshirt-bag/`에 저장합니다. 새 영상 편집 시 `public/generated/tshirt/`의 실제 12개 장면과 내레이션을 먼저 대조합니다. 원본 `storyboard.png`의 7번 칸은 수정 전이며, 최종 7번 장면은 위 public 폴더와 `imagegen-receipt.json`을 기준으로 확인합니다. 재생성·부분 수정은 업스트림 ImageGen 지침과 기존 호출 기록을 따릅니다.

브라우저 자동 열기는 사용하지 않습니다. 미리보기 서버를 필요에 따라 실행한 경우에도 작업 종료 시 자신이 시작한 세션을 확인해 종료하며 다른 프로젝트 서버는 종료하지 않습니다.
