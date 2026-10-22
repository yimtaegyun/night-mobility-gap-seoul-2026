# 밤의 이동 공백

서울 심야버스 정류장과 기존 저녁 교통수요의 공간적 불일치 분석.
2026년9월 원본과 2026년10월22일에 고정한 보행망·공식 운행정보를 재현합니다.

## 실행

검증 환경: Python3.12.14. 이 폴더에서 순서대로 실행합니다.

    python -m pip install -r requirements.txt
    python run_all.py

패키지 설치 후에는 인터넷·인증키 없이 실행됩니다. Windows에서는 필요하면 python 대신
py -3.12를 사용합니다. results/와 figures/의 같은 이름 파일을 교체합니다.

    python run_all.py --output-dir reproduced/results --figures-dir reproduced/figures

## 순서와 역할

1. analysis.py: 원본 검증, 시간대 집계, ID·좌표 결합, 거리 민감도, 3거점 순차 선택, 5개월 목록 비교.
2. extended_analysis.py: 전체 쌍 haversine 대조, 시간대·좌표·선정 기준 민감도, 정수계획 최적화와 선택 방식 비교.
3. audit_evidence.py: 외부 응답 해시 확인, 보행망 모형권, 기존 노선 시각·배차·방향, 가정 예산표.
4. verify_results.py: 표준 라이브러리로 원본24시간 합계·N합계, 거점 합집합, 보행 응답 결과를 독립 확인.
5. plot_figures.py, plot_extended.py: 그림10종을 PNG·PDF로 생성.

개별 실행도 가능하지만 전체 재현에는 run_all.py를 권장합니다.
정수계획은 최대60초이며 상태·상한·상대 갭을 selection_validation.json에 남깁니다.
동일 최적해가 여러 개여서 다른 환경에서는 솔버가 다른 동일 최적 조합을 선택할 수 있습니다.

## 입력과 고정된 외부 응답

data/raw/의 원본7개는 변경하지 않습니다. 9월 승하차CSV(CP949)1개, 9월2일 위치XLSX1개,
5월6일·6월2일·7월1일·8월4일·9월2일 노선별 정류소XLSX5개입니다.
assets/expected_input_sha256.json으로 원본 바이트를 검증합니다.
data/evidence/는 OSRM foot72개 지점쌍과 TOPIS 공개 검색14회의 원본 응답,
요청 내용·조회시각·해시를 포함합니다. 사용한 운행정보는 N14개·일반13개 노선입니다.
OSM 원본 그래프 기준시각은 응답에 없어 확인할 수 없습니다.

## 핵심 결과

| 구분 | 결과 | 해석 |
|---|---:|---|
| 관측 | 21\~23시 도로버스14,522,035건 | 9월 교통카드 월간 승차, 고유 이용자 수 아님 |
| 관측 공간분석 | N500m 밖2,823,334건·20.15% | 좌표 연결 표본14,010,743건 기준의 직선거리 |
| 공간 가정 | 3거점 추가권48곳·225,811건 | 기존 저녁 승차의 공간 포괄량 |
| 조건부 최적화 | 최적값225,811건·갭0 | 후보334곳·500m·저녁 가중·3개 이하 거점에 한정 |
| 보행망 모형 | 33곳·179,320건 | 고정된 추가권의 경로+연결거리500m 이내, 실측 아님 |
| 관측 | 추가권23·0·1시39,405·9,215·361건 | 기존 일반 노선 승차, 미충족 수요 아님 |

기하학적 포괄률은79.85%→81.46%(+1.61%p)입니다. 기존 N권 전체를 보행망으로 재산정하지
않았으므로179,320건을 더해 전체 보행 포괄률을 만들지 않습니다.
승객 증가·대기시간 절감·비용효율·탄소감축을 측정하거나 예측한 결과는 없습니다.

## 방법과 한계

결합키는 표준버스정류장ID=NODE_ID(9자리 문자열), ARS는 표시용입니다. 한강버스8행과
공항 관련 N6000·N6002·N6701·N6703은 범위에서 제외합니다. 도시형N14개를 기준으로 씁니다.
단위구3차원 KDTree 현 길이를 구면 거리로 변환하며 지구 반지름6,371,008.8m를 사용합니다.
전체 쌍 haversine과 대조해 거리·임계값 분류가 일치했습니다. 좌표 누락·불일치·민감도도 공개합니다.
서울시 버스 노선의 결합 표본으로, 서울 행정경계 안 전수조사는 아닙니다.

후보334곳은 N500m 밖·21\~23시 월2,000건 이상입니다. 순차 선택은 미포괄 주변 승차 합을
최대화하고 동점은 NODE_ID 오름차순입니다. 정의한 조건에서 최적 총량을 확인했지만 최적해는
유일하지 않습니다. 반경300·800m나1\~3시 가중에서는 후보가 달라집니다.

보행망은 거점→주변 정류장 방향입니다. 경로에 양 끝점 연결거리(직선)를 더하며 끝점별 오차
25m 이내만 사용합니다. 같은 정류장은0m입니다. N연결은8개 위치마다 직선 최근접3곳을
조회한 경로 중 짧은 값이며 전수 최단거리가 아닙니다. 역방향·야간 통행·횡단 대기·조명·경사·
휠체어 접근성은 미확인입니다. 지도 완전성과 실제 통행 가능성은 현장 확인이 필요합니다.

TOPIS 첫차·막차는 기점 계획 출발이며 거점 통과시각이 아닙니다. 공시 배차도 실제 도착을
보장하지 않습니다.9월 관측과10월 조회를 구분합니다. 예산30·50·80만원/대·야간과 승차
50·100·200건은 모두 가정입니다. 공식2023년 전일 원가를2026년 심야 단가로 환산하지 않았습니다.

## 주요 결과 파일

- 핵심: metrics.json, hourly.csv, distance_sensitivity.csv, scenario_three_hubs.csv.
- 시간대: stops_hourly.csv, time_window_sensitivity.csv, hub_temporal_audit.csv, route_hourly.csv.
- 품질: extended_checks.json, coordinate_consistency.csv, coordinate_source_sensitivity.csv, n_ids_outside_snapshot.csv.
- 선택: selection_validation.json, method_comparison.csv, candidate_robustness.csv.
- 보행: walking_validation.json, walking_pairs_audit.csv, fixed_hub_walking_audit.csv, hub_walking_summary.csv, walking_threshold_sensitivity.csv.
- 운행: schedule_facts.csv, hub_existing_route_audit.csv, n_connection_sample_best.csv, n_connection_directions.csv.
- 예산: budget_sensitivity.csv. 독립 검증: verification.json, input_sha256.json, environment.json.

## 선택적 재조회

    python acquire_evidence.py --fetch

기존 응답은 재조회하지 않습니다. 갱신 시 기존 폴더를 보존하고 새 캐시를 만듭니다.
조회일이 바뀐 결과를 제출 보고서와 혼용하지 않습니다. 요청 간격1.15초 이상·식별 User-Agent·
캐시를 사용하며 대규모 수집용이 아닙니다. 정책: https://routing.openstreetmap.de/about.html

## 공개와 이용조건

공개 저장소: https://github.com/yimtaegyun/night-mobility-gap-seoul-2026

코드·원본 데이터·고정된 외부 응답·분석결과·그림을 함께 제공합니다. 개인정보·서명·내부
리서치 기록은 포함하지 않습니다. GitHub의 Code → Download ZIP으로 전체 파일을 내려받아
위 실행 순서대로 재현할 수 있습니다. 공모전 제출 보고서에도 이 저장소 주소를 표시합니다.

서울시 원본은 공공누리1유형으로 출처를 표시합니다. OSM 경로와 파생 데이터는 ODbL 조건을
따릅니다(data/evidence/LICENSE_OSM.md). 자체 코드의 별도 공개 라이선스는 지정하지 않았으며
권리자가 공개 시 결정할 수 있습니다. NanumGothic은 SIL OFL(assets/OFL.txt)입니다.

© OpenStreetMap contributors: https://www.openstreetmap.org/copyright
지도 오류 제보: https://www.openstreetmap.org/fixthemap
AI 활용은 AI_USAGE.md, 출처는 DATA_SOURCES.md에 있습니다.
