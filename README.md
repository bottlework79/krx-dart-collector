# KRX DART Collector — Public GitHub Actions

공개 저장소는 **실행기**이며 운영 소스·재무 DB는 비공개 [bottlework79/krx-stock-data](https://github.com/bottlework79/krx-stock-data)에 둡니다.

**최신 확정 재무 설계:** 비공개 저장소 `docs/FINANCIAL_DESIGN.md` (2026-11-02). 공개 Actions를 수정하기 전에 반드시 확인합니다.

## 현재 주요 워크플로우

| 파일 | 현재 역할 | 설계상 상태 |
| --- | --- | --- |
| `dart_collect.yml` | DART JSON 재무제표 수집, 기본 2015~2026 | 유지 |
| `financial_calculate.yml` | 저장 DB 기반 오프라인 재무 계산 | 유지하되 계산 중 누락 계정 조회 연결 필요 |
| `dart_original_enrich.yml` | 별도 누락 원문 사전 수집 | **레거시**, 새 기능 확장 금지; 기존 계산 회귀 보장 전 삭제 금지 |
| `financial_calculation_verify.yml` | 재무 계산 검증 | 유지 |
| `krx_daily_public.yml` | KRX 주가 수집 | 유지 |

기타 패턴·추세 워크플로우는 각각의 독립 기능으로 유지합니다.

## 고정 운영 원칙

1. 재무 수집은 **2015년부터 DART JSON만** 저장하며, 원문을 미리 대량 수집하지 않습니다.
2. 재무 계산은 기존 2025 연간/2026 반기 성공 계산기를 재사용합니다.
3. 필요한 계정이 JSON에 없으면 XBRL, 그래도 없으면 **계산 중 그 계정에 한해** 공시 원문·주석을 조회하는 것이 목표입니다. 현재 오프라인 계산 워크플로우에는 아직 미구현입니다.
4. 공개 Actions는 비공개 저장소를 체크아웃해 실행하고 결과는 비공개 저장소에만 저장합니다.
5. API 키·토큰·비공개 DB를 공개 커밋/로그/아티팩트에 노출하지 않습니다.
6. 2025/2026 기존 계산 회귀를 통과하기 전 레거시 경로를 제거하지 않습니다.

## 실행 안내

[Actions](https://github.com/bottlework79/krx-dart-collector/actions)에서 필요한 워크플로우를 수동 실행합니다. 실행 성공과 재무지표 계산 성공은 별개로 검증합니다.
