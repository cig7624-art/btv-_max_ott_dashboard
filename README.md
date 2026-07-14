# B tv+ max 콘텐츠 경쟁력 비교 대시보드

타이틀을 추가하면 키노라이츠에서 포스터와 OTT 정액제 제공처를 조회하고, 넷플릭스·쿠팡플레이·티빙·웨이브·디즈니+·왓챠 편성 여부를 O/X로 표시하는 Streamlit 앱입니다.

## GitHub에 올릴 파일

ZIP을 푼 뒤 아래 파일과 폴더를 저장소 최상단에 모두 업로드합니다.

- `app.py`
- `requirements.txt`
- `packages.txt`
- `btv_max_contents.csv`
- `.streamlit/secrets.toml.example` — 참고용이며 없어도 실행됩니다.

## Streamlit 배포

1. GitHub에서 새 저장소를 만듭니다.
2. 위 파일을 저장소 최상단에 업로드합니다.
3. Streamlit Community Cloud에서 `Create app`을 선택합니다.
4. 저장소와 `main` 브랜치를 선택하고 Main file path에 `app.py`를 입력합니다.
5. Deploy를 누릅니다.

## 추가·삭제 내용을 영구 저장하는 설정

Streamlit Cloud는 실행 중 생성된 로컬 파일이 재시작 때 초기화될 수 있습니다. 타이틀 추가·삭제 결과를 계속 보존하려면 GitHub API 저장 설정이 필요합니다.

Streamlit 앱의 `Settings > Secrets`에 아래와 같이 입력합니다.

```toml
ADMIN_PASSWORD = "원하는관리자비밀번호"

[github]
GITHUB_TOKEN = "github_pat_xxxxxxxxxxxxxxxxx"
GITHUB_REPO = "깃허브아이디/저장소명"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "btv_max_contents.csv"
```

`GITHUB_TOKEN`은 해당 저장소의 **Contents: Read and write** 권한이 있는 Fine-grained personal access token을 사용합니다. 토큰을 `secrets.toml` 파일로 만들어 GitHub 저장소에 직접 올리면 안 됩니다.

`ADMIN_PASSWORD`를 설정하지 않으면 누구나 타이틀을 추가·삭제할 수 있습니다.

## 주의

- O/X는 키노라이츠의 정액제·바로 보기 정보에서 자동 추출합니다.
- 동명 콘텐츠는 공개연도를 함께 입력하면 매칭 정확도가 높아집니다.
- 키노라이츠 화면 구조가 바뀌면 조회 로직 수정이 필요할 수 있습니다.
