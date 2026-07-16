# 에이전트 메모리 공간

이 디렉토리는 각 에이전트가 작업 중 분석한 내용을 저장하고 공유하는 공간입니다.

## 목적
- 반복 분석 방지
- 에이전트 간 컨텍스트 공유
- 프로젝트 지식 축적

## 디렉토리 구조
```
.claude/memory/
├── README.md              # 이 파일
├── project-lead/          # 리더 에이전트 메모
├── implementer/           # implementer 분석 이력
└── reviewer/              # reviewer 분석 이력
```

## 작성 규칙
- 파일명은 분석 대상을 명확히 표현 (예: `auth-flow-analysis.md`)
- 날짜를 상단에 기록
- 분석 결론을 요약 형태로 상단에 작성
